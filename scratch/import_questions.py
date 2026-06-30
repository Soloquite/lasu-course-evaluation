import re
from evaluations.models import EvaluationQuestion

def run():
    import os
    from django.conf import settings
    file_path = os.path.join(settings.BASE_DIR, "questions.txt.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Failed to read file: {e}")
        return

    # Regex to find "Question X: [text]"
    # Matches: Question \d+: followed by the question text up to the next Question \d+ or end of string
    pattern = re.compile(r"Question (\d+):\s*(.*?)(?=\s*Question \d+:|$)")
    matches = pattern.findall(content)
    
    if not matches:
        print("No questions found via regex pattern.")
        return

    print(f"Found {len(matches)} questions. Importing to database...")
    
    questions_created = 0
    for num_str, text in matches:
        num = int(num_str)
        text = text.strip()
        
        # Strip trailing text like "24 Custom Department Questions" or header titles if they got caught in text
        # Let's clean the text: if it contains titles like "24 Custom Department Questions", we split and clean.
        # But wait, looking at the regex, it matches up to the next "Question X:".
        # Let's clean any headers at the end of the text.
        for header in [
            "24 Custom Department Questions (Agreement Scale)",
            "Science & STEM",
            "World Languages & Culture",
            "Business & Professional Programs",
            "Humanities",
            "Studio Art & Design",
            "Music Performance & Private Lessons",
            "Theater, Dance & Performance",
            "Large Music Ensembles"
        ]:
            if text.endswith(header):
                text = text[:-len(header)].strip()
        
        # Identify question type
        # Question 10 and 11 are TEXT, rest are RATING
        if num in [10, 11]:
            q_type = EvaluationQuestion.QuestionType.TEXT
        else:
            q_type = EvaluationQuestion.QuestionType.RATING

        # Map to specific categories
        if 1 <= num <= 11:
            category = 'CORE'
        elif 12 <= num <= 14:
            category = 'STEM'
        elif 15 <= num <= 17:
            category = 'LANG'
        elif 18 <= num <= 20:
            category = 'BUS'
        elif 21 <= num <= 23:
            category = 'HUM'
        elif 24 <= num <= 27:
            category = 'ART'
        elif 28 <= num <= 31:
            category = 'MUSIC_LESSON'
        elif 32 <= num <= 35:
            category = 'THEATER'
        elif 36 <= num <= 44:
            category = 'MUSIC_ENSEMBLE'
        else:
            category = 'CORE'
            
        q, created = EvaluationQuestion.objects.update_or_create(
            order=num,
            defaults={
                'text': text,
                'question_type': q_type,
                'category': category
            }
        )
        if created:
            questions_created += 1
            
    print(f"Successfully processed {len(matches)} questions. Created {questions_created} new questions.")

if __name__ == "__main__":
    run()
