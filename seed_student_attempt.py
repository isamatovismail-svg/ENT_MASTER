import os
import django
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User
from subjects.models import StudentSubjectSelection
from exams.models import ExamAttempt, ExamAttemptQuestion
from exams.services import ScoringService, ExamCreationService

def seed_attempt():
    student = User.objects.filter(username='student').first()
    if not student:
        return

    # Check if student already has completed attempts
    if ExamAttempt.objects.filter(student=student, status=ExamAttempt.Status.COMPLETED).exists():
        print("  ✓ Student already has exam history.")
        return

    print("🌱 Generating initial sample exam attempt for student...")
    attempt = ExamCreationService.start_full_simulation(student)
    
    # Simulate answers for the generated questions
    for aq in attempt.attempt_questions.all():
        # Select correct option for 85% of questions
        correct_opts = aq.question.options.filter(is_correct=True)
        if correct_opts.exists():
            aq.selected_options.set(correct_opts)
            aq.is_answered = True
            aq.save()

    # Finish and grade attempt
    ScoringService.finish_and_grade_attempt(attempt)
    # Set finish time slightly earlier for realistic timeline
    attempt.finished_at = timezone.now() - timedelta(hours=2)
    attempt.save()
    print(f"  ✓ Created completed attempt #{attempt.id} with score {attempt.total_score}/{attempt.max_possible_score}")

if __name__ == '__main__':
    seed_attempt()
