from django.urls import path
from . import views
from . import admin_panel_views

urlpatterns = [
    path('register/student/', views.register_student_view, name='register_student'),
    path('register/teacher/', views.register_teacher_view, name='register_teacher'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard-redirect/', views.dashboard_redirect_view, name='dashboard_redirect'),
    path('profile/', views.profile_view, name='profile'),
    path('teacher/pending/', views.teacher_pending_view, name='teacher_pending'),

    # Admin Dashboard URLs
    path('admin-panel/', admin_panel_views.admin_panel_dashboard, name='admin_panel_dashboard'),
    path('admin-panel/teachers/approve/<int:teacher_id>/', admin_panel_views.approve_teacher_view, name='approve_teacher'),
    path('admin-panel/teachers/reject/<int:teacher_id>/', admin_panel_views.reject_teacher_view, name='reject_teacher'),
    path('admin-panel/questions/approve/<int:question_id>/', admin_panel_views.approve_question_view, name='approve_question'),
    path('admin-panel/questions/reject/<int:question_id>/', admin_panel_views.reject_question_view, name='reject_question'),
]
