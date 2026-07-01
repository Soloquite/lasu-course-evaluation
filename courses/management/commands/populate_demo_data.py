import os
import random
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q

from accounts.models import StudentProfile
from courses.models import Course, Department, CourseRegistration
from evaluations.models import EvaluationSession, EvaluationQuestion, SubmissionRecord, EvaluationResponse

CustomUser = get_user_model()

COMMENTS_HELPFUL = [
    "The instructor was highly engaging and explained complex derivations clearly.",
    "Very responsive during office hours. Assisted me with debugging my code/experiments.",
    "The practical exercises and homework helped solidify the course lectures.",
    "Gave very constructive feedback on our project design documents.",
    "Always willing to re-explain difficult concepts when asked in class.",
    "Well-structured lecture slides and excellent reading recommendations.",
    "The step-by-step problem-solving sessions in class were extremely helpful.",
    "Encouraged active participation and critical thinking during discussions.",
]

COMMENTS_IMPROVE = [
    "The grading on assignments was a bit slow; quicker feedback would help.",
    "The mid-semester project felt slightly rushed. More time for planning would be great.",
    "Providing recorded lectures or extra online resources would be highly beneficial.",
    "Some of the slides were too dense. Simpler bullet points would be easier to follow.",
    "The textbook was expensive and we didn't use it much. PDFs would be better.",
    "I suggest incorporating more real-world practical examples in the lectures.",
    "The class pacing could be adjusted; we spent too much time on basic topics initially.",
]

DEPARTMENTS_CONFIG = [
    {
        'code': 'IRHRM',
        'name': 'INDUSTRIAL RELATIONS & HUMAN RESOURCES MANAGEMENT',
        'matric_prefix': '230831',  # 2023, 300 level
        'level': '300',
        'num_students': 40,
        'num_submitting': 25
    },
    {
        'code': 'CE123',
        'name': 'CIVIL ENGINEERING',
        'matric_prefix': '250241',  # 2025, 100 level
        'level': '100',
        'num_students': 70,
        'num_submitting': 40
    },
    {
        'code': 'HIS',
        'name': 'HISTORY AND INTERNATIONAL STUDIES',
        'matric_prefix': '240126',  # 2024, 200 level
        'level': '200',
        'num_students': 35,
        'num_submitting': 20
    },
    {
        'code': 'MC',
        'name': 'MASS COMMUNICATION',
        'matric_prefix': '230910',  # 2023, 300 level
        'level': '300',
        'num_students': 45,
        'num_submitting': 25
    },
    {
        'code': 'A110',
        'name': 'ACCOUNTING',
        'matric_prefix': '240811',  # 2024, 200 level
        'level': '200',
        'num_students': 30,
        'num_submitting': 18
    },
    {
        'code': 'P68',
        'name': 'PHYSICS',
        'matric_prefix': '250571',  # 2025, 100 level
        'level': '100',
        'num_students': 25,
        'num_submitting': 12
    }
]

class Command(BaseCommand):
    help = "Generates mock students and evaluation responses for UAT testing and demo purposes"

    def handle(self, *args, **options):
        # 1. Fetch active session
        semester_name = os.environ.get("SEMESTER_NAME", "2025/2026 Second Semester")
        session = EvaluationSession.objects.filter(title=semester_name).first()
        if not session:
            self.stdout.write(f"Active session '{semester_name}' not found. Creating and opening one...")
            session = EvaluationSession.objects.create(
                title=semester_name,
                opens_at=timezone.now(),
                closes_at=timezone.now() + timezone.timedelta(days=60),
                is_open=True
            )
        elif not session.is_open:
            session.is_open = True
            session.save()
            self.stdout.write(f"Opened existing session '{semester_name}'.")

        # Get questions
        core_questions = list(EvaluationQuestion.objects.filter(category='CORE'))
        if not core_questions:
            raise CommandError("No core evaluation questions found in the database. Run import_questions first!")

        # 2. Iterate through each configured department
        for config in DEPARTMENTS_CONFIG:
            dept_name = config['name']
            dept_code = config['code']
            
            # Find department
            dept = Department.objects.filter(Q(code=dept_code) | Q(name=dept_name)).first()
            if not dept:
                self.stdout.write(self.style.WARNING(f"Department '{dept_name}' ({dept_code}) not found. Skipping."))
                continue
                
            self.stdout.write(f"Processing '{dept.name}' (Level {config['level']})...")
            
            # Find courses for this department, level, and semester
            courses = list(Course.objects.filter(department=dept, level=config['level'], semester=semester_name))
            if not courses:
                self.stdout.write(self.style.WARNING(f"  No courses found for {dept.name} Level {config['level']} in {semester_name}. Skipping evaluations."))
                continue
                
            self.stdout.write(f"  Found {len(courses)} courses to evaluate.")
            
            # Create students
            students_created = []
            with transaction.atomic():
                for i in range(1, config['num_students'] + 1):
                    matric = f"{config['matric_prefix']}{i:03d}"
                    username = matric
                    
                    # Create custom user
                    user, created = CustomUser.objects.get_or_create(
                        username=username,
                        defaults={
                            'first_name': f"DemoStudent_{dept_code}",
                            'last_name': f"No_{i}",
                            'email': f"student_{matric}@st.lasu.edu.ng",
                            'role': 'STUDENT'
                        }
                    )
                    if created:
                        user.set_password(f"LasuStudent2026!")
                        user.save()
                        
                        # Create profile
                        StudentProfile.objects.create(
                            user=user,
                            matric_number=matric,
                            department=dept,
                            level=config['level']
                        )
                        
                        # Auto-register for courses
                        registrations = [
                            CourseRegistration(student=user, course=c, is_manual_addition=False)
                            for c in courses
                        ]
                        CourseRegistration.objects.bulk_create(registrations, ignore_conflicts=True)
                        
                    students_created.append(user)
            
            self.stdout.write(f"  Seeded {config['num_students']} students for {dept.name}.")
            
            # Select subset of students to submit evaluations
            submitting_students = students_created[:config['num_submitting']]
            
            # Seed evaluations
            eval_count = 0
            with transaction.atomic():
                for student in submitting_students:
                    for course in courses:
                        # Check if already submitted
                        if SubmissionRecord.objects.filter(student=student, course=course, session=session).exists():
                            continue
                            
                        # Create SubmissionRecord (idempotency key is auto-generated)
                        SubmissionRecord.objects.create(
                            student=student,
                            course=course,
                            session=session
                        )
                        
                        # Create EvaluationResponse for each core question
                        for q in core_questions:
                            if q.question_type == EvaluationQuestion.QuestionType.RATING:
                                # High ratings (3-5) to showcase premium averages
                                rating = random.choices([3, 4, 5], weights=[0.15, 0.45, 0.40])[0]
                                EvaluationResponse.objects.create(
                                    course=course,
                                    session=session,
                                    question=q,
                                    rating_value=rating
                                )
                            elif q.question_type == EvaluationQuestion.QuestionType.TEXT:
                                # Open text comments
                                if q.order == 10:  # Helpful
                                    text = random.choice(COMMENTS_HELPFUL)
                                else:  # Suggestions
                                    text = random.choice(COMMENTS_IMPROVE)
                                    
                                EvaluationResponse.objects.create(
                                    course=course,
                                    session=session,
                                    question=q,
                                    text_value=text
                                )
                        eval_count += 1
            self.stdout.write(f"  Generated {eval_count} course evaluations for {dept.name}.")

        self.stdout.write(self.style.SUCCESS("Demo data generation complete!"))
