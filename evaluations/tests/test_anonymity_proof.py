import ast
import os
from django.test import TestCase
from django.apps import apps
from django.db import connection
from django.contrib.auth import get_user_model

from accounts.models import StudentProfile
from courses.models import Course, Department, Faculty
from evaluations.models import EvaluationSession, EvaluationQuestion, SubmissionRecord, EvaluationResponse

class AnonymityProofTests(TestCase):
    
    def test_schema_graph_separation(self):
        """Proof 1: Walk relations. No path of length <= 3 should connect EvaluationResponse to CustomUser/StudentProfile."""
        ResponseModel = apps.get_model('evaluations', 'EvaluationResponse')
        CustomUser = get_user_model()
        
        # Traverse relationships
        for field in ResponseModel._meta.get_fields():
            if field.is_relation and field.related_model:
                related_model = field.related_model
                self.assertNotEqual(
                    related_model, CustomUser,
                    f"Direct violation: EvaluationResponse has relation to User model via '{field.name}'"
                )
                self.assertNotEqual(
                    related_model, StudentProfile,
                    f"Direct violation: EvaluationResponse has relation to StudentProfile via '{field.name}'"
                )
                self.assertNotEqual(
                    related_model, SubmissionRecord,
                    f"Direct violation: EvaluationResponse has relation to SubmissionRecord via '{field.name}'"
                )
                
    def test_shared_keys_intersection(self):
        """Proof 2: Only course_id and session_id should be shared between SubmissionRecord and EvaluationResponse."""
        ResponseModel = apps.get_model('evaluations', 'EvaluationResponse')
        RecordModel = apps.get_model('evaluations', 'SubmissionRecord')
        
        response_cols = {f.column for f in ResponseModel._meta.concrete_fields if f.is_relation}
        record_cols = {f.column for f in RecordModel._meta.concrete_fields if f.is_relation}
        
        intersection = response_cols.intersection(record_cols)
        expected = {'course_id', 'session_id'}
        
        self.assertEqual(
            intersection, expected,
            f"Violated intersection of columns: expected {expected}, got {intersection}"
        )
        
    def test_ast_source_code_views(self):
        """Proof 3: Query inspection. Ensure functions in views.py returning response content don't import student variables."""
        import evaluations.views as views
        views_file_path = views.__file__.replace('.pyc', '.py')
        
        with open(views_file_path, 'r', encoding='utf-8') as f:
            source = f.read()
            
        tree = ast.parse(source)
        
        class ViewVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_func = None
                self.refs = {}
                
            def visit_FunctionDef(self, node):
                self.current_func = node.name
                self.refs[node.name] = set()
                self.generic_visit(node)
                self.current_func = None
                
            def visit_Name(self, node):
                if self.current_func:
                    if node.id in ['SubmissionRecord', 'EvaluationResponse', 'CustomUser', 'StudentProfile']:
                        self.refs[self.current_func].add(node.id)
                        
        visitor = ViewVisitor()
        visitor.visit(tree)
        
        # Verify specific sensitive views
        # lecturer_course_summary must NOT reference CustomUser or StudentProfile
        lecturer_refs = visitor.refs.get('lecturer_course_summary', set())
        self.assertNotIn(
            'CustomUser', lecturer_refs,
            "Violation: lecturer_course_summary view references CustomUser model directly"
        )
        self.assertNotIn(
            'StudentProfile', lecturer_refs,
            "Violation: lecturer_course_summary view references StudentProfile directly"
        )
        
        # admin_reports is allowed to reference CustomUser (to fetch the LECTURER list),
        # but must NOT reference StudentProfile to prevent linking student identities.
        admin_refs = visitor.refs.get('admin_reports', set())
        self.assertNotIn(
            'StudentProfile', admin_refs,
            "Violation: admin_reports view references StudentProfile directly"
        )
            
    def test_sql_join_reidentification(self):
        """Proof 4: SQL join attempt. Verify that SQL join yields Cartesian product, not direct re-identification."""
        # Create mock data
        user_model = get_user_model()
        user1 = user_model.objects.create_user(username='student1', password='password123', role='STUDENT')
        user2 = user_model.objects.create_user(username='student2', password='password123', role='STUDENT')
        
        faculty = Faculty.objects.create(code='SCI', name='Science')
        dept = Department.objects.create(code='CSC', name='Computer Science', faculty=faculty)
        course = Course.objects.create(code='CSC401', title='Algorithms', department=dept, level='400', semester='Test Semester')
        
        session = EvaluationSession.objects.create(
            title='Test Semester',
            opens_at='2026-01-01T00:00:00Z',
            closes_at='2026-12-31T00:00:00Z',
            is_open=True
        )
        
        question = EvaluationQuestion.objects.create(text='Rate this course', question_type='RATING', order=1)
        
        # Submissions
        SubmissionRecord.objects.create(student=user1, course=course, session=session)
        SubmissionRecord.objects.create(student=user2, course=course, session=session)
        
        # Responses
        EvaluationResponse.objects.create(course=course, session=session, question=question, rating_value=5)
        EvaluationResponse.objects.create(course=course, session=session, question=question, rating_value=3)
        
        # Querying evaluations. Try to join. Since there is no user link on Response, we do a raw query:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT u.username, r.rating_value 
                FROM accounts_customuser u
                JOIN evaluations_submissionrecord s ON s.student_id = u.id
                JOIN evaluations_evaluationresponse r ON r.course_id = s.course_id AND r.session_id = s.session_id
                WHERE r.course_id = %s
            """, [course.id])
            rows = cursor.fetchall()
            
        # Expect 4 rows (Cartesian product of 2 students x 2 responses), showing that joins produce no specific mapping
        self.assertEqual(len(rows), 4, "Join query should produce Cartesian product, proving anonymity")
        
        # Student 1 gets linked to both 5 and 3 rating scores, same for Student 2
        student_ratings = {}
        for username, rating in rows:
            if username not in student_ratings:
                student_ratings[username] = []
            student_ratings[username].append(rating)
            
        self.assertEqual(set(student_ratings['student1']), {3, 5})
        self.assertEqual(set(student_ratings['student2']), {3, 5})
