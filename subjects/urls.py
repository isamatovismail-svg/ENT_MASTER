from django.urls import path
from . import views

app_name = 'subjects'

urlpatterns = [
    path('select/', views.select_subjects_view, name='select_subjects'),
    path('', views.subjects_list_view, name='subjects_list'),
]
