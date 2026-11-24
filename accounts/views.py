from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from .forms import StudentRegistrationForm, TeacherRegistrationForm, UserProfileForm

def home_view(request):
    """
    Public homepage of ENT MASTER.
    """
    from subjects.models import Subject, ProfileSubjectCombination
    compulsory_subjects = Subject.objects.filter(is_compulsory=True).order_by('order')
    profile_pairs = ProfileSubjectCombination.objects.filter(is_active=True)[:6]
    
    context = {
        'compulsory_subjects': compulsory_subjects,
        'profile_pairs': profile_pairs,
    }
    return render(request, 'home.html', context)


def register_student_view(request):
    """
    Handles student registration.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Тіркелу сәтті аяқталды! Қош келдіңіз!")
            return redirect('subjects:select_subjects')
    else:
        form = StudentRegistrationForm()

    return render(request, 'accounts/register_student.html', {'form': form})


def register_teacher_view(request):
    """
    Handles teacher registration.
    Teacher accounts require administrator approval before gaining question creation privileges.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.info(
                request,
                "Мұғалім ретінде тіркелдіңіз! Әкімші аккаунтыңызды растағаннан кейін сұрақтарды басқаруға рұқсат беріледі."
            )
            return redirect('login')
    else:
        form = TeacherRegistrationForm()

    return render(request, 'accounts/register_teacher.html', {'form': form})


def login_view(request):
    """
    Standard Django authentication login view.
    """
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Қош келдіңіз, {user.first_name or user.username}!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Логин немесе құпия сөз қате енгізілді.")
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """
    Logs out the user safely and redirects to the homepage.
    """
    logout(request)
    messages.info(request, "Сіз жүйеден сәтті шықтыңыз.")
    return redirect('home')


@login_required
def dashboard_redirect_view(request):
    """
    Smart router redirecting user to appropriate dashboard based on their role:
    - Administrator -> /admin-panel/
    - Teacher -> /teacher/
    - Student -> /dashboard/
    """
    user = request.user
    if user.is_administrator():
        return redirect('admin_panel_dashboard')
    elif user.is_teacher():
        if not user.is_teacher_approved:
            return redirect('teacher_pending')
        return redirect('teacher_questions_list')
    else:
        # Check if student has selected subjects yet
        if not hasattr(user, 'subject_selection'):
            return redirect('subjects:select_subjects')
        return redirect('student_dashboard')


@login_required
def profile_view(request):
    """
    Student or Teacher profile management.
    """
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль деректері сәтті жаңартылды!")
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form})


@login_required
def teacher_pending_view(request):
    """
    Waiting room notice for teachers whose accounts are still pending administrator verification.
    """
    if request.user.is_teacher_approved or request.user.is_administrator():
        return redirect('teacher_questions_list')

    return render(request, 'accounts/teacher_pending.html')
