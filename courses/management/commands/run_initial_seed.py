import os
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from evaluations.models import EvaluationQuestion
from scratch.import_questions import run as seed_questions

CustomUser = get_user_model()

class Command(BaseCommand):
    help = "Seeds the database for Render free tier instances automatically"

    def handle(self, *args, **options):
        self.stdout.write("Checking / Seeding academic courses...")
        # Run course import if no courses exist for the specified semester
        semester_name = os.environ.get("SEMESTER_NAME")
        if not semester_name:
            raise CommandError(
                "SEMESTER_NAME environment variable is not set. "
                "Please define it in your environment settings (e.g., SEMESTER_NAME=2025/2026 Second Semester)."
            )
        from courses.models import Course
        if not Course.objects.filter(semester=semester_name).exists():
            self.stdout.write(f"Importing courses from CSV for '{semester_name}'...")
            call_command('import_courses', 'lasu_course_allocations.csv', semester=semester_name)
        else:
            self.stdout.write(f"Courses for '{semester_name}' already seeded.")
            
        self.stdout.write("Checking / Seeding evaluation questions...")
        # Run questions import if no questions exist
        if not EvaluationQuestion.objects.exists():
            self.stdout.write("Importing questions...")
            seed_questions()
        else:
            self.stdout.write("Questions already seeded.")
            
        self.stdout.write("Checking / Seeding default admin user...")
        # Create superuser if it doesn't exist
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@lasu.edu.ng")
        admin_password = os.environ.get("ADMIN_PASSWORD", "LasuEval2026!Admin")
        
        if not CustomUser.objects.filter(username=admin_username).exists():
            self.stdout.write(f"Creating superuser '{admin_username}'...")
            CustomUser.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password,
                role='ADMIN',
                first_name="Portal",
                last_name="Administrator"
            )
            self.stdout.write("Admin user created successfully.")
        else:
            self.stdout.write("Admin user already exists.")
            
        self.stdout.write("Seeding completed successfully.")
