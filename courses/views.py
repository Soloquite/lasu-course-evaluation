from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required

from accounts.permissions import role_required
from .models import Course, CourseLecturer

@role_required('LECTURER')
def claim_courses(request):
    lecturer_profile = request.user.lecturer_profile
    dept = lecturer_profile.department
    if request.method == 'POST':
        course_ids = request.POST.getlist('course_ids')
        if not course_ids:
            messages.warning(request, "Please select at least one course to claim.")
            return redirect('courses:claim_courses')
            
        # Filter course IDs that actually belong to the lecturer's department to prevent cross-department claiming
        try:
            cleaned_ids = [int(cid) for cid in course_ids if str(cid).strip().isdigit()]
            valid_course_ids = set(
                Course.objects.filter(
                    id__in=cleaned_ids,
                    department=dept
                ).values_list('id', flat=True)
            )
        except ValueError:
            messages.error(request, "Invalid course selection.")
            return redirect('courses:claim_courses')

        if not valid_course_ids:
            messages.warning(request, "No valid courses selected for claiming.")
            return redirect('courses:claim_courses')

        with transaction.atomic():
            # Create claims
            claims = [
                CourseLecturer(lecturer=request.user, course_id=cid)
                for cid in valid_course_ids
            ]
            CourseLecturer.objects.bulk_create(claims, ignore_conflicts=True)
            
        messages.success(request, f"Successfully claimed {len(valid_course_ids)} courses.")
        return redirect('evaluations:lecturer_dashboard')
        
    # Get courses in home department
    courses = Course.objects.filter(department=dept).order_by('code')
    
    # Get courses already claimed by this lecturer
    claimed_course_ids = set(
        CourseLecturer.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
    )
    
    # Build list of courses with claimed status
    courses_data = []
    for c in courses:
        courses_data.append({
            'course': c,
            'is_claimed': c.id in claimed_course_ids,
            'claim_count': CourseLecturer.objects.filter(course=c).count()
        })
        
    return render(request, 'courses/claim_courses.html', {
        'courses_data': courses_data,
        'department': dept
    })
