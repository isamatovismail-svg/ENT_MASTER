from django.db import models
from django.conf import settings
from django.utils import timezone
from subjects.models import Subject, ProfileSubjectCombination
from questions.models import Question, AnswerOption

class ExamConfiguration(models.Model):
    """
    Administrator-configurable settings for Full ENT Simulation.
    Allows changing total duration, question quotas per subject, and scoring limits.
    """
    title = models.CharField(
        max_length=200,
        default="ҰБТ Ресми Симуляторы (ENT Master)",
        help_text="Емтихан атауы"
    )
    duration_minutes = models.PositiveIntegerField(
        default=240,
        help_text="Жалпы ресми емтихан уақыты (минут, әдетте 240 мин / 4 сағат)"
    )
    total_questions = models.PositiveIntegerField(
        default=120,
        help_text="Жалпы сұрақ саны (әдетте 120 сұрақ)"
    )
    total_max_score = models.PositiveIntegerField(
        default=140,
        help_text="Жалпы максималды балл (әдетте 140 балл)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Осы конфигурация қазір қолданыста ма?"
    )

    # Question quotas per subject
    compulsory_history_count = models.PositiveIntegerField(default=20, help_text="Қазақстан тарихы сұрақ саны")
    compulsory_mathlit_count = models.PositiveIntegerField(default=15, help_text="Мат. сауаттылық сұрақ саны")
    compulsory_readlit_count = models.PositiveIntegerField(default=15, help_text="Оқу сауаттылығы сұрақ саны")
    profile_1_count = models.PositiveIntegerField(default=35, help_text="1-ші бейіндік пән сұрақ саны")
    profile_2_count = models.PositiveIntegerField(default=35, help_text="2-ші бейіндік пән сұрақ саны")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Емтихан конфигурациясы"
        verbose_name_plural = "Емтихан конфигурациялары"

    def __str__(self):
        active_str = " (Белсенді)" if self.is_active else ""
        return f"{self.title} — {self.duration_minutes} мин / {self.total_questions} сұрақ{active_str}"


class ExamAttempt(models.Model):
    """
    Student's examination session (Practice or Full ENT Simulation).
    Controlled and timed strictly by the Django server to prevent cheating.
    """
    class Mode(models.TextChoices):
        PRACTICE = 'PRACTICE', 'Жаттығу режимі (Practice Mode)'
        FULL_SIMULATION = 'FULL_SIMULATION', 'Толық ҰБТ Симуляторы (Full ENT Simulation)'

    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'Тапсырылуда (In Progress)'
        COMPLETED = 'COMPLETED', 'Аяқталды (Completed)'
        EXPIRED = 'EXPIRED', 'Уақыты өтті (Expired)'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exam_attempts'
    )
    config = models.ForeignKey(
        ExamConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attempts'
    )
    mode = models.CharField(
        max_length=25,
        choices=Mode.choices,
        default=Mode.FULL_SIMULATION
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS
    )
    combination = models.ForeignKey(
        ProfileSubjectCombination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    practice_subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Егер жаттығу режимі болса, таңдалған пән"
    )

    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField(help_text="Серверде қатаң бекітілген уақыт шегі")
    finished_at = models.DateTimeField(null=True, blank=True)

    total_score = models.FloatField(default=0.0, help_text="Жинаған балы")
    max_possible_score = models.FloatField(default=140.0, help_text="Мүмкін болған максималды балл")
    percentage = models.FloatField(default=0.0, help_text="Дәлдік пайызы")

    class Meta:
        ordering = ['-started_at']
        verbose_name = "Емтихан тапсырылымы"
        verbose_name_plural = "Емтихан тапсырылымдары"

    def is_expired(self):
        """Checks if server deadline has passed."""
        return timezone.now() > self.deadline

    def get_remaining_seconds(self):
        """Returns seconds left until server deadline."""
        if self.status != self.Status.IN_PROGRESS:
            return 0
        diff = (self.deadline - timezone.now()).total_seconds()
        return max(0, int(diff))

    def get_duration_formatted(self):
        """Returns time spent formatted (e.g. 3 сағ 24 мин)."""
        if not self.finished_at:
            return "—"
        seconds = int((self.finished_at - self.started_at).total_seconds())
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours} сағ {minutes} мин"
        return f"{minutes} мин"

    def __str__(self):
        return f"{self.student.username} — {self.get_mode_display()} ({self.get_status_display()}) — {self.total_score} балл"


class ExamAttemptQuestion(models.Model):
    """
    A single question assigned to an exam attempt with frozen order and student's choices.
    """
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name='attempt_questions'
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )
    order = models.PositiveIntegerField(default=1, help_text="Сұрақтың нөмірі (1-120)")
    selected_options = models.ManyToManyField(
        AnswerOption,
        blank=True,
        related_name='chosen_in_attempts'
    )
    is_flagged = models.BooleanField(default=False, help_text="Оқушы қайта қарау үшін белгіледі ме?")
    is_answered = models.BooleanField(default=False, help_text="Жауап берілді ме?")
    points_awarded = models.FloatField(default=0.0, help_text="Бұл сұраққа есептелген балл")

    class Meta:
        ordering = ['order']
        unique_together = ('attempt', 'order')

    def __str__(self):
        return f"№{self.order} [{self.subject.name}] ({self.attempt.student.username})"
