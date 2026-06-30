from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    path('claim/', views.claim_courses, name='claim_courses'),
]
