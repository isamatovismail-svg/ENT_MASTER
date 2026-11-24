from django.db import models
from django.conf import settings
from subjects.models import Subject

class Question(models.Model):
    """
    ENT Test Question.
    Can be created by approved teachers or administrators.
    Supports single-choice and multiple-choice types, images, and explanations.
    """
    class QuestionType(models.TextChoices):
        SINGLE = 'SINGLE', 'Бір дұрыс жауап (Single Choice)'
        MULTIPLE = 'MULTIPLE', 'Бір немесе бірнеше дұрыс жауап (Multiple Choice)'

    class Difficulty(models.TextChoices):
        EASY = 'EASY', 'Оңай (Easy)'
        MEDIUM = 'MEDIUM', 'Орташа (Medium)'
        HARD = 'HARD', 'Күрделі (Hard)'

    class Language(models.TextChoices):
        KK = 'kk', 'Қазақша'
        RU = 'ru', 'Русский'
        EN = 'en', 'English'
        UZ = 'uz', "O'zbekcha"

    class ModerationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Тексерілуде (Pending)'
        APPROVED = 'APPROVED', 'Мақұлданған (Approved)'
        REJECTED = 'REJECTED', 'Қабылданбаған (Rejected)'

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='questions',
        help_text="Қай пәнге тиесілі?"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authored_questions',
        help_text="Сұрақты құрастырған мұғалім немесе әкімші"
    )

    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE,
        help_text="Сұрақ түрі"
    )

    language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.KK,
        help_text="Сұрақ жазылған нақты тіл"
    )

    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        help_text="Күрделілік деңгейі"
    )

    text = models.TextField(help_text="Сұрақтың толық мәтіні немесе шарты")

    image = models.ImageField(
        upload_to='questions/',
        blank=True,
        null=True,
        help_text="Қосымша сызба, сурет немесе формула (міндетті емес)"
    )

    explanation = models.TextField(
        blank=True,
        help_text="Дұрыс жауаптың шешімі, формуласы немесе түсіндірмесі"
    )

    moderation_status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.APPROVED,  # Admin added can be auto-approved, teachers will submit as PENDING
        help_text="Модерация мәртебесі. Тек APPROVED сұрақтар емтиханға шығады."
    )

    rejection_reason = models.TextField(
        blank=True,
        help_text="Қабылданбаған жағдайда себебі"
    )

    points = models.PositiveIntegerField(
        default=1,
        help_text="Бұл сұраққа берілетін максималды балл"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']
        verbose_name = "Сұрақ"
        verbose_name_plural = "Сұрақтар"

    def __str__(self):
        snippet = self.text[:60] + "..." if len(self.text) > 60 else self.text
        return f"[{self.subject.code}] {snippet} ({self.get_moderation_status_display()})"

    def is_approved(self):
        return self.moderation_status == self.ModerationStatus.APPROVED

    def get_correct_options(self):
        return self.options.filter(is_correct=True)

    def get_correct_keys_list(self):
        return list(self.options.filter(is_correct=True).values_list('key', flat=True))


class AnswerOption(models.Model):
    """
    Answer Option for a Question (A, B, C, D, E, etc.).
    """
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='options'
    )
    key = models.CharField(
        max_length=5,
        help_text="Нұсқа әрпі (A, B, C, D, E...)"
    )
    text = models.TextField(help_text="Жауап нұсқасының мәтіні")
    is_correct = models.BooleanField(
        default=False,
        help_text="Бұл нұсқа дұрыс па?"
    )

    class Meta:
        ordering = ['key']
        verbose_name = "Жауап нұсқасы"
        verbose_name_plural = "Жауап нұсқалары"

    def __str__(self):
        checkmark = " ✓" if self.is_correct else ""
        return f"{self.key}) {self.text[:40]}{checkmark}"
