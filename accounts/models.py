from django.contrib.auth.models import AbstractUser
from django.db import models

from courses.models import Department


class CustomUser(AbstractUser):
    """
    Custom user model with a role field.

    Best-practice note: Django strongly recommends defining a custom user
    model at the START of a project, even if it looks identical to the
    default User model at first. Swapping to a custom user model after the
    first migration has already been applied is painful, because every
    other model's ForeignKey to User would need a data migration too.
    Setting it up now means we never have to deal with that.
    """

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        LECTURER = "LECTURER", "Lecturer"
        ADMIN = "ADMIN", "Administrator"

    role = models.CharField(max_length=20, choices=Role.choices)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class StudentProfile(models.Model):
    """
    Extra fields specific to students only.

    department is a real ForeignKey (not free text) since it's populated
    from the CSV-driven Department table at signup, and is what drives
    auto-populating the student's default course list.
    """

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="student_profile"
    )
    matric_number = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="students"
    )
    level = models.CharField(
        max_length=10,
        choices=[(str(level), str(level)) for level in (100, 200, 300, 400, 500)],
    )

    def __str__(self):
        return f"{self.matric_number} - {self.user.get_full_name()}"


class LecturerProfile(models.Model):
    """
    Extra fields specific to lecturers only.

    department here is the lecturer's home department, used at signup to
    browse which courses are available to claim. It is NOT the same thing
    as which courses they actually teach — that link lives in
    courses.CourseLecturer, created when they claim a specific course.
    """

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="lecturer_profile"
    )
    lecturer_id = models.CharField(max_length=150, unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="lecturers"
    )

    def __str__(self):
        return f"{self.lecturer_id} - {self.user.get_full_name()}"
