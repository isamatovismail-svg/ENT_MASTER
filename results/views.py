from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Count, Avg
from exams.models import ExamAttempt, ExamAttemptQuestion
from subjects.models import Subject

@login_required
def exam_result_view(request, attempt_id):
    """
    Detailed results and score breakdown report for an examination attempt.
    Displays subject-by-subject points and comprehensive question-by-question review with explanations.
    """
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)

    attempt_questions = attempt.attempt_questions.select_related('question', 'subject').prefetch_related('question__options', 'selected_options')

    # Subject breakdown
    subject_scores = {}
    for aq in attempt_questions:
        subj = aq.subject
        if subj.id not in subject_scores:
            subject_scores[subj.id] = {
                'subject': subj,
                'points_scored': 0.0,
                'max_points': 0.0,
                'total_questions': 0,
                'correct_questions': 0
            }
        subject_scores[subj.id]['points_scored'] += aq.points_awarded
        subject_scores[subj.id]['max_points'] += float(aq.question.points)
        subject_scores[subj.id]['total_questions'] += 1
        if aq.points_awarded > 0:
            subject_scores[subj.id]['correct_questions'] += 1

    for s_id in subject_scores:
        max_p = subject_scores[s_id]['max_points']
        scored = subject_scores[s_id]['points_scored']
        subject_scores[s_id]['percentage'] = round((scored / max_p) * 100) if max_p > 0 else 0

    context = {
        'attempt': attempt,
        'subject_scores': list(subject_scores.values()),
        'attempt_questions': attempt_questions,
    }
    return render(request, 'results/exam_result.html', context)


@login_required
def exam_history_view(request):
    """
    Complete history table of student's past examinations.
    """
    attempts = ExamAttempt.objects.filter(
        student=request.user,
        status=ExamAttempt.Status.COMPLETED
    ).order_by('-finished_at')

    context = {
        'attempts': attempts,
    }
    return render(request, 'results/exam_history.html', context)


@login_required
def mistakes_notebook_view(request):
    """
    'Қателер дәптері' (Mistakes Notebook).
    Collects questions where student answered incorrectly across past exams,
    enabling targeted review, explanations, and learning.
    """
    mistakes = ExamAttemptQuestion.objects.filter(
        attempt__student=request.user,
        attempt__status=ExamAttempt.Status.COMPLETED,
        points_awarded=0.0
    ).select_related('question', 'subject', 'attempt').prefetch_related('question__options', 'selected_options').order_by('-attempt__finished_at')[:40]

    context = {
        'mistakes': mistakes,
    }
    return render(request, 'results/mistakes_notebook.html', context)


def leaderboard_view(request):
    """
    Public platform leaderboard displaying top students by best ENT examination scores.
    """
    top_students = ExamAttempt.objects.filter(
        status=ExamAttempt.Status.COMPLETED,
        mode=ExamAttempt.Mode.FULL_SIMULATION
    ).values(
        'student__username',
        'student__first_name',
        'student__last_name',
        'student__target_university'
    ).annotate(
        best_score=Max('total_score'),
        completed_exams=Count('id')
    ).order_by('-best_score')[:25]

    context = {
        'top_students': top_students,
    }
    return render(request, 'results/leaderboard.html', context)
