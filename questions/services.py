"""
ENT MASTER — Question Management & Safe Import Service.
Provides validation, duplicate checking, and bulk import from CSV.
"""

import csv
import io
from django.db import transaction
from subjects.models import Subject
from questions.models import Question, AnswerOption

class QuestionImportService:
    """
    Validates and safely imports questions from CSV files.
    Expected CSV columns:
    subject_code, question_type, difficulty, language, question_text, explanation, points, option_A, option_B, option_C, option_D, option_E, correct_keys
    """

    @classmethod
    def import_from_csv(cls, file_content_str, user=None) -> dict:
        reader = csv.DictReader(io.StringIO(file_content_str))
        required_headers = {'subject_code', 'question_text', 'option_A', 'option_B', 'correct_keys'}

        if not reader.fieldnames or not required_headers.issubset(set(reader.fieldnames)):
            missing = required_headers - set(reader.fieldnames or [])
            return {
                'success': False,
                'errors': [f"CSV файлында міндетті бағандар жоқ: {', '.join(missing)}"],
                'imported_count': 0
            }

        imported_questions = []
        validation_errors = []

        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                subject_code = row.get('subject_code', '').strip()
                question_text = row.get('question_text', '').strip()
                correct_keys_raw = row.get('correct_keys', '').strip().upper()
                explanation = row.get('explanation', '').strip()
                difficulty = row.get('difficulty', 'MEDIUM').strip().upper()
                language = row.get('language', 'kk').strip().lower()
                question_type = row.get('question_type', 'SINGLE').strip().upper()
                points = int(row.get('points', 1) or 1)

                if not question_text:
                    validation_errors.append(f"Қатар {row_num}: Сұрақ мәтіні бос.")
                    continue

                subject = Subject.objects.filter(code=subject_code).first()
                if not subject:
                    validation_errors.append(f"Қатар {row_num}: '{subject_code}' пән коды табылмады.")
                    continue

                # Duplicate detection by text and subject
                if Question.objects.filter(subject=subject, text=question_text).exists():
                    validation_errors.append(f"Қатар {row_num}: Бұл сұрақ бұрын жүктелген (қайталану анықталды).")
                    continue

                # Parse correct keys (e.g. 'A' or 'A,B')
                correct_keys = [k.strip() for k in correct_keys_raw.replace(';', ',').split(',') if k.strip()]
                if not correct_keys:
                    validation_errors.append(f"Қатар {row_num}: Дұрыс жауап белгіленбеген (correct_keys бос).")
                    continue

                # Create question
                question = Question.objects.create(
                    subject=subject,
                    created_by=user,
                    question_type=question_type if question_type in Question.QuestionType.values else Question.QuestionType.SINGLE,
                    difficulty=difficulty if difficulty in Question.Difficulty.values else Question.Difficulty.MEDIUM,
                    language=language if language in Question.Language.values else Question.Language.KK,
                    text=question_text,
                    explanation=explanation,
                    points=points,
                    moderation_status=Question.ModerationStatus.APPROVED if (user and user.is_administrator()) else Question.ModerationStatus.PENDING
                )

                # Parse and create answer options (A, B, C, D, E)
                for key in ['A', 'B', 'C', 'D', 'E', 'F']:
                    opt_col = f'option_{key}'
                    opt_text = row.get(opt_col, '').strip()
                    if opt_text:
                        AnswerOption.objects.create(
                            question=question,
                            key=key,
                            text=opt_text,
                            is_correct=(key in correct_keys)
                        )

                imported_questions.append(question)

        return {
            'success': len(imported_questions) > 0,
            'imported_count': len(imported_questions),
            'errors': validation_errors
        }
