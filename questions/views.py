from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Question, AnswerOption
from .forms import QuestionCreateForm, QuestionImportForm
from .services import QuestionImportService

def is_approved_teacher_or_admin(user):
    return user.is_authenticated and (user.is_administrator() or (user.is_teacher() and user.is_teacher_approved))


@login_required
@user_passes_test(is_approved_teacher_or_admin, login_url='teacher_pending')
def teacher_questions_list_view(request):
    """
    Teacher questions management dashboard.
    Lists questions created by the teacher with their moderation statuses.
    """
    user = request.user
    if user.is_administrator():
        questions_qs = Question.objects.all().select_related('subject', 'created_by')
    else:
        questions_qs = Question.objects.filter(created_by=user).select_related('subject')

    status_filter = request.GET.get('status')
    if status_filter:
        questions_qs = questions_qs.filter(moderation_status=status_filter)

    paginator = Paginator(questions_qs, 15)
    page_number = request.GET.get('page')
    questions = paginator.get_page(page_number)

    stats = {
        'total': questions_qs.count(),
        'approved': questions_qs.filter(moderation_status=Question.ModerationStatus.APPROVED).count(),
        'pending': questions_qs.filter(moderation_status=Question.ModerationStatus.PENDING).count(),
        'rejected': questions_qs.filter(moderation_status=Question.ModerationStatus.REJECTED).count(),
    }

    context = {
        'questions': questions,
        'stats': stats,
        'status_filter': status_filter,
    }
    return render(request, 'questions/teacher_questions_list.html', context)


@login_required
@user_passes_test(is_approved_teacher_or_admin, login_url='teacher_pending')
def teacher_question_create_view(request):
    """
    Allows approved teacher or administrator to author a new test question.
    """
    if request.method == 'POST':
        form = QuestionCreateForm(request.POST, request.FILES)
        if form.is_valid():
            question = form.save(user=request.user)
            if request.user.is_administrator():
                messages.success(request, "Сұрақ сәтті сақталды және мақұлданды!")
            else:
                messages.info(request, "Сұрақ модерацияға жіберілді. Әкімші мақұлдағаннан кейін емтихандарға қосылады.")
            return redirect('teacher_questions_list')
    else:
        form = QuestionCreateForm()

    return render(request, 'questions/question_form.html', {'form': form, 'title': 'Жаңа ҰБТ сұрағын қосу'})


@login_required
@user_passes_test(is_approved_teacher_or_admin, login_url='teacher_pending')
def question_import_view(request):
    """
    CSV Question Importer view.
    Safely validates and imports bulk questions from a CSV file.
    """
    if request.method == 'POST':
        form = QuestionImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                content = csv_file.read().decode('utf-8-sig')
                result = QuestionImportService.import_from_csv(content, user=request.user)

                if result['success']:
                    messages.success(request, f"Сәтті! {result['imported_count']} сұрақ жүйеге жүктелді.")
                if result['errors']:
                    for err in result['errors'][:5]:
                        messages.warning(request, err)
                    if len(result['errors']) > 5:
                        messages.warning(request, f"Және тағы {len(result['errors']) - 5} қателік анықталды.")

                return redirect('teacher_questions_list')
            except Exception as e:
                messages.error(request, f"Файлды оқу барысында қате шықты: {str(e)}")
    else:
        form = QuestionImportForm()

    return render(request, 'questions/question_import.html', {'form': form})
