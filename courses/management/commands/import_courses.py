"""
Management command: import_courses
===================================
One-time import of the LASU course allocation CSV that seeds Faculty,
Department, and Course records for a given semester. This is the only
way course data enters the system in v1 — there is no LASU SIS
integration.

Usage
-----
    python manage.py import_courses path/to/lasu_course_allocations.csv \
        --semester "2024/2025 Second Semester"

Expected CSV columns (order does not matter, names must match exactly):
    Faculty, Department, Course Title, Course Code,
    Unit, Level, Course Status, Curriculum Type

What is imported:      Faculty, Department, Course
What is NOT imported:  Lecturers (they self-claim courses at signup)
                       Students (they self-register at signup)

Data quality handling
---------------------
1. Level normalisation:
   - '100','200','300','400','500' → accepted as-is
   - '2'                           → mapped to '200' (clear typo in real data)
   - '401'–'407'                   → mapped to '400' (sub-level variants)
   - '600' and anything else       → skipped; logged in the summary

2. Duplicate (code, department, semester) rows:
   Likely First/Second semester variants collapsed into one annual CSV.
   First occurrence wins; subsequent rows for the same key are skipped
   and counted in the summary.

3. All skipped rows are printed at --verbosity 2 and summarised at the
   end regardless of verbosity level, so the admin always knows what
   was dropped.
"""

import csv
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from courses.models import Course, Department, Faculty


# Maps the exact string values that appear in the Level column of the
# real CSV to the normalised choices defined on the Course model.
LEVEL_MAP = {
    "100": "100",
    "200": "200",
    "300": "300",
    "400": "400",
    "500": "500",
    # Data quality fixes for values found in the real LASU CSV:
    "2": "200",    # Typo — one row in Faculty of Engineering
    "401": "400",  # Sub-level variants in Faculty of Social Science
    "402": "400",
    "403": "400",
    "404": "400",
    "405": "400",
    "406": "400",
    "407": "400",
}

REQUIRED_COLUMNS = {
    "Faculty",
    "Department",
    "Course Title",
    "Course Code",
    "Unit",
    "Level",
    "Course Status",
    "Curriculum Type",
}


def _slugify_code(name: str, max_length: int = 10) -> str:
    """
    Derive a short code from a faculty or department name when the CSV
    doesn't supply one. Uses initials of meaningful words (drops common
    articles and prepositions). Truncated to max_length.

    Examples:
        "FACULTY OF EDUCATION"                    → "FOE"
        "SCHOOL OF COMPUTING AND INFORMATION…"   → "SCIT"
        "ELECTRONICS AND COMPUTER ENGINEERING"   → "ECE"
    """
    stop_words = {"of", "and", "the", "in", "for", "a", "an", "&"}
    words = name.upper().replace("(", "").replace(")", "").split()
    initials = "".join(w[0] for w in words if w.lower() not in stop_words)
    return initials[:max_length]


class Command(BaseCommand):
    help = (
        "One-time import of Faculty, Department, and Course records from the "
        "LASU course allocation CSV. Lecturers and students are NOT imported — "
        "they self-register via the signup flows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to the course allocation CSV file.",
        )
        parser.add_argument(
            "--semester",
            type=str,
            required=True,
            help='Semester label to tag every imported course with, e.g. "2024/2025 Second Semester".',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate the CSV without writing anything to the database. "
            "Prints a full summary of what would be created and what would be skipped.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        semester = options["semester"].strip()
        dry_run = options["dry_run"]
        verbosity = options["verbosity"]

        # ── Validate file ────────────────────────────────────────────────
        if not csv_path.exists():
            raise CommandError(f"File not found: {csv_path}")

        self.stdout.write(f"\nImporting from: {csv_path}")
        self.stdout.write(f"Semester label: {semester}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no database writes will occur.\n"))

        # ── Parse CSV ────────────────────────────────────────────────────
        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
                if missing:
                    raise CommandError(
                        f"CSV is missing required columns: {', '.join(sorted(missing))}\n"
                        f"Columns found: {', '.join(reader.fieldnames or [])}"
                    )
                rows = list(reader)
        except UnicodeDecodeError:
            raise CommandError(
                "Could not read the CSV as UTF-8. Try saving it as UTF-8 in Excel "
                "or running: iconv -f latin1 -t utf-8 input.csv > output.csv"
            )

        self.stdout.write(f"Rows read: {len(rows):,}\n")

        # ── Counters & skip log ───────────────────────────────────────────
        stats = {
            "faculties_created": 0,
            "faculties_existing": 0,
            "departments_created": 0,
            "departments_existing": 0,
            "courses_created": 0,
            "courses_existing": 0,
            "skipped_bad_level": 0,
            "skipped_duplicate": 0,
        }
        skip_log = []  # (row_number, reason, row_data)

        # Track codes we've seen in this import to catch CSV-internal dupes
        # before they hit the database unique constraint.
        seen_courses: set[tuple[str, str, str]] = set()

        # Track generated codes to avoid collision when two different names
        # produce the same initials (e.g. "EARLY CHILDHOOD…" and "ELECTRONICS
        # AND COMPUTER ENGINEERING" both slug to "ECE"). On collision we
        # append an incrementing suffix: ECE, ECE2, ECE3, …
        used_faculty_codes: set[str] = set(
            Faculty.objects.values_list("code", flat=True)
        )
        used_dept_codes: set[str] = set(
            Department.objects.values_list("code", flat=True)
        )

        def _unique_code(base: str, used: set[str]) -> str:
            candidate = base
            n = 2
            while candidate in used:
                candidate = f"{base}{n}"
                n += 1
            used.add(candidate)
            return candidate

        # ── Main import loop (inside a single transaction) ────────────────
        with transaction.atomic():

            for row_num, row in enumerate(rows, start=2):  # 2 = first data row

                faculty_name = row["Faculty"].strip()
                dept_name = row["Department"].strip()
                course_title = row["Course Title"].strip()
                course_code = row["Course Code"].strip()
                raw_level = row["Level"].strip()

                # ── Level normalisation ──────────────────────────────────
                level = LEVEL_MAP.get(raw_level)
                if level is None:
                    stats["skipped_bad_level"] += 1
                    skip_log.append((
                        row_num,
                        f"Unrecognised level {raw_level!r} — skipped",
                        f"{course_code} / {course_title}",
                    ))
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Row {row_num}: skipping level={raw_level!r} "
                                f"({course_code} {course_title[:40]})"
                            )
                        )
                    continue

                # ── Duplicate check (within this import run) ─────────────
                dedup_key = (course_code, dept_name, semester)
                if dedup_key in seen_courses:
                    stats["skipped_duplicate"] += 1
                    skip_log.append((
                        row_num,
                        f"Duplicate ({course_code}, {dept_name!r}, {semester!r}) — skipped",
                        course_title,
                    ))
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Row {row_num}: duplicate key ({course_code}, "
                                f"{dept_name[:30]!r}) — skipping"
                            )
                        )
                    continue
                seen_courses.add(dedup_key)

                if dry_run:
                    # In a dry run we still want to exercise the code path
                    # fully, so count what would happen but don't touch the db.
                    stats["courses_created"] += 1
                    continue

                # ── Faculty ──────────────────────────────────────────────
                faculty, created = Faculty.objects.get_or_create(
                    name=faculty_name,
                    defaults={
                        "code": _unique_code(_slugify_code(faculty_name), used_faculty_codes)
                    },
                )
                if created:
                    stats["faculties_created"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  + Faculty: {faculty_name} [{faculty.code}]")
                else:
                    stats["faculties_existing"] += 1

                # ── Department ───────────────────────────────────────────
                dept, created = Department.objects.get_or_create(
                    name=dept_name,
                    defaults={
                        "code": _unique_code(_slugify_code(dept_name), used_dept_codes),
                        "faculty": faculty,
                    },
                )
                if created:
                    stats["departments_created"] += 1
                    if verbosity >= 2:
                        self.stdout.write(f"  + Department: {dept_name} [{dept_code}]")
                else:
                    stats["departments_existing"] += 1

                # ── Course ───────────────────────────────────────────────
                course, created = Course.objects.get_or_create(
                    code=course_code,
                    department=dept,
                    semester=semester,
                    defaults={
                        "title": course_title,
                        "level": level,
                    },
                )
                if created:
                    stats["courses_created"] += 1
                else:
                    # Already exists from a prior run — don't overwrite.
                    stats["courses_existing"] += 1

            # ── Dry run: roll back so nothing was committed ───────────────
            if dry_run:
                transaction.set_rollback(True)

        # ── Summary ───────────────────────────────────────────────────────
        self.stdout.write("\n" + "-" * 60)
        self.stdout.write(self.style.SUCCESS("Import complete") if not dry_run else "Dry-run summary")
        self.stdout.write("-" * 60)

        if not dry_run:
            self.stdout.write(
                f"  Faculties     created: {stats['faculties_created']:>6}  "
                f"already existed: {stats['faculties_existing']:>6}"
            )
            self.stdout.write(
                f"  Departments   created: {stats['departments_created']:>6}  "
                f"already existed: {stats['departments_existing']:>6}"
            )
            self.stdout.write(
                f"  Courses       created: {stats['courses_created']:>6}  "
                f"already existed: {stats['courses_existing']:>6}"
            )
        else:
            self.stdout.write(
                f"  Courses that would be created: {stats['courses_created']:>6}"
            )

        total_skipped = stats["skipped_bad_level"] + stats["skipped_duplicate"]
        if total_skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  Rows skipped — bad level:    {stats['skipped_bad_level']:>6}\n"
                    f"  Rows skipped — duplicate:    {stats['skipped_duplicate']:>6}\n"
                    f"  Total skipped:               {total_skipped:>6}"
                )
            )
            self.stdout.write(
                "\n  Run with --verbosity 2 to see each skipped row,"
                " or check the log below:"
            )
            for row_num, reason, label in skip_log[:20]:
                self.stdout.write(f"    Row {row_num:>5}: {reason}  [{label[:50]}]")
            if len(skip_log) > 20:
                self.stdout.write(f"    ... and {len(skip_log) - 20} more")
        else:
            self.stdout.write(self.style.SUCCESS("  No rows were skipped."))

        self.stdout.write("-" * 60 + "\n")
