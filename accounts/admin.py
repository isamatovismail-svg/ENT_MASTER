from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_teacher_approved', 'is_premium', 'is_staff')
    list_filter = ('role', 'is_teacher_approved', 'is_premium', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('ENT Master Қосымша мәліметтері', {
            'fields': ('role', 'phone', 'avatar', 'target_university', 'target_score', 'is_teacher_approved', 'is_premium', 'premium_until')
        }),
    )
