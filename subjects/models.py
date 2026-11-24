from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings

class Subject(models.Model):
    """
    ENT Examination Subject.
    Includes both 3 compulsory subjects and profile elective subjects.
    """
    name = models.CharField(max_length=150, help_text="Пән атауы (Қазақша негізгі)")
    name_kk = models.CharField(max_length=150, blank=True)
    name_ru = models.CharField(max_length=150, blank=True)
    name_en = models.CharField(max_length=150, blank=True)
    name_uz = models.CharField(max_length=150, blank=True)

    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Пәннің бірегей коды (мыс: KZ_HISTORY, MATH_LIT, READ_LIT, MATH, PHYSICS, т.б.)"
    )

    is_compulsory = models.BooleanField(
        default=False,
        help_text="Міндетті 3 пәннің бірі ме? (Қазақстан тарихы, Мат. сауаттылық, Оқу сауаттылығы)"
    )

    description = models.TextField(blank=True, help_text="Пән бойынша қысқаша түсіндірме")
    icon_class = models.CharField(max_length=100, default='bi-journal-bookmark', help_text="Bootstrap Icons класы")
    default_question_count = models.PositiveIntegerField(default=20, help_text="Емтихандағы сұрақтар саны")
    max_score = models.PositiveIntegerField(default=20, help_text="Пән бойынша максималды балл")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-is_compulsory', 'order', 'name']
        verbose_name = "Пән"
        verbose_name_plural = "Пәндер"

    def __str__(self):
        compulsory_badge = " [Міндетті]" if self.is_compulsory else " [Бейіндік]"
        return f"{self.name}{compulsory_badge}"

    def get_localized_name(self, lang='kk'):
        if lang == 'ru' and self.name_ru: return self.name_ru
        if lang == 'en' and self.name_en: return self.name_en
        if lang == 'uz' and self.name_uz: return self.name_uz
        return self.name_kk or self.name


class ProfileSubjectCombination(models.Model):
    """
    Allowed Profile Subject Pairs (Бейіндік пәндер жұбы).
    Strictly managed in Django to ensure students only pick officially permitted pairs.
    """
    name = models.CharField(
        max_length=200,
        help_text="Жұп атауы (мыс: Математика + Физика (Инженерия & IT))"
    )
    subject_1 = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='combination_first',
        help_text="1-ші бейіндік пән"
    )
    subject_2 = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='combination_second',
        help_text="2-ші бейіндік пән"
    )
    description = models.TextField(blank=True, help_text="Бағыт немесе мамандықтар сипаттамасы")
    is_active = models.BooleanField(default=True, help_text="Таңдауға қолжетімді ме?")

    class Meta:
        unique_together = ('subject_1', 'subject_2')
        verbose_name = "Бейіндік пән жұбы"
        verbose_name_plural = "Бейіндік пән жұптары"

    def clean(self):
        if self.subject_1 == self.subject_2:
            raise ValidationError("1-ші және 2-ші бейіндік пән бірдей бола алмайды!")
        if self.subject_1.is_compulsory or self.subject_2.is_compulsory:
            raise ValidationError("Міндетті пәндерді бейіндік пән ретінде таңдауға болмайды!")

    def __str__(self):
        return f"{self.name} ({self.subject_1.name} + {self.subject_2.name})"


class StudentSubjectSelection(models.Model):
    """
    Student's chosen profile subject pair.
    Every student has 3 compulsory subjects automatically + their chosen 2 profile subjects.
    """
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subject_selection'
    )
    combination = models.ForeignKey(
        ProfileSubjectCombination,
        on_delete=models.PROTECT,
        related_name='student_selections',
        help_text="Таңдалған бейіндік жұп"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Оқушының пән таңдауы"
        verbose_name_plural = "Оқушылардың пән таңдаулары"

    def get_all_five_subjects(self):
        """Returns the list of all 5 subjects: 3 compulsory + 2 profile subjects."""
        compulsory = list(Subject.objects.filter(is_compulsory=True).order_by('order'))
        profile = [self.combination.subject_1, self.combination.subject_2]
        return compulsory + profile

    def __str__(self):
        return f"{self.student.username} -> {self.combination.name}"
