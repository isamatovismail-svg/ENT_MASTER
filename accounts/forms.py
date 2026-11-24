from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from .models import User

class StudentRegistrationForm(forms.ModelForm):
    """
    Registration form for high school students preparing for ENT.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '••••••••'}),
        label="Құпия сөз"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '••••••••'}),
        label="Құпия сөзді қайталаңыз"
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'target_university', 'target_score']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'aidost'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'Айдос'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'Тұрсынбай'}),
            'email': forms.EmailInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'aidos@mail.kz'}),
            'phone': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '+7 777 000 0000'}),
            'target_university': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'ҚазҰУ, СДУ, т.б.'}),
            'target_score': forms.NumberInput(attrs={'class': 'form-control form-control-custom', 'min': 50, 'max': 140}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('password_confirm', "Құпия сөздер бір-біріне сәйкес келмейді!")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.STUDENT
        user.is_teacher_approved = True
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class TeacherRegistrationForm(forms.ModelForm):
    """
    Registration form for teachers.
    Teacher accounts require administrator approval before gaining question creation privileges.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '••••••••'}),
        label="Құпия сөз"
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '••••••••'}),
        label="Құпия сөзді қайталаңыз"
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'teacher_marat'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'Марат'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'Ахметов'}),
            'email': forms.EmailInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'marat@school.kz'}),
            'phone': forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': '+7 701 111 2233'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('password_confirm', "Құпия сөздер бір-біріне сәйкес келмейді!")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.TEACHER
        user.is_teacher_approved = False  # Strict approval requirement
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """
    Profile editing form for students and teachers.
    """
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'target_university', 'target_score', 'avatar']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control form-control-custom'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control form-control-custom'}),
            'email': forms.EmailInput(attrs={'class': 'form-control form-control-custom'}),
            'phone': forms.TextInput(attrs={'class': 'form-control form-control-custom'}),
            'target_university': forms.TextInput(attrs={'class': 'form-control form-control-custom'}),
            'target_score': forms.NumberInput(attrs={'class': 'form-control form-control-custom'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control form-control-custom'}),
        }
