import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from subjects.models import Subject, StudentSubjectSelection
from questions.models import Question, AnswerOption
from .models import ExamConfiguration, ExamAttempt, ExamAttemptQuestion
from .services import ScoringService, ExamCreationService

@login_required
def student_dashboard_view(request):
    """
    SaaS Student Dashboard.
    Pulls real database metrics: profile info, 5 selected subjects,
    recent exams, score progression for Chart.js, weak topics, and leaderboard preview.
    """
    user = request.user
    if user.is_teacher() and not user.is_administrator():
        return redirect('teacher_questions_list')

    selection = getattr(user, 'subject_selection', None)
    if not selection:
        return redirect('subjects:select_subjects')

    five_subjects = selection.get_all_five_subjects()

    # Recent exam attempts from database
    recent_attempts = ExamAttempt.objects.filter(
        student=user,
        status=ExamAttempt.Status.COMPLETED
    ).order_by('-finished_at')[:6]

    # Best score and average score
    completed_attempts = ExamAttempt.objects.filter(student=user, status=ExamAttempt.Status.COMPLETED)
    best_score = completed_attempts.order_by('-total_score').first()
    best_score_val = best_score.total_score if best_score else 0

    # Chart progression data (last 7 completed attempts)
    chart_attempts = list(completed_attempts.order_by('finished_at')[:7])
    chart_labels = [f"Тест #{a.id} ({a.finished_at.strftime('%d.%m') if a.finished_at else ''})" for a in chart_attempts]
    chart_data = [a.total_score for a in chart_attempts]

    # Subject performance stats based on completed attempts
    subject_stats = []
    for subj in five_subjects:
        attempt_questions = ExamAttemptQuestion.objects.filter(
            attempt__student=user,
            attempt__status=ExamAttempt.Status.COMPLETED,
            subject=subj
        )
        total_q = attempt_questions.count()
        correct_q = attempt_questions.filter(points_awarded__gt=0).count()
        accuracy = round((correct_q / total_q) * 100) if total_q > 0 else 0
        subject_stats.append({
            'subject': subj,
            'total_answered': total_q,
            'correct_count': correct_q,
            'accuracy': accuracy,
        })

    # Weak topics / areas with most mistakes
    weak_questions = ExamAttemptQuestion.objects.filter(
        attempt__student=user,
        attempt__status=ExamAttempt.Status.COMPLETED,
        points_awarded=0.0
    ).select_related('question', 'subject')[:4]

    # Leaderboard preview (top 5 students across platform)
    from django.db.models import Max
    top_students = ExamAttempt.objects.filter(
        status=ExamAttempt.Status.COMPLETED,
        mode=ExamAttempt.Mode.FULL_SIMULATION
    ).values('student__username', 'student__first_name', 'student__last_name', 'student__target_university').annotate(
        max_score=Max('total_score')
    ).order_by('-max_score')[:5]

    context = {
        'selection': selection,
        'five_subjects': five_subjects,
        'subject_stats': subject_stats,
        'recent_attempts': recent_attempts,
        'best_score_val': best_score_val,
        'chart_labels_json': json.dumps(chart_labels),
        'chart_data_json': json.dumps(chart_data),
        'weak_questions': weak_questions,
        'top_students': top_students,
    }
    return render(request, 'student/dashboard.html', context)


@login_required
def start_full_simulation_view(request):
    """
    Initializes a new Full ENT Examination Simulation.
    Creates server-side session with frozen questions and hard deadline.
    """
    user = request.user
    if not hasattr(user, 'subject_selection'):
        messages.warning(request, "Алдымен өзіңіздің 2 бейіндік пәніңізді таңдаңыз!")
        return redirect('subjects:select_subjects')

    try:
        attempt = ExamCreationService.start_full_simulation(user)
        return redirect('exams:exam_interface', attempt_id=attempt.id)
    except Exception as e:
        messages.error(request, f"Емтиханды бастау мүмкін болмады: {str(e)}")
        return redirect('student_dashboard')


@login_required
def start_practice_view(request, subject_id):
    """
    Starts an interactive practice session for a single chosen subject.
    """
    user = request.user
    try:
        attempt = ExamCreationService.start_practice_set(user, subject_id, count=10)
        return redirect('exams:exam_interface', attempt_id=attempt.id)
    except Exception as e:
        messages.error(request, f"Жаттығуды бастау мүмкін болмады: {str(e)}")
        return redirect('student_dashboard')


@login_required
def exam_interface_view(request, attempt_id):
    """
    Real examination interface (ENT Simulator).
    Handles timer countdown, question palette, flagging, and secure answer choices.
    Never exposes correct answers to client during active examination!
    """
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)

    # Check if time expired
    if attempt.status == ExamAttempt.Status.IN_PROGRESS and attempt.is_expired():
        ScoringService.finish_and_grade_attempt(attempt)
        messages.warning(request, "Емтиханның ресми уақыты аяқталды! Жауаптарыңыз автоматты түрде сақталды.")
        return redirect('results:exam_result', attempt_id=attempt.id)

    if attempt.status == ExamAttempt.Status.COMPLETED:
        return redirect('results:exam_result', attempt_id=attempt.id)

    attempt_questions = attempt.attempt_questions.select_related('question', 'subject').prefetch_related('question__options', 'selected_options')

    # Group questions by subject for subject tabs
    subjects_in_exam = []
    seen_subj_ids = set()
    for aq in attempt_questions:
        if aq.subject.id not in seen_subj_ids:
            seen_subj_ids.add(aq.subject.id)
            subjects_in_exam.append(aq.subject)

    context = {
        'attempt': attempt,
        'attempt_questions': attempt_questions,
        'subjects_in_exam': subjects_in_exam,
        'remaining_seconds': attempt.get_remaining_seconds(),
    }
    return render(request, 'exams/exam_interface.html', context)


@login_required
@require_POST
def save_answer_api(request):
    """
    AJAX endpoint for automatic answer saving.
    Security: Server verifies attempt belongs to authenticated user and deadline has not expired.
    """
    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        attempt_question_id = data.get('attempt_question_id')
        selected_option_ids = data.get('selected_option_ids', [])

        attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)

        if attempt.status != ExamAttempt.Status.IN_PROGRESS or attempt.is_expired():
            return JsonResponse({'status': 'expired', 'message': 'Емтихан уақыты өтті!'}, status=403)

        attempt_q = get_object_or_404(ExamAttemptQuestion, id=attempt_question_id, attempt=attempt)

        # Update options
        options = AnswerOption.objects.filter(id__in=selected_option_ids, question=attempt_q.question)
        attempt_q.selected_options.set(options)
        attempt_q.is_answered = len(options) > 0
        attempt_q.save(update_fields=['is_answered'])

        answered_count = attempt.attempt_questions.filter(is_answered=True).count()
        total_count = attempt.attempt_questions.count()

        return JsonResponse({
            'status': 'ok',
            'is_answered': attempt_q.is_answered,
            'answered_count': answered_count,
            'total_count': total_count
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
def flag_question_api(request):
    """
    AJAX endpoint for bookmarking/flagging a question for review.
    """
    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        attempt_question_id = data.get('attempt_question_id')

        attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)
        attempt_q = get_object_or_404(ExamAttemptQuestion, id=attempt_question_id, attempt=attempt)

        attempt_q.is_flagged = not attempt_q.is_flagged
        attempt_q.save(update_fields=['is_flagged'])

        return JsonResponse({'status': 'ok', 'is_flagged': attempt_q.is_flagged})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def submit_exam_view(request, attempt_id):
    """
    Finalizes and grades the exam session.
    Calculates final score server-side and redirects to results summary.
    """
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)

    if attempt.status == ExamAttempt.Status.COMPLETED:
        messages.info(request, "Бұл емтихан бұрын аяқталған.")
        return redirect('results:exam_result', attempt_id=attempt.id)

    ScoringService.finish_and_grade_attempt(attempt)
    messages.success(request, f"Емтихан сәтті аяқталды! Сіздің жинаған балыңыз: {attempt.total_score} / {attempt.max_possible_score}")
    return redirect('results:exam_result', attempt_id=attempt.id)


@login_required
@require_POST
def practice_check_answer_api(request):
    """
    Interactive instant check for Practice Mode only.
    Returns correct answer and explanation immediately for learning.
    """
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        selected_option_ids = data.get('selected_option_ids', [])

        question = get_object_or_404(Question, id=question_id)
        points = ScoringService.calculate_question_points(question, selected_option_ids)
        is_correct = points > 0

        correct_options = list(question.options.filter(is_correct=True).values('id', 'key', 'text'))

        return JsonResponse({
            'status': 'ok',
            'is_correct': is_correct,
            'points_awarded': points,
            'correct_options': correct_options,
            'explanation': question.explanation or "Бұл сұраққа арналған қосымша түсіндірме дайындалуда."
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
