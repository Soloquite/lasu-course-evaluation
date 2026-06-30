# Online Course Evaluation System for LASU

Final year project — Computer Science, Lagos State University.
Full design rationale lives in `PRD_LASU_Evaluation_System.md` (shipped alongside this zip). This README only covers getting the project running.

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Open .env and set SECRET_KEY to any random string for local dev.
# Leave DB_ENGINE=sqlite for now — zero extra setup needed.

# 4. Run migrations
python manage.py migrate

# 5. Create an admin account
python manage.py createsuperuser

# 6. Run the dev server
python manage.py runserver
```

Visit `http://127.0.0.1:8000/admin/` and log in with the superuser account to confirm everything works — you should see Faculty, Department, Course, and the rest of the models registered there.

## Switching to PostgreSQL

When you're ready to match the recommended stack (or deploy), edit `.env`:

```
DB_ENGINE=postgres
DB_NAME=lasu_eval
DB_USER=lasu_eval_user
DB_PASSWORD=your-real-password
DB_HOST=localhost
DB_PORT=5432
```

Then re-run `python manage.py migrate` against the new database.

## Project structure

```
config/          Django project settings, root URLs
accounts/        CustomUser, StudentProfile, LecturerProfile
courses/         Faculty, Department, Course, CourseLecturer, CourseRegistration
evaluations/     EvaluationSession, EvaluationQuestion, SubmissionRecord, EvaluationResponse
```

## The one thing to understand before touching `evaluations/models.py`

`SubmissionRecord` and `EvaluationResponse` are deliberately two separate tables with no foreign key between them. `SubmissionRecord` proves *who* submitted (no content). `EvaluationResponse` stores *what* was said (no identity). This is the project's core anonymity guarantee — enforced by the schema itself, not by a permission check that could be bypassed or a policy that could be ignored. Any future change to either model should preserve this separation. See PRD section 10 ("The Anonymity Guarantee") for the full reasoning.

## What's built vs. what's next

Models, admin registration, and migrations for all three apps are done and verified (`python manage.py check` and a live sanity test both pass clean — see PRD section 11 for the full roadmap). Views, templates, the CSV import script, and the signup flows are not yet built — that's Phase 2 onward.
