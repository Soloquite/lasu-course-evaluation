from django import forms
from .models import EvaluationQuestion

AGREEMENT_CHOICES = [
    ('1', '1 — Strongly Disagree'),
    ('2', '2 — Disagree'),
    ('3', '3 — Neutral'),
    ('4', '4 — Agree'),
    ('5', '5 — Strongly Agree'),
]

FREQUENCY_MOTIVATE_CHOICES = [
    ('1', '1 — Not at all'),
    ('2', '2 — Slightly'),
    ('3', '3 — Moderately'),
    ('4', '4 — Very much'),
    ('5', '5 — Extremely'),
]

LIKELIHOOD_RECOMMEND_CHOICES = [
    ('1', '1 — Extremely Unlikely'),
    ('2', '2 — Unlikely'),
    ('3', '3 — Neutral'),
    ('4', '4 — Likely'),
    ('5', '5 — Extremely Likely'),
]

WORKLOAD_TIME_CHOICES = [
    ('1', '1 — Much less time'),
    ('2', '2 — Less time'),
    ('3', '3 — About the same'),
    ('4', '4 — More time'),
    ('5', '5 — Much more time'),
]

WORKLOAD_WEEKLY_HOURS_CHOICES = [
    ('1', '1 — Less than 3 hours'),
    ('2', '2 — 3-6 hours'),
    ('3', '3 — 7-10 hours'),
    ('4', '4 — 11-14 hours'),
    ('5', '5 — 15+ hours'),
]

def get_choices_for_question(order):
    if order in [5, 6]:
        return FREQUENCY_MOTIVATE_CHOICES
    elif order == 7:
        return LIKELIHOOD_RECOMMEND_CHOICES
    elif order == 8:
        return WORKLOAD_TIME_CHOICES
    elif order == 9:
        return WORKLOAD_WEEKLY_HOURS_CHOICES
    else:
        return AGREEMENT_CHOICES


class EvaluationForm(forms.Form):
    idempotency_key = forms.CharField(widget=forms.HiddenInput(), required=True)

    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
        if course:
            from .views import get_categories_for_course
            categories = get_categories_for_course(course)
            questions = EvaluationQuestion.objects.filter(category__in=categories).order_by('order')
        else:
            questions = EvaluationQuestion.objects.all().order_by('order')
        for q in questions:
            field_name = f'question_{q.id}'
            if q.question_type == EvaluationQuestion.QuestionType.RATING:
                choices = get_choices_for_question(q.order)
                self.fields[field_name] = forms.ChoiceField(
                    choices=choices,
                    widget=forms.RadioSelect(attrs={'class': 'rating-input'}),
                    label=q.text,
                    required=True
                )
            elif q.question_type == EvaluationQuestion.QuestionType.TEXT:
                self.fields[field_name] = forms.CharField(
                    widget=forms.Textarea(attrs={
                        'class': 'form-control',
                        'rows': 4,
                        'placeholder': 'Type your feedback here (optional)...'
                    }),
                    label=q.text,
                    required=False
                )
