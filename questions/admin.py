from django.contrib import admin
from .models import Question, AnswerOption

class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 5
    fields = ('key', 'text', 'is_correct')

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'question_type', 'difficulty', 'language', 'moderation_status', 'points', 'created_by')
    list_filter = ('moderation_status', 'subject', 'question_type', 'difficulty', 'language')
    search_fields = ('text', 'explanation')
    inlines = [AnswerOptionInline]
    actions = ['approve_questions', 'reject_questions']

    @admin.action(description="Таңдалған сұрақтарды мақұлдау (Approve)")
    def approve_questions(self, request, queryset):
        queryset.update(moderation_status=Question.ModerationStatus.APPROVED)

    @admin.action(description="Таңдалған сұрақтарды қабылдамау (Reject)")
    def reject_questions(self, request, queryset):
        queryset.update(moderation_status=Question.ModerationStatus.REJECTED)
