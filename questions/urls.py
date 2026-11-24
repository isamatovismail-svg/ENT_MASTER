from django.urls import path
from . import views

urlpatterns = [
    path('teacher/', views.teacher_questions_list_view, name='teacher_questions_list'),
    path('teacher/create/', views.teacher_question_create_view, name='teacher_question_create'),
    path('import/csv/', views.question_import_view, name='question_import_csv'),
]
