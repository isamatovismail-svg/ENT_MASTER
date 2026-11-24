from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Subject, ProfileSubjectCombination, StudentSubjectSelection
from .forms import StudentSubjectSelectionForm

@login_required
def select_subjects_view(request):
    """
    Workflow for student to choose their 2 profile subjects.
    3 compulsory subjects are automatically attached.
    """
    user = request.user
    existing_selection = getattr(user, 'subject_selection', None)

    if request.method == 'POST':
        form = StudentSubjectSelectionForm(request.POST, instance=existing_selection)
        if form.is_valid():
            selection = form.save(commit=False)
            selection.student = user
            selection.save()
            messages.success(request, f"Бейіндік пәндер жұбы '{selection.combination.name}' сәтті таңдалды!")
            return redirect('student_dashboard')
    else:
        form = StudentSubjectSelectionForm(instance=existing_selection)

    compulsory_subjects = Subject.objects.filter(is_compulsory=True).order_by('order')
    combinations = ProfileSubjectCombination.objects.filter(is_active=True).select_related('subject_1', 'subject_2')

    context = {
        'form': form,
        'compulsory_subjects': compulsory_subjects,
        'combinations': combinations,
        'existing_selection': existing_selection,
    }
    return render(request, 'subjects/select_subjects.html', context)


def subjects_list_view(request):
    """
    Public listing of subjects and question statistics.
    """
    compulsory_subjects = Subject.objects.filter(is_compulsory=True).order_by('order')
    profile_subjects = Subject.objects.filter(is_compulsory=False).order_by('order', 'name')
    combinations = ProfileSubjectCombination.objects.filter(is_active=True)

    context = {
        'compulsory_subjects': compulsory_subjects,
        'profile_subjects': profile_subjects,
        'combinations': combinations,
    }
    return render(request, 'subjects/subjects_list.html', context)
