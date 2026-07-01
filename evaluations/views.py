import random
import uuid
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

logger = logging.getLogger(__name__)
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from accounts.permissions import role_required
from courses.models import Course, CourseRegistration, Department, CourseLecturer
from .models import EvaluationSession, EvaluationQuestion, SubmissionRecord, EvaluationResponse
from .forms import EvaluationForm
from .constants import MIN_RESPONSES_FOR_AGGREGATE_DISPLAY
CustomUser = get_user_model()


def get_categories_for_course(course):
    dept_name = course.department.name.upper()
    course_title = course.title.upper()
    categories = ['CORE']  # Core is always included

    # STEM
    stem_keywords = [
        'ENGINEERING', 'SCIENCE', 'AGRICULT', 'ANIMAL', 'CROP', 'ZOOLOGY', 'BOTANY',
        'CHEMISTRY', 'PHYSICS', 'MATHEMATICS', 'COMPUTER', 'MICROBIOLOGY', 'BIOCHEMISTRY'
    ]
    if any(k in dept_name for k in stem_keywords):
        categories.append('STEM')

    # Languages
    lang_keywords = ['ARABIC', 'FRENCH', 'PORTUGUESE', 'LINGUISTICS', 'YORUBA']
    if any(k in dept_name for k in lang_keywords):
        categories.append('LANG')

    # Business
    bus_keywords = [
        'ACCOUNTING', 'FINANCE', 'BUSINESS', 'MARKETING', 'ADMINISTRATION',
        'INSURANCE', 'TAXATION', 'LOGISTICS', 'MANAGEMENT'
    ]
    if any(k in dept_name for k in bus_keywords) and 'EDUCATION' not in dept_name:
        categories.append('BUS')

    # Humanities
    hum_keywords = [
        'HISTORY', 'PHILOSOPHY', 'PEACE', 'PSYCHOLOGY', 'SOCIOLOGY',
        'RELIGIOUS', 'LAW', 'ENGLISH', 'LITERATURE'
    ]
    if any(k in dept_name for k in hum_keywords):
        categories.append('HUM')

    # Studio Art
    art_keywords = ['FINE ARTS', 'INDUSTRIAL DESIGN', 'ART']
    if any(k in dept_name for k in art_keywords):
        categories.append('ART')

    # Theater
    theater_keywords = ['THEATRE', 'FILM', 'DANCE', 'DRAMA']
    if any(k in dept_name for k in theater_keywords):
        categories.append('THEATER')

    # Music
    if 'MUSIC' in dept_name:
        # Check course title to distinguish ensemble vs lesson
        ensemble_keywords = ['ENSEMBLE', 'CONCERT', 'CHOIR', 'BAND', 'ORCHESTRA', 'CHORUS']
        if any(k in course_title for k in ensemble_keywords):
            categories.append('MUSIC_ENSEMBLE')
        else:
            categories.append('MUSIC_LESSON')

    return categories

# ---------------------------------------------------------------------------
# Student Dashboard & Evaluation Flow
# ---------------------------------------------------------------------------

@role_required('STUDENT')
def student_dashboard(request):
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    
    if not active_session:
        return render(request, 'evaluations/student_dashboard.html', {
            'active_session': None,
            'courses': []
        })
        
    # Get all registrations for this student for the active session's semester
    registrations = CourseRegistration.objects.filter(
        student=request.user,
        course__semester=active_session.title
    ).select_related('course', 'course__department')
    
    # Get IDs of courses already submitted in this session
    submitted_course_ids = set(
        SubmissionRecord.objects.filter(
            student=request.user,
            session=active_session
        ).values_list('course_id', flat=True)
    )
    
    courses_data = []
    for reg in registrations:
        courses_data.append({
            'course': reg.course,
            'is_manual_addition': reg.is_manual_addition,
            'submitted': reg.course.id in submitted_course_ids
        })
        
    return render(request, 'evaluations/student_dashboard.html', {
        'active_session': active_session,
        'courses_data': courses_data
    })


@role_required('STUDENT')
def evaluate_course(request, course_id):
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    if not active_session:
        messages.error(request, "There is no active evaluation session at this time.")
        return redirect('evaluations:student_dashboard')
        
    course = get_object_or_404(Course, pk=course_id, semester=active_session.title)
    
    # Guard: must be registered for this course
    if not CourseRegistration.objects.filter(student=request.user, course=course).exists():
        raise PermissionDenied("You are not registered for this course.")
        
    # Guard: cannot evaluate twice
    if SubmissionRecord.objects.filter(student=request.user, course=course, session=active_session).exists():
        messages.warning(request, "You have already submitted an evaluation for this course.")
        return redirect('evaluations:submission_confirmation', course_id=course.id)
        
    if request.method == 'POST':
        form = EvaluationForm(request.POST, course=course)
        if form.is_valid():
            idempotency_key = form.cleaned_data['idempotency_key']
            
            # Interruption safety: check if record already exists with this key
            retry_record = SubmissionRecord.objects.filter(
                student=request.user,
                course=course,
                session=active_session,
                idempotency_key=idempotency_key
            ).first()
            
            if retry_record:
                # Redirect to confirmation page (idempotent success)
                return redirect('evaluations:submission_confirmation', course_id=course.id)
                
            # Atomic write transaction
            try:
                with transaction.atomic():
                    # Check for race condition double submission (different idempotency key)
                    if SubmissionRecord.objects.filter(student=request.user, course=course, session=active_session).exists():
                        return render(request, 'evaluations/already_submitted.html', {'course': course})
                        
                    # 1. Create SubmissionRecord (identifies that this student submitted for this course/session)
                    SubmissionRecord.objects.create(
                        student=request.user,
                        course=course,
                        session=active_session,
                        idempotency_key=idempotency_key
                    )
                    
                    # 2. Create EvaluationResponses (structurally separated from student identity)
                    categories = get_categories_for_course(course)
                    questions = EvaluationQuestion.objects.filter(category__in=categories)
                    for q in questions:
                        field_name = f'question_{q.id}'
                        val = form.cleaned_data.get(field_name)
                        
                        resp = EvaluationResponse(
                            course=course,
                            session=active_session,
                            question=q
                        )
                        if q.question_type == EvaluationQuestion.QuestionType.RATING:
                            resp.rating_value = int(val)
                        elif q.question_type == EvaluationQuestion.QuestionType.TEXT:
                            resp.text_value = val
                            
                        # Structural Anonymity: Response holds NO student foreign key, ever.
                        resp.save()
                        
                messages.success(request, f"Evaluation for {course.code} submitted successfully.")
                return redirect('evaluations:submission_confirmation', course_id=course.id)
                
            except Exception as e:
                logger.exception("Error saving course evaluation response for course %s", course.id)
                messages.error(request, "An error occurred while saving your responses. Please try again.")
        # If form is invalid, re-render form with errors below
    else:
        idempotency_key = uuid.uuid4().hex
        form = EvaluationForm(initial={'idempotency_key': idempotency_key}, course=course)
        
    return render(request, 'evaluations/evaluate.html', {
        'course': course,
        'form': form
    })


@role_required('STUDENT')
def submission_confirmation(request, course_id):
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    # Fallback to last session if none currently open, just to check submission record
    session = active_session or EvaluationSession.objects.order_by('-opens_at').first()
    
    if not session:
        return redirect('evaluations:student_dashboard')
        
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if SubmissionRecord exists
    has_submitted = SubmissionRecord.objects.filter(
        student=request.user,
        course=course,
        session=session
    ).exists()
    
    if not has_submitted:
        raise PermissionDenied("You have not submitted an evaluation for this course yet.")
        
    return render(request, 'evaluations/confirmation.html', {
        'course': course,
        'session': session
    })


@role_required('STUDENT')
def search_courses(request):
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    if not active_session:
        messages.error(request, "There is no active evaluation session at this time.")
        return redirect('evaluations:student_dashboard')
        
    query = request.GET.get('q', '').strip()
    results = []
    
    if query:
        # Search courses in the current semester
        results = Course.objects.filter(
            semester=active_session.title
        ).filter(
            Q(code__icontains=query) | Q(title__icontains=query)
        ).select_related('department')[:20]
        
    # Get student's existing registrations to avoid duplicates in UI
    registered_course_ids = set(
        CourseRegistration.objects.filter(
            student=request.user
        ).values_list('course_id', flat=True)
    )
    
    return render(request, 'evaluations/search_courses.html', {
        'query': query,
        'results': results,
        'registered_course_ids': registered_course_ids,
        'active_session': active_session
    })


@role_required('STUDENT')
def add_course_registration(request):
    if request.method != 'POST':
        return redirect('evaluations:search_courses')
        
    course_id = request.POST.get('course_id')
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    
    if not active_session:
        messages.error(request, "No active evaluation session.")
        return redirect('evaluations:student_dashboard')
        
    course = get_object_or_404(Course, pk=course_id, semester=active_session.title)
    
    # Try creating registration
    reg, created = CourseRegistration.objects.get_or_create(
        student=request.user,
        course=course,
        defaults={'is_manual_addition': True}
    )
    
    if created:
        messages.success(request, f"Successfully registered for {course.code}.")
    else:
        messages.info(request, f"You are already registered for {course.code}.")
        
    return redirect('evaluations:student_dashboard')


# ---------------------------------------------------------------------------
# Lecturer Dashboard & Reports Flow
# ---------------------------------------------------------------------------

@role_required('LECTURER')
def lecturer_dashboard(request):
    # Fetch all claimed courses for this lecturer
    claimed_courses = Course.objects.filter(
        lecturers=request.user
    ).select_related('department').order_by('code')
    
    active_session = EvaluationSession.objects.filter(is_open=True).order_by('-opens_at').first()
    # If no active session, look for the most recent one
    session = active_session or EvaluationSession.objects.order_by('-opens_at').first()
    
    courses_data = []
    for course in claimed_courses:
        if session:
            count = SubmissionRecord.response_count(course, session)
            enough, _ = SubmissionRecord.has_enough_responses_for_display(course, session)
        else:
            count = 0
            enough = False
            
        courses_data.append({
            'course': course,
            'response_count': count,
            'enough_responses': enough
        })
        
    return render(request, 'evaluations/lecturer_dashboard.html', {
        'courses_data': courses_data,
        'session': session
    })


@role_required('LECTURER')
def lecturer_course_summary(request, course_id):
    # Must be one of their claimed courses
    course = get_object_or_404(Course, pk=course_id, lecturers=request.user)
    
    # Get session, default to latest
    session_id = request.GET.get('session')
    if session_id:
        session = get_object_or_404(EvaluationSession, pk=session_id)
    else:
        session = EvaluationSession.objects.order_by('-opens_at').first()
        
    if not session:
        return render(request, 'evaluations/lecturer_summary.html', {
            'course': course,
            'session': None,
            'enough_responses': False
        })
        
    # Check threshold gate (n >= 10)
    enough_responses, count = SubmissionRecord.has_enough_responses_for_display(course, session)
    
    # Available sessions list for selector
    sessions = EvaluationSession.objects.order_by('-opens_at')
    
    if not enough_responses:
        # Stop and render empty summary details (results pending)
        return render(request, 'evaluations/lecturer_summary.html', {
            'course': course,
            'session': session,
            'sessions': sessions,
            'enough_responses': False,
            'response_count': count,
            'required_count': 10
        })
        
    # Aggregate rating values (mean)
    rating_questions = EvaluationQuestion.objects.filter(
        question_type=EvaluationQuestion.QuestionType.RATING
    ).order_by('order')
    
    ratings_data = []
    for q in rating_questions:
        mean_val = EvaluationResponse.objects.filter(
            course=course,
            session=session,
            question=q
        ).aggregate(mean=Avg('rating_value'))['mean']
        
        ratings_data.append({
            'question': q,
            'mean': round(mean_val, 2) if mean_val is not None else None
        })
        
    # Get shuffled text responses
    text_questions = EvaluationQuestion.objects.filter(
        question_type=EvaluationQuestion.QuestionType.TEXT
    ).order_by('order')
    
    text_data = []
    for q in text_questions:
        comments = list(
            EvaluationResponse.objects.filter(
                course=course,
                session=session,
                question=q
            ).exclude(
                text_value__isnull=True
            ).exclude(
                text_value__exact=''
            ).values_list('text_value', flat=True)
        )
        # Randomize comment order to protect anonymity (submission time correlation check)
        random.shuffle(comments)
        
        text_data.append({
            'question': q,
            'comments': comments
        })
        
    # Hard Rule check: Context contains no CustomUser, StudentProfile, or SubmissionRecord lists.
    return render(request, 'evaluations/lecturer_summary.html', {
        'course': course,
        'session': session,
        'sessions': sessions,
        'enough_responses': True,
        'response_count': count,
        'ratings_data': ratings_data,
        'text_data': text_data
    })


# ---------------------------------------------------------------------------
# Admin Dashboard & Session Management Flow
# ---------------------------------------------------------------------------

@role_required('ADMIN')
def admin_dashboard(request):
    total_students = CustomUser.objects.filter(role='STUDENT').count()
    total_lecturers = CustomUser.objects.filter(role='LECTURER').count()
    total_courses = Course.objects.count()
    
    active_session = EvaluationSession.objects.filter(is_open=True).first()
    
    return render(request, 'evaluations/admin_dashboard.html', {
        'total_students': total_students,
        'total_lecturers': total_lecturers,
        'total_courses': total_courses,
        'active_session': active_session
    })


@role_required('ADMIN')
def admin_sessions(request):
    sessions = EvaluationSession.objects.order_by('-opens_at')
    
    if request.method == 'POST':
        # Create a new session
        title = request.POST.get('title')
        opens_at = request.POST.get('opens_at')
        closes_at = request.POST.get('closes_at')
        
        if title and opens_at and closes_at:
            EvaluationSession.objects.create(
                title=title,
                opens_at=opens_at,
                closes_at=closes_at,
                is_open=False
            )
            messages.success(request, f"Session '{title}' created successfully.")
            return redirect('evaluations:admin_sessions')
        else:
            messages.error(request, "All fields are required to create a session.")
            
    return render(request, 'evaluations/admin_sessions.html', {
        'sessions': sessions
    })


@role_required('ADMIN')
def toggle_session(request, session_id):
    if request.method != 'POST':
        return redirect('evaluations:admin_sessions')
        
    session = get_object_or_404(EvaluationSession, pk=session_id)
    
    if session.is_open:
        try:
            session.is_open = False
            session.save()
            messages.success(request, f"Session '{session.title}' has been closed successfully.")
        except Exception as e:
            messages.error(request, f"Failed to close session: {e}")
    else:
        # Check if another session is open
        if EvaluationSession.objects.filter(is_open=True).exists():
            messages.error(request, "Another evaluation session is currently open. Close it first.")
        else:
            session.is_open = True
            session.save()
            messages.success(request, f"Session '{session.title}' is now open.")
            
    return redirect('evaluations:admin_sessions')


@role_required('ADMIN')
def admin_reports(request):
    # Available sessions
    sessions = EvaluationSession.objects.order_by('-opens_at')
    
    # Active or latest session
    session_id = request.GET.get('session')
    selected_session = None
    
    if EvaluationSession.objects.exists():
        if session_id and str(session_id).isdigit():
            selected_session = get_object_or_404(EvaluationSession, pk=int(session_id))
        else:
            selected_session = EvaluationSession.objects.order_by('-opens_at').first()
        
    if not selected_session:
        return render(request, 'evaluations/admin_reports.html', {
            'sessions': [],
            'selected_session': None,
            'courses_data': []
        })
        
    # Filters
    department_id = request.GET.get('department')
    lecturer_id = request.GET.get('lecturer')
    include_unclaimed = request.GET.get('include_unclaimed', 'true') == 'true'
    
    try:
        selected_dept_id = int(department_id) if department_id and str(department_id).isdigit() else None
    except (ValueError, TypeError):
        selected_dept_id = None
        
    try:
        selected_lecturer_id = int(lecturer_id) if lecturer_id and str(lecturer_id).isdigit() else None
    except (ValueError, TypeError):
        selected_lecturer_id = None
    
    # Base queryset of courses in the chosen semester, annotated with submission count in ONE query (LEFT JOIN)
    courses = Course.objects.filter(semester=selected_session.title).select_related('department').prefetch_related('lecturers')
    
    courses = courses.annotate(
        submission_count=Count(
            'submissionrecord',
            filter=Q(submissionrecord__session=selected_session)
        )
    )
    
    if selected_dept_id:
        courses = courses.filter(department_id=selected_dept_id)
        
    if selected_lecturer_id:
        courses = courses.filter(lecturers__id=selected_lecturer_id)
        
    if not include_unclaimed:
        courses = courses.filter(lecturers__isnull=False).distinct()
        
    # Fetch all mean ratings in one query (GROUP BY) for courses in the selected session
    avg_ratings = EvaluationResponse.objects.filter(
        session=selected_session,
        question__question_type=EvaluationQuestion.QuestionType.RATING
    ).values('course_id').annotate(mean_score=Avg('rating_value'))
    
    mean_scores_map = {}
    for item in avg_ratings:
        c_id = item['course_id']
        val = item['mean_score']
        if val is not None:
            mean_scores_map[c_id] = round(val, 2)
            
    # Build list containing aggregates
    courses_data = []
    for c in courses:
        count = c.submission_count
        enough = count >= MIN_RESPONSES_FOR_AGGREGATE_DISPLAY
        mean_score = mean_scores_map.get(c.id) if enough else None
        
        courses_data.append({
            'course': c,
            'lecturers': c.lecturers.all(),
            'response_count': count,
            'enough_responses': enough,
            'mean_score': mean_score
        })
        
    # Check for CSV Export request
    if request.GET.get('export') == 'csv':
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="LASU_Evaluation_Report_{selected_session.title.replace(" ", "_")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Course Code', 'Course Title', 'Department', 'Lecturer(s)', 'Responses', 'Mean Rating'])
        
        for item in courses_data:
            lecturer_names = ", ".join([l.get_full_name() or l.username for l in item['lecturers']])
            writer.writerow([
                item['course'].code,
                item['course'].title,
                item['course'].department.name,
                lecturer_names or 'Unclaimed',
                item['response_count'],
                item['mean_score'] if item['enough_responses'] else 'Pending (<10)'
            ])
        return response
        
    # Context data for dropdown selectors
    departments = Department.objects.all().order_by('name')
    lecturers = CustomUser.objects.filter(role='LECTURER').order_by('last_name')
    
    return render(request, 'evaluations/admin_reports.html', {
        'sessions': sessions,
        'selected_session': selected_session,
        'courses_data': courses_data,
        'departments': departments,
        'lecturers': lecturers,
        'selected_department_id': selected_dept_id,
        'selected_lecturer_id': selected_lecturer_id,
        'include_unclaimed': include_unclaimed
    })


# ---------------------------------------------------------------------------
# Anonymity Verification & Audit Endpoint (AYO-43)
# ---------------------------------------------------------------------------

@role_required('ADMIN')
def audit_anonymity(request):
    """Admin-gated read-only auditor endpoint for ethics board and advisors.
    Provides verifiable proof of schema-level anonymity constraint."""
    
    # 1. Inspect Schema Fields (Graph Introspection)
    from django.apps import apps
    EvaluationResponseModel = apps.get_model('evaluations', 'EvaluationResponse')
    SubmissionRecordModel = apps.get_model('evaluations', 'SubmissionRecord')
    
    response_fields = [f.name for f in EvaluationResponseModel._meta.get_fields()]
    submission_fields = [f.name for f in SubmissionRecordModel._meta.get_fields()]
    
    # Verify that no field in EvaluationResponse points to student or SubmissionRecord
    unwanted_links = []
    for field in EvaluationResponseModel._meta.get_fields():
        if field.is_relation and field.related_model:
            model_name = field.related_model.__name__
            if model_name in ['CustomUser', 'StudentProfile', 'SubmissionRecord']:
                unwanted_links.append(f"{field.name} -> {model_name}")
                
    schema_safe = len(unwanted_links) == 0
    
    # 2. Run Test Suite On-Demand
    import unittest
    from .tests.test_anonymity_proof import AnonymityProofTests
    
    suite = unittest.TestLoader().loadTestsFromTestCase(AnonymityProofTests)
    from io import StringIO
    stream = StringIO()
    runner = unittest.TextTestRunner(stream=stream, resultclass=unittest.TextTestResult)
    
    # Run proof test suite
    result = runner.run(suite)
    test_log = stream.getvalue()
    tests_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    tests_passed = (failures == 0 and errors == 0)
    
    # 3. View AST source code audit summary for views.py
    import os
    import ast
    
    views_path = __file__.replace('.pyc', '.py')
    violations = []
    
    try:
        with open(views_path, 'r', encoding='utf-8') as f:
            source = f.read()
            tree = ast.parse(source)
            
        # Analyze AST to make sure lecturer_course_summary and admin_reports
        # do not mix references to EvaluationResponse and student info.
        class AnonymityAuditVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_function = None
                self.references = {}
                
            def visit_FunctionDef(self, node):
                self.current_function = node.name
                self.references[node.name] = set()
                self.generic_visit(node)
                self.current_function = None
                
            def visit_Name(self, node):
                if self.current_function:
                    if node.id in ['SubmissionRecord', 'EvaluationResponse', 'CustomUser', 'StudentProfile']:
                        self.references[self.current_function].add(node.id)
                        
        visitor = AnonymityAuditVisitor()
        visitor.visit(tree)
        
        # Check functions that aggregate content: they must NOT reference student identity models
        sensitive_functions = ['lecturer_course_summary', 'admin_reports']
        for func in sensitive_functions:
            refs = visitor.references.get(func, set())
            # Note: SubmissionRecord is allowed ONLY for checking response counts/display threshold.
            # CustomUser and StudentProfile represent direct identification.
            if 'CustomUser' in refs or 'StudentProfile' in refs:
                violations.append(f"Function '{func}' references student identity models: {refs}")
    except Exception as e:
        violations.append(f"AST Audit failed to parse views: {e}")
        
    # Generate downloadable audit packet if requested
    if request.GET.get('packet') == 'markdown':
        audit_packet = f"""# LASU Course Evaluation System — Anonymity Audit Report
Generated at: {request.GET.get('timestamp', 'Current Session')}

## 1. Schema-Level Separation Check
- **EvaluationResponse Fields:** {', '.join(response_fields)}
- **SubmissionRecord Fields:** {', '.join(submission_fields)}
- **Safety Status:** {"SECURE" if schema_safe else "REGRESSED"}
{f"- **Violations Found:** {unwanted_links}" if not schema_safe else "- **Verification:** No join path exists between feedback and user identity."}

## 2. Automated Proof Tests
- **Proof Tests Run:** {tests_run}
- **Status:** {"PASSED" if tests_passed else "FAILED"}
- **Errors/Failures:** {errors + failures}
- **Log Excerpt:**
```
{test_log}
```

## 3. Query Inventory & AST View Audit
- **Code Audit Violations:** {violations or 'None'}
- **Verification:** verified that aggregator queries do not reference student profile models.
"""
        response = HttpResponse(audit_packet, content_type='text/markdown')
        response['Content-Disposition'] = 'attachment; filename="anonymity_audit_packet.md"'
        return response
        
    return render(request, 'evaluations/audit_anonymity.html', {
        'schema_safe': schema_safe,
        'response_fields': response_fields,
        'submission_fields': submission_fields,
        'unwanted_links': unwanted_links,
        'tests_passed': tests_passed,
        'tests_run': tests_run,
        'failures_count': failures + errors,
        'test_log': test_log,
        'ast_violations': violations
    })
