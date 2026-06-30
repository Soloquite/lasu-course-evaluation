from django.conf import settings
from django.db import models


class Faculty(models.Model):
    """
    Top of the CSV-driven hierarchy. Populated from the one-time CSV
    import (no LASU central system integration — see PRD section 5.2).
    """

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=150)

    class Meta:
        verbose_name_plural = "Faculties"

    def __str__(self):
        return self.name


class Department(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=150)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")

    def __str__(self):
        return f"{self.name} ({self.faculty.code})"


class Course(models.Model):
    """
    Populated from the CSV import. The CSV deliberately never names a
    lecturer, so `lecturers` starts empty for every course and fills in
    only as lecturers self-claim courses at signup (see CourseLecturer).
    """

    LEVEL_CHOICES = [(str(level), str(level)) for level in (100, 200, 300, 400, 500)]

    code = models.CharField(max_length=15)
    title = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="courses")
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    semester = models.CharField(max_length=50, help_text="e.g. 2025/2026 First Semester")

    lecturers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CourseLecturer",
        limit_choices_to={"role": "LECTURER"},
        related_name="courses_taught",
        blank=True,
    )

    class Meta:
        # Same course code could in principle repeat in a future semester's
        # CSV (v1 only ever imports one semester, but this keeps the
        # constraint correct rather than coincidentally correct).
        # The same course code (e.g. ACC 212) legitimately appears in many
        # departments across LASU — 875 codes do this in the real CSV.
        # Uniqueness is therefore per-department, not globally per-code.
        unique_together = ("code", "department", "semester")

    def __str__(self):
        return f"{self.code} - {self.title}"


class CourseLecturer(models.Model):
    """
    Through-model for a lecturer claiming a course at signup.

    Multiple different lecturers can claim the same course (co-taught
    courses, per your decision), but the same lecturer can't claim the
    same course twice. A course with zero rows here is "unclaimed" — its
    evaluation responses still collect (see evaluations app) and are
    visible only in the admin's reporting, never on any lecturer
    dashboard, until a CourseLecturer row links it to someone.
    """

    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "LECTURER"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lecturer", "course")

    def __str__(self):
        return f"{self.lecturer} teaches {self.course}"


class CourseRegistration(models.Model):
    """
    Records which student is taking which course.

    Auto-created at signup for every course matching the student's own
    (department, level) from the CSV-populated list for the active
    semester. `is_manual_addition` distinguishes that default set from
    courses the student deliberately searched for and added from another
    department/faculty.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "STUDENT"},
        related_name="course_registrations",
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="registrations")
    is_manual_addition = models.BooleanField(
        default=False,
        help_text="True if the student added this course themselves rather than "
        "it being auto-populated from their home department/level at signup.",
    )

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student} -> {self.course}"
