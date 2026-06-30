import uuid

from django.conf import settings
from django.db import models

from courses.models import Course

from .constants import MIN_RESPONSES_FOR_AGGREGATE_DISPLAY


class EvaluationSession(models.Model):
    """
    An evaluation window opened by an administrator. Covers all courses
    at once - admins open and close it centrally rather than leaving
    evaluation to individual departmental discretion.
    """

    title = models.CharField(max_length=100, help_text="e.g. 2025/2026 First Semester")
    is_open = models.BooleanField(default=False)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()

    def __str__(self):
        return self.title


class EvaluationQuestion(models.Model):
    """A reusable question shown on every course's evaluation form."""

    class QuestionType(models.TextChoices):
        RATING = "RATING", "Rating (1-5)"
        TEXT = "TEXT", "Open-ended text"

    CATEGORY_CHOICES = [
        ('CORE', 'Core Campus-Wide'),
        ('STEM', 'Science & STEM'),
        ('LANG', 'World Languages & Culture'),
        ('BUS', 'Business & Professional Programs'),
        ('HUM', 'Humanities'),
        ('ART', 'Studio Art & Design'),
        ('MUSIC_LESSON', 'Music Performance & Private Lessons'),
        ('MUSIC_ENSEMBLE', 'Large Music Ensembles'),
        ('THEATER', 'Theater, Dance & Performance')
    ]

    text = models.CharField(max_length=300)
    question_type = models.CharField(max_length=10, choices=QuestionType.choices)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='CORE')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text


class SubmissionRecord(models.Model):
    """
    Tracks WHO has submitted an evaluation for WHICH course/session - and
    nothing more. Enforces "one submission per student per course per
    session" and nothing else; stores no feedback content whatsoever.

    idempotency_key is generated when the evaluation form is first
    rendered and resubmitted with the form. If a network retry or
    double-click sends the same key twice, the view treats it as the
    same successful submission and returns the original confirmation,
    instead of erroring on the unique_together constraint below.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={"role": "STUDENT"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    session = models.ForeignKey(EvaluationSession, on_delete=models.CASCADE)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course", "session")

    def __str__(self):
        return f"Submission logged: {self.course} / {self.session}"

    @classmethod
    def response_count(cls, course, session):
        """Safe to expose anywhere - it's a count, never the content."""
        return cls.objects.filter(course=course, session=session).count()

    @classmethod
    def has_enough_responses_for_display(cls, course, session, threshold=None):
        threshold = threshold or MIN_RESPONSES_FOR_AGGREGATE_DISPLAY
        count = cls.response_count(course, session)
        return count >= threshold, count


class EvaluationResponse(models.Model):
    """
    Stores actual feedback content. Deliberately has NO foreign key to a
    student or any user account - this is the structural anonymity
    enforcement that is this project's core technical contribution. The
    only record that a submission happened lives in SubmissionRecord
    above, which has no foreign key pointing into this table.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="responses")
    session = models.ForeignKey(EvaluationSession, on_delete=models.CASCADE)
    question = models.ForeignKey(EvaluationQuestion, on_delete=models.CASCADE)
    rating_value = models.PositiveSmallIntegerField(null=True, blank=True)
    text_value = models.TextField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Response to '{self.question}' for {self.course}"
