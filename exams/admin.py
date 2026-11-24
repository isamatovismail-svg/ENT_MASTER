from django.contrib import admin
from .models import ExamConfiguration, ExamAttempt, ExamAttemptQuestion

@admin.register(ExamConfiguration)
class ExamConfigurationAdmin(admin.ModelAdmin):
    list_display = ('title', 'duration_minutes', 'total_questions', 'total_max_score', 'is_active')
    list_editable = ('is_active',)

class ExamAttemptQuestionInline(admin.TabularInline):
    model = ExamAttemptQuestion
    extra = 0
    readonly_fields = ('order', 'question', 'subject', 'is_answered', 'is_flagged', 'points_awarded')
    can_delete = False

@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'mode', 'status', 'total_score', 'max_possible_score', 'percentage', 'started_at', 'finished_at')
    list_filter = ('mode', 'status', 'started_at')
    search_fields = ('student__username', 'student__email')
    readonly_fields = ('started_at', 'deadline', 'finished_at')
    inlines = [ExamAttemptQuestionInline]
