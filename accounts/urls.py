from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.role_select, name='role_select'),
    path('signup/student/', views.student_signup, name='student_signup'),
    path('signup/lecturer/', views.lecturer_signup, name='lecturer_signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/departments/', views.get_departments, name='get_departments'),
]
