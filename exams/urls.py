from django.urls import path
from . import views

app_name = 'exams'

urlpatterns = [
    path('dashboard/', views.student_dashboard_view, name='student_dashboard'),
    path('start-simulation/', views.start_full_simulation_view, name='start_full_simulation'),
    path('start-practice/<int:subject_id>/', views.start_practice_view, name='start_practice'),
    path('interface/<int:attempt_id>/', views.exam_interface_view, name='exam_interface'),
    path('submit/<int:attempt_id>/', views.submit_exam_view, name='submit_exam'),

    # APIs for AJAX testing interactions
    path('api/save-answer/', views.save_answer_api, name='api_save_answer'),
    path('api/flag-question/', views.flag_question_api, name='api_flag_question'),
    path('api/practice-check/', views.practice_check_answer_api, name='api_practice_check'),
]
