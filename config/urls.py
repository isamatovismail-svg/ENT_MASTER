"""
URL configuration for ENT MASTER project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from accounts.views import home_view
from exams.views import student_dashboard_view

urlpatterns = [
    # Language change view (handles switching between kk, ru, en, uz)
    path('i18n/', include('django.conf.urls.i18n')),

    # Django built-in admin
    path('admin/', admin.site.urls),

    # Public homepage
    path('', home_view, name='home'),

    # Direct convenient dashboard URL
    path('dashboard/', student_dashboard_view, name='student_dashboard'),

    # Domain apps
    path('accounts/', include('accounts.urls')),
    path('subjects/', include('subjects.urls')),
    path('questions/', include('questions.urls')),
    path('exams/', include('exams.urls')),
    path('results/', include('results.urls')),
    path('payments/', include('payments.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
