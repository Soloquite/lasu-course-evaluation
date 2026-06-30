from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from courses.models import Course, CourseRegistration, Department
from .forms import LecturerSignupForm, LoginForm, StudentSignupForm
from .models import CustomUser, LecturerProfile, StudentProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dashboard_url(user):
    """Return the dashboard URL for the given user's role."""
    role_map = {
        'STUDENT': 'evaluations:student_dashboard',
        'LECTURER': 'evaluations:lecturer_dashboard',
        'ADMIN': 'evaluations:admin_dashboard',
    }
    return reverse(role_map.get(user.role, 'accounts:login'))


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

def landing_page(request):
    """Root view: redirects authenticated users to their dashboard."""
    if request.user.is_authenticated:
        return redirect(_dashboard_url(request.user))
    return render(request, 'landing.html')


# ---------------------------------------------------------------------------
# Role selection (signup gateway)
# ---------------------------------------------------------------------------

def role_select(request):
    if request.user.is_authenticated:
        return redirect(_dashboard_url(request.user))
    return render(request, 'accounts/role_select.html')


# ---------------------------------------------------------------------------
# Student signup
# ---------------------------------------------------------------------------

def student_signup(request):
    if request.method == 'POST':
        form = StudentSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = CustomUser(
                    username=form.cleaned_data['matric_number'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=form.cleaned_data.get('email', ''),
                    role='STUDENT',
                )
                user.set_password(form.cleaned_data['password1'])
                user.save()

                StudentProfile.objects.create(
                    user=user,
                    matric_number=form.cleaned_data['matric_number'],
                    department=form.cleaned_data['department'],
                    level=form.cleaned_data['level'],
                )

                # Auto-register for courses matching department + level
                dept = form.cleaned_data['department']
                level = form.cleaned_data['level']
                courses = Course.objects.filter(department=dept, level=level)
                registrations = [
                    CourseRegistration(student=user, course=c, is_manual_addition=False)
                    for c in courses
                ]
                CourseRegistration.objects.bulk_create(registrations, ignore_conflicts=True)

            login(request, user)
            messages.success(
                request,
                f'Welcome, {user.first_name}! Your account has been created.',
            )
            return redirect('evaluations:student_dashboard')
    else:
        form = StudentSignupForm()

    return render(request, 'accounts/signup_student.html', {'form': form})


# ---------------------------------------------------------------------------
# Lecturer signup
# ---------------------------------------------------------------------------

def lecturer_signup(request):
    if request.method == 'POST':
        form = LecturerSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                lecturer_id = form.cleaned_data.get('lecturer_id', '').strip()
                work_email = form.cleaned_data.get('work_email', '').strip()
                username = lecturer_id or work_email

                user = CustomUser(
                    username=username,
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    email=work_email,
                    role='LECTURER',
                )
                user.set_password(form.cleaned_data['password1'])
                user.save()

                LecturerProfile.objects.create(
                    user=user,
                    lecturer_id=lecturer_id or username,
                    department=form.cleaned_data['department'],
                )

            login(request, user)
            messages.success(
                request,
                f'Welcome, {user.first_name}! Your lecturer account has been created.',
            )
            return redirect('courses:claim_courses')
    else:
        form = LecturerSignupForm()

    return render(request, 'accounts/signup_lecturer.html', {'form': form})


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name}!')
                return redirect(_dashboard_url(user))
            else:
                return render(request, 'accounts/login.html', {
                    'form': form,
                    'error': 'Invalid username or password. Please try again.',
                })
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('accounts:login')


# ---------------------------------------------------------------------------
# AJAX: departments by faculty
# ---------------------------------------------------------------------------

def get_departments(request):
    """Returns departments for a given faculty_id as JSON (used by signup form JS)."""
    faculty_id = request.GET.get('faculty_id')
    if not faculty_id:
        return JsonResponse({'departments': []})
    departments = Department.objects.filter(faculty_id=faculty_id).values('id', 'code', 'name')
    return JsonResponse({'departments': list(departments)})
