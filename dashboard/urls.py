from django.urls import path
from . import views
from .views import message_view

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('attendance/', views.attendance_list, name='attendance_list'),
    path('checkin/<int:session_id>/', views.checkin, name='checkin'),
    path('manual-checkin/', views.manual_checkin, name='manual_checkin'),
    path('create-session/', views.create_class_session, name='create_session'),
    path('session/edit/<int:session_id>/', views.edit_class_session, name='edit_session'),
    path('session/delete/<int:session_id>/', views.delete_class_session, name='delete_session'),
    path('search/', views.search_results, name='search_results'),
    path('notifications/', views.view_notifications, name='view_notifications'),  # ✅
    path('send/', views.send_notification, name='send_notification'),              # ✅
    path('courses/', views.courses, name='courses'),
    path('reports/', views.reports, name='reports'),
    path('export-report/', views.export_reports_excel, name='export_report'),
    path('reports/export/excel/', views.export_teacher_report_excel, name='export_teacher_report_excel'),
    path('messages/', message_view, name='messages'),
    path('students/', views.teacher_students_checked_in, name='teacher_students_checked_in'),
    path('settings/', views.settings, name='settings'),
    path('export-attendance/', views.export_attendance_excel, name='export_attendance'),
    path('login/', views.user_login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.user_logout, name='logout'),
    path('add-course/', views.add_course, name='add_course'),
]
