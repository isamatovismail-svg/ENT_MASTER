from django import forms
from .models import ProfileSubjectCombination, StudentSubjectSelection

class StudentSubjectSelectionForm(forms.ModelForm):
    """
    Form allowing students to select their officially permitted profile subject pair.
    """
    combination = forms.ModelChoiceField(
        queryset=ProfileSubjectCombination.objects.filter(is_active=True),
        empty_label="— Бейіндік пәндер жұбын таңдаңыз —",
        widget=forms.Select(attrs={'class': 'form-select form-control-custom'}),
        label="Бейіндік пән жұбы"
    )

    class Meta:
        model = StudentSubjectSelection
        fields = ['combination']
