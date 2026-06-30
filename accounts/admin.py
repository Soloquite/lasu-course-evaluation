from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, LecturerProfile, StudentProfile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_staff")
    fieldsets = UserAdmin.fieldsets + ((
        "Role",
        {"fields": ("role",)},
    ),)


admin.site.register(StudentProfile)
admin.site.register(LecturerProfile)
