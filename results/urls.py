from django.urls import path
from . import views

app_name = 'results'

urlpatterns = [
    path('attempt/<int:attempt_id>/', views.exam_result_view, name='exam_result'),
    path('history/', views.exam_history_view, name='exam_history'),
    path('mistakes-notebook/', views.mistakes_notebook_view, name='mistakes_notebook'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
]
