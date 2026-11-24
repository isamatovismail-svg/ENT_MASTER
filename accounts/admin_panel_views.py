from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from accounts.models import User
from questions.models import Question
from subjects.models import Subject, ProfileSubjectCombination
from exams.models import ExamAttempt, ExamConfiguration

def is_admin(user):
    return user.is_authenticated and user.is_administrator()

@login_required
@user_passes_test(is_admin)
def admin_panel_dashboard(request):
    """
    Administrator Dashboard for platform operations:
    - Teacher approvals queue
    - Question moderation queue
    - Platform analytics overview
    """
    # Teacher approval requests
    pending_teachers = User.objects.filter(role=User.Role.TEACHER, is_teacher_approved=False)

    # Questions pending moderation
    pending_questions = Question.objects.filter(
        moderation_status=Question.ModerationStatus.PENDING
    ).select_related('subject', 'created_by')[:20]

    # Platform metrics
    stats = {
        'total_students': User.objects.filter(role=User.Role.STUDENT).count(),
        'total_teachers': User.objects.filter(role=User.Role.TEACHER).count(),
        'total_questions': Question.objects.filter(moderation_status=Question.ModerationStatus.APPROVED).count(),
        'completed_exams': ExamAttempt.objects.filter(status=ExamAttempt.Status.COMPLETED).count(),
        'pending_teachers_count': pending_teachers.count(),
        'pending_questions_count': pending_questions.count(),
    }

    exam_config = ExamConfiguration.objects.filter(is_active=True).first()

    context = {
        'stats': stats,
        'pending_teachers': pending_teachers,
        'pending_questions': pending_questions,
        'exam_config': exam_config,
    }
    return render(request, 'admin_panel/dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def approve_teacher_view(request, teacher_id):
    teacher = get_object_or_404(User, id=teacher_id, role=User.Role.TEACHER)
    teacher.is_teacher_approved = True
    teacher.save()
    messages.success(request, f"Мұғалім '{teacher.get_full_name() or teacher.username}' сәтті мақұлданды!")
    return redirect('admin_panel_dashboard')


@login_required
@user_passes_test(is_admin)
def reject_teacher_view(request, teacher_id):
    teacher = get_object_or_404(User, id=teacher_id, role=User.Role.TEACHER)
    teacher.delete()
    messages.warning(request, f"Мұғалім аккаунты қабылданбады және жойылды.")
    return redirect('admin_panel_dashboard')


@login_required
@user_passes_test(is_admin)
def approve_question_view(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    question.moderation_status = Question.ModerationStatus.APPROVED
    question.save()
    messages.success(request, f"Сұрақ #{question.id} мақұлданды!")
    return redirect('admin_panel_dashboard')


@login_required
@user_passes_test(is_admin)
def reject_question_view(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    question.moderation_status = Question.ModerationStatus.REJECTED
    question.save()
    messages.warning(request, f"Сұрақ #{question.id} қабылданбады.")
    return redirect('admin_panel_dashboard')
