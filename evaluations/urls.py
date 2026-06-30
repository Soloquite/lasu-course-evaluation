from django.urls import path
from . import views

app_name = 'evaluations'

urlpatterns = [
    # Student Views
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/evaluate/<int:course_id>/', views.evaluate_course, name='evaluate_course'),
    path('student/evaluate/<int:course_id>/done/', views.submission_confirmation, name='submission_confirmation'),
    path('student/courses/search/', views.search_courses, name='search_courses'),
    path('student/courses/add/', views.add_course_registration, name='add_course_registration'),
    
    # Lecturer Views
    path('lecturer/dashboard/', views.lecturer_dashboard, name='lecturer_dashboard'),
    path('lecturer/course/<int:course_id>/', views.lecturer_course_summary, name='lecturer_course_summary'),
    
    # Admin Views
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/sessions/', views.admin_sessions, name='admin_sessions'),
    path('admin-dashboard/sessions/<int:session_id>/toggle/', views.toggle_session, name='toggle_session'),
    path('admin-dashboard/reports/', views.admin_reports, name='admin_reports'),
    
    # Audit Views
    path('admin-dashboard/audit/anonymity/', views.audit_anonymity, name='audit_anonymity'),
]
