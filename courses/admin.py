from django.contrib import admin

from .models import Course, CourseLecturer, CourseRegistration, Department, Faculty


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "faculty")
    list_filter = ("faculty",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "department", "level", "semester")
    list_filter = ("department", "level", "semester")
    search_fields = ("code", "title")


@admin.register(CourseLecturer)
class CourseLecturerAdmin(admin.ModelAdmin):
    list_display = ("lecturer", "course", "claimed_at")


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "is_manual_addition")
    list_filter = ("is_manual_addition", "course")
