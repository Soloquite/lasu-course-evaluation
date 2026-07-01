from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from courses.models import Department, Faculty
from .models import CustomUser, LecturerProfile, StudentProfile


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Matric number or Lecturer ID',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
        })
    )


# ---------------------------------------------------------------------------
# Student Signup
# ---------------------------------------------------------------------------

class StudentSignupForm(forms.Form):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name',
        }),
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name',
        }),
    )
    matric_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 190401001',
        }),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional email address',
        }),
    )
    faculty = forms.ModelChoiceField(
        queryset=Faculty.objects.all(),
        empty_label='Select Faculty',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_faculty',
        }),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        empty_label='Select Department',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_department',
        }),
    )
    level = forms.ChoiceField(
        choices=[('', 'Select Level')] + [(str(l), str(l)) for l in (100, 200, 300, 400, 500)],
        widget=forms.Select(attrs={
            'class': 'form-control',
        }),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a password',
        }),
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate department queryset if faculty was already selected
        if self.data.get('faculty'):
            try:
                faculty_id = int(self.data['faculty'])
                self.fields['department'].queryset = Department.objects.filter(
                    faculty_id=faculty_id
                )
            except (ValueError, TypeError):
                pass

    # -- Field-level validation --

    def clean_matric_number(self):
        value = self.cleaned_data['matric_number']
        if StudentProfile.objects.filter(matric_number=value).exists():
            raise ValidationError('A student with this matric number already exists.')
        if CustomUser.objects.filter(username=value).exists():
            raise ValidationError('This matric number is already registered.')
        return value

    def clean_department(self):
        department = self.cleaned_data.get('department')
        faculty = self.cleaned_data.get('faculty')
        if department and faculty and department.faculty != faculty:
            raise ValidationError('This department does not belong to the selected faculty.')
        return department

    # -- Cross-field validation --

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')

        if password1 and password2:
            if password1 != password2:
                self.add_error('password2', 'Passwords do not match.')
            else:
                try:
                    validate_password(password1)
                except ValidationError as e:
                    self.add_error('password1', e)

        return cleaned


# ---------------------------------------------------------------------------
# Lecturer Signup
# ---------------------------------------------------------------------------

class LecturerSignupForm(forms.Form):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name',
        }),
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name',
        }),
    )
    lecturer_id = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. LASU/LEC/001',
        }),
        help_text='Provide either Lecturer ID or work email.',
    )
    work_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'university.email@lasu.edu.ng',
        }),
        help_text='Provide either Lecturer ID or work email.',
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        empty_label='Select Department',
        widget=forms.Select(attrs={
            'class': 'form-control',
        }),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a password',
        }),
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
        }),
    )

    # -- Field-level validation --

    def clean_lecturer_id(self):
        value = self.cleaned_data.get('lecturer_id', '').strip()
        if value and LecturerProfile.objects.filter(lecturer_id=value).exists():
            raise ValidationError('A lecturer with this ID already exists.')
        return value

    def clean_work_email(self):
        value = self.cleaned_data.get('work_email', '').strip()
        if value and CustomUser.objects.filter(email=value).exists():
            raise ValidationError('This email address is already registered.')
        return value

    # -- Cross-field validation --

    def clean(self):
        cleaned = super().clean()
        lecturer_id = cleaned.get('lecturer_id', '').strip()
        work_email = cleaned.get('work_email', '').strip()

        if not lecturer_id and not work_email:
            raise ValidationError(
                'Please provide at least one identifier: Lecturer ID or work email.'
            )

        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')

        if password1 and password2:
            if password1 != password2:
                self.add_error('password2', 'Passwords do not match.')
            else:
                try:
                    validate_password(password1)
                except ValidationError as e:
                    self.add_error('password1', e)

        return cleaned
