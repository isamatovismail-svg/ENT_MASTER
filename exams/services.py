"""
ENT MASTER — Examination & Scoring Services.
Contains:
1. Provisional Scoring Service (modular so official formulas can be updated anytime).
2. Exam Creation & Session Orchestration Service.
"""

from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from questions.models import Question, AnswerOption
from subjects.models import Subject
from exams.models import ExamConfiguration, ExamAttempt, ExamAttemptQuestion

class ScoringService:
    """
    Provisional Scoring Service for ENT Master.
    Calculates points awarded for single-choice and multiple-choice questions.
    Kept modular and isolated so scoring formulas can be modified easily.
    """

    @staticmethod
    def calculate_question_points(question: Question, selected_option_ids: list) -> float:
        """
        Calculates score for an individual question.
        Returns float points awarded (e.g. 0, 1, or 2).
        """
        if not selected_option_ids:
            return 0.0

        correct_options = question.options.filter(is_correct=True)
        correct_ids = set(correct_options.values_list('id', flat=True))
        selected_ids = set(selected_option_ids)

        if not correct_ids:
            return 0.0

        # --- A. Single-Choice Question ---
        if question.question_type == Question.QuestionType.SINGLE:
            # For single choice: exactly one option must be selected and must match the correct option
            if len(selected_ids) == 1 and selected_ids == correct_ids:
                return float(question.points)
            return 0.0

        # --- B. Multiple-Choice Question (Provisional Model) ---
        # Provisional Rule:
        # Full points if all correct options are selected with zero wrong choices.
        # Partial credit (1 point) if student found most correct options with at most 1 mistake.
        # Otherwise 0 points.
        if question.question_type == Question.QuestionType.MULTIPLE:
            if selected_ids == correct_ids:
                return float(question.points)

            # Check overlap and mistakes
            correctly_selected = len(selected_ids.intersection(correct_ids))
            incorrectly_selected = len(selected_ids - correct_ids)
            missed_correct = len(correct_ids - selected_ids)

            # 1 mistake tolerance for partial point (e.g. 1 missed or 1 extra wrong)
            total_mistakes = incorrectly_selected + missed_correct
            if total_mistakes == 1 and correctly_selected > 0:
                return 1.0  # Partial point

            return 0.0

    @classmethod
    def finish_and_grade_attempt(cls, attempt: ExamAttempt) -> ExamAttempt:
        """
        Grades all questions in an attempt, computes totals and subject breakdowns,
        and marks the attempt as COMPLETED.
        """
        with transaction.atomic():
            total_score = 0.0
            max_possible = 0.0

            attempt_questions = attempt.attempt_questions.select_related('question', 'subject').prefetch_related('selected_options')

            for attempt_q in attempt_questions:
                q = attempt_q.question
                selected_ids = list(attempt_q.selected_options.values_list('id', flat=True))
                
                points = cls.calculate_question_points(q, selected_ids)
                attempt_q.points_awarded = points
                attempt_q.is_answered = len(selected_ids) > 0
                attempt_q.save(update_fields=['points_awarded', 'is_answered'])

                total_score += points
                max_possible += float(q.points)

            attempt.total_score = round(total_score, 1)
            attempt.max_possible_score = max_possible if max_possible > 0 else 140.0
            attempt.percentage = round((total_score / attempt.max_possible_score) * 100, 1) if attempt.max_possible_score > 0 else 0.0
            attempt.status = ExamAttempt.Status.COMPLETED
            attempt.finished_at = timezone.now()
            attempt.save()

            return attempt


class ExamCreationService:
    """
    Handles creating full ENT simulations and targeted practice sets.
    Freezes questions and options in deterministic order for each attempt.
    """

    @staticmethod
    def get_or_create_default_config() -> ExamConfiguration:
        config = ExamConfiguration.objects.filter(is_active=True).first()
        if not config:
            config = ExamConfiguration.objects.create(
                title="ҰБТ Ресми Симуляторы (2026-2027 Формат)",
                duration_minutes=240,
                total_questions=120,
                total_max_score=140,
                is_active=True,
                compulsory_history_count=20,
                compulsory_mathlit_count=15,
                compulsory_readlit_count=15,
                profile_1_count=35,
                profile_2_count=35
            )
        return config

    @classmethod
    def start_full_simulation(cls, student) -> ExamAttempt:
        """
        Launches a full ENT exam simulation for the student.
        Requires that the student has selected their 2 profile subjects.
        """
        selection = getattr(student, 'subject_selection', None)
        if not selection:
            raise ValueError("Оқушы алдымен өзінің 2 бейіндік пәнін таңдауы қажет!")

        config = cls.get_or_create_default_config()

        # Check if student already has an active in-progress attempt with valid deadline
        existing_attempt = ExamAttempt.objects.filter(
            student=student,
            mode=ExamAttempt.Mode.FULL_SIMULATION,
            status=ExamAttempt.Status.IN_PROGRESS
        ).first()

        if existing_attempt:
            if not existing_attempt.is_expired():
                # Resume active attempt
                return existing_attempt
            else:
                # Expired attempt -> auto grade and finish it
                ScoringService.finish_and_grade_attempt(existing_attempt)

        # Calculate server deadline
        now = timezone.now()
        deadline = now + timedelta(minutes=config.duration_minutes)

        with transaction.atomic():
            attempt = ExamAttempt.objects.create(
                student=student,
                config=config,
                mode=ExamAttempt.Mode.FULL_SIMULATION,
                status=ExamAttempt.Status.IN_PROGRESS,
                combination=selection.combination,
                deadline=deadline,
                max_possible_score=float(config.total_max_score)
            )

            # Build question list across the 5 subjects
            # 1. Kazakhstan History (20 questions)
            # 2. Math Literacy (15 questions)
            # 3. Reading Literacy (15 questions)
            # 4. Profile Subject 1 (35 questions)
            # 5. Profile Subject 2 (35 questions)
            subjects_with_counts = [
                ('KZ_HISTORY', config.compulsory_history_count),
                ('MATH_LIT', config.compulsory_mathlit_count),
                ('READ_LIT', config.compulsory_readlit_count),
                (selection.combination.subject_1.code, config.profile_1_count),
                (selection.combination.subject_2.code, config.profile_2_count)
            ]

            order_counter = 1
            for subj_code, count in subjects_with_counts:
                subj = Subject.objects.filter(code=subj_code).first()
                if not subj:
                    continue

                # Fetch approved questions in this subject
                questions = list(Question.objects.filter(
                    subject=subj,
                    moderation_status=Question.ModerationStatus.APPROVED
                ).order_by('?')[:count])

                for q in questions:
                    ExamAttemptQuestion.objects.create(
                        attempt=attempt,
                        question=q,
                        subject=subj,
                        order=order_counter
                    )
                    order_counter += 1

            return attempt

    @classmethod
    def start_practice_set(cls, student, subject_id: int, count: int = 10) -> ExamAttempt:
        """
        Launches an interactive practice set for a specific subject.
        """
        subj = Subject.objects.get(id=subject_id)
        now = timezone.now()
        deadline = now + timedelta(hours=2)  # Generous deadline for practice

        with transaction.atomic():
            attempt = ExamAttempt.objects.create(
                student=student,
                mode=ExamAttempt.Mode.PRACTICE,
                status=ExamAttempt.Status.IN_PROGRESS,
                practice_subject=subj,
                deadline=deadline
            )

            questions = list(Question.objects.filter(
                subject=subj,
                moderation_status=Question.ModerationStatus.APPROVED
            ).order_by('?')[:count])

            order_counter = 1
            for q in questions:
                ExamAttemptQuestion.objects.create(
                    attempt=attempt,
                    question=q,
                    subject=subj,
                    order=order_counter
                )
                order_counter += 1

            return attempt
