from django import forms
from .models import Question, AnswerOption
from subjects.models import Subject

class QuestionCreateForm(forms.ModelForm):
    """
    Teacher and Admin Question Authoring Form.
    Includes question text, subject, options A, B, C, D, E and correct answer keys.
    """
    option_a = forms.CharField(label="А нұсқасы", widget=forms.TextInput(attrs={'class': 'form-control form-control-custom'}))
    option_b = forms.CharField(label="В нұсқасы", widget=forms.TextInput(attrs={'class': 'form-control form-control-custom'}))
    option_c = forms.CharField(label="С нұсқасы", widget=forms.TextInput(attrs={'class': 'form-control form-control-custom'}))
    option_d = forms.CharField(label="D нұсқасы", widget=forms.TextInput(attrs={'class': 'form-control form-control-custom'}))
    option_e = forms.CharField(label="Е нұсқасы", required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-custom'}))

    correct_options = forms.CharField(
        label="Дұрыс нұсқа(лар)",
        help_text="Бір немесе бірнеше дұрыс нұсқа әріптерін жазыңыз (мыс: 'A' немесе 'A, C')",
        widget=forms.TextInput(attrs={'class': 'form-control form-control-custom', 'placeholder': 'A немесе B, D'})
    )

    class Meta:
        model = Question
        fields = ['subject', 'question_type', 'difficulty', 'language', 'text', 'image', 'explanation', 'points']
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-select form-control-custom'}),
            'question_type': forms.Select(attrs={'class': 'form-select form-control-custom'}),
            'difficulty': forms.Select(attrs={'class': 'form-select form-control-custom'}),
            'language': forms.Select(attrs={'class': 'form-select form-control-custom'}),
            'text': forms.Textarea(attrs={'class': 'form-control form-control-custom', 'rows': 4}),
            'image': forms.FileInput(attrs={'class': 'form-control form-control-custom'}),
            'explanation': forms.Textarea(attrs={'class': 'form-control form-control-custom', 'rows': 3}),
            'points': forms.NumberInput(attrs={'class': 'form-control form-control-custom', 'min': 1, 'max': 5}),
        }

    def save(self, user=None, commit=True):
        question = super().save(commit=False)
        if user:
            question.created_by = user
            # Teachers need moderation approval; Admins auto-approve
            if user.is_administrator():
                question.moderation_status = Question.ModerationStatus.APPROVED
            else:
                question.moderation_status = Question.ModerationStatus.PENDING

        if commit:
            question.save()
            # Parse and save options
            correct_keys = [k.strip().upper() for k in self.cleaned_data['correct_options'].replace(';', ',').split(',') if k.strip()]
            options_data = [
                ('A', self.cleaned_data.get('option_a')),
                ('B', self.cleaned_data.get('option_b')),
                ('C', self.cleaned_data.get('option_c')),
                ('D', self.cleaned_data.get('option_d')),
                ('E', self.cleaned_data.get('option_e')),
            ]
            for key, text in options_data:
                if text:
                    AnswerOption.objects.create(
                        question=question,
                        key=key,
                        text=text,
                        is_correct=(key in correct_keys)
                    )
        return question


class QuestionImportForm(forms.Form):
    """
    CSV File Upload Form for bulk question bank loading.
    """
    csv_file = forms.FileField(
        label="CSV файлды таңдаңыз",
        help_text="Бағандары: subject_code, question_type, difficulty, language, question_text, explanation, points, option_A, option_B, option_C, option_D, option_E, correct_keys",
        widget=forms.FileInput(attrs={'class': 'form-control form-control-custom', 'accept': '.csv'})
    )
