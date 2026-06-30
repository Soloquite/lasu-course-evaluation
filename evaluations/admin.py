from django.contrib import admin

from .models import (
    EvaluationQuestion,
    EvaluationResponse,
    EvaluationSession,
    SubmissionRecord,
)


@admin.register(EvaluationSession)
class EvaluationSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "is_open", "opens_at", "closes_at")


@admin.register(EvaluationQuestion)
class EvaluationQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "question_type", "order")


@admin.register(SubmissionRecord)
class SubmissionRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "session", "submitted_at")
    # Deliberately read-only-feeling: this table proves WHO submitted,
    # never WHAT they said. Keeping it visually separate from
    # EvaluationResponse in the admin reinforces that boundary.


@admin.register(EvaluationResponse)
class EvaluationResponseAdmin(admin.ModelAdmin):
    list_display = ("course", "session", "question", "rating_value", "submitted_at")
    list_filter = ("course", "session", "question")
    # No student field exists here to display - that's the point.
