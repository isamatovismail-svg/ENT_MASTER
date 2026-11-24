from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """
    Custom User Model for ENT MASTER platform.
    Supports three user roles: Student, Teacher, and Administrator.
    """
    class Role(models.TextChoices):
        STUDENT = 'STUDENT', 'Оқушы / Student'
        TEACHER = 'TEACHER', 'Мұғалім / Teacher'
        ADMIN = 'ADMIN', 'Әкімші / Administrator'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text="Пайдаланушының рөлі: Оқушы, Мұғалім немесе Әкімші"
    )

    phone = models.CharField(
        max_length=25,
        blank=True,
        help_text="Байланыс телефон нөмірі"
    )

    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        help_text="Жеке профиль суреті"
    )

    target_university = models.CharField(
        max_length=200,
        blank=True,
        help_text="Түскісі келетін мақсатты университет (мыс: ҚазҰУ, СДУ, т.б.)"
    )

    target_score = models.PositiveIntegerField(
        default=130,
        help_text="Мақсатты ҰБТ балы (0 - 140)"
    )

    is_teacher_approved = models.BooleanField(
        default=False,
        help_text="Мұғалім аккаунтын әкімші растады ма? Расталмаған мұғалім сұрақ қоса алмайды."
    )

    is_premium = models.BooleanField(
        default=False,
        help_text="Премиум жазылым мәртебесі"
    )

    premium_until = models.DateField(
        null=True,
        blank=True,
        help_text="Премиум мерзімі аяқталатын күн"
    )

    def is_student(self):
        return self.role == self.Role.STUDENT

    def is_teacher(self):
        return self.role == self.Role.TEACHER

    def is_administrator(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def save(self, *args, **kwargs):
        # Auto-approve administrators and students by default
        if self.is_superuser or self.role == self.Role.ADMIN or self.role == self.Role.STUDENT:
            self.is_teacher_approved = True
        super().save(*args, **kwargs)

    def __str__(self):
        display_name = self.get_full_name() or self.username
        return f"{display_name} ({self.get_role_display()})"
