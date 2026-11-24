from django.contrib import admin
from .models import Subject, ProfileSubjectCombination, StudentSubjectSelection

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_compulsory', 'default_question_count', 'max_score', 'order')
    list_filter = ('is_compulsory',)
    search_fields = ('name', 'code')
    ordering = ('-is_compulsory', 'order', 'name')

@admin.register(ProfileSubjectCombination)
class ProfileSubjectCombinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_1', 'subject_2', 'is_active')
    list_filter = ('is_active', 'subject_1', 'subject_2')
    search_fields = ('name',)

@admin.register(StudentSubjectSelection)
class StudentSubjectSelectionAdmin(admin.ModelAdmin):
    list_display = ('student', 'combination', 'updated_at')
    search_fields = ('student__username', 'student__email')
