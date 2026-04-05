from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now, localtime
from django.contrib import messages
from datetime import date
from .models import Course, ClassSession, Attendance, Notification, Profile, Message
from .forms import ManualCheckinForm, RegistrationForm, ClassSessionForm, MessageForm, NotificationForm, UserUpdateForm
from django.contrib.auth.forms import AuthenticationForm
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from django.db.models import Q
from django.contrib.auth.models import User

@login_required
def dashboard(request):
    today = date.today()
    role = request.user.profile.role

    if role == 'LECTURER':
        today_sessions = ClassSession.objects.filter(course__lecturer=request.user, date=today)
    elif role == 'STUDENT':
        today_sessions = ClassSession.objects.filter(date=today, course__students=request.user)
    else:
        today_sessions = ClassSession.objects.filter(date=today)

    unchecked_sessions = []
    if role == 'STUDENT':
        for session in today_sessions:
            already_checked_in = Attendance.objects.filter(
                student=request.user,
                course=session.course,
                date=session.date
            ).exists()
            if not already_checked_in:
                unchecked_sessions.append(session)

    overall_attendance = 0
    if role == 'STUDENT':
        user_attendances = Attendance.objects.filter(student=request.user)
        present_count = user_attendances.filter(status='present').count()
        overall_attendance = round((present_count / user_attendances.count()) * 100) if user_attendances.count() > 0 else 0

    elif role == 'LECTURER':
        all_courses = Course.objects.filter(lecturer=request.user)
        all_sessions = ClassSession.objects.filter(course__in=all_courses)

        total_classes = all_sessions.count()
        total_possible_attendances = 0
        total_actual_presents = 0

        for session in all_sessions:
            enrolled_students = session.course.students.count()
            total_possible_attendances += enrolled_students
            present_count = Attendance.objects.filter(course=session.course, date=session.date, status='present').count()
            total_actual_presents += present_count

        overall_attendance = round((total_actual_presents / total_possible_attendances) * 100) if total_possible_attendances > 0 else 0

    warning_classes = []
    if role == 'STUDENT':
        warning_threshold = 75
        for course in request.user.courses_enrolled.all():
            course_sessions = ClassSession.objects.filter(course=course)
            if course_sessions.exists():
                attended = Attendance.objects.filter(
                    student=request.user,
                    course=course,
                    status='present'
                ).count()
                percentage = round((attended / course_sessions.count()) * 100)
                if percentage < warning_threshold:
                    warning_classes.append({
                        'course': course,
                        'attendance': percentage
                    })

    session_data = []
    current_time = now().time()
    for session in today_sessions:
        attendance = None
        if role == 'STUDENT':
            attendance = Attendance.objects.filter(
                student=request.user,
                course=session.course,
                date=session.date
            ).first()

        has_checkin = Attendance.objects.filter(session=session, status='present').exists()

        session_data.append({
            'session': session,
            'attendance': attendance,
            'is_ongoing': session.start_time <= current_time <= session.end_time,
            'has_checkin': has_checkin,
        })

    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).count()

    return render(request, 'dashboard/dashboard.html', {
        'session_data': session_data,
        'total_classes': total_classes if role == 'LECTURER' else ClassSession.objects.count(),
        'overall_attendance': overall_attendance,
        'warning_classes': warning_classes,
        'unread_notifications': unread_notifications,
        'unchecked_sessions': unchecked_sessions,
    })


# (Rest of the file remains unchanged)




def search_results(request):
    query = request.GET.get('q')
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(email__icontains=query)
    )

    profiles = Profile.objects.filter(
        Q(registration_number__icontains=query) |
        Q(role__icontains=query)
    )

    # Add more models/fields as needed

    context = {
        'query': query,
        'users': users,
        'profiles': profiles,
    }
    return render(request, 'dashboard/search_results.html', context)


@login_required
def teacher_students_checked_in(request):
    if request.user.profile.role != 'LECTURER':
        return HttpResponse("Unauthorized", status=403)

    courses = request.user.courses_taught.all()
    sessions = ClassSession.objects.filter(course__in=courses)

    student_ids = Attendance.objects.filter(
        session__in=sessions,
        status='present'
    ).values_list('student_id', flat=True).distinct()

    # Prefetch profiles to avoid DB hits in template
    unique_students = User.objects.filter(id__in=student_ids).select_related('profile')

    return render(request, 'dashboard/teacher_students_checked_in.html', {
        'checked_in_students': unique_students
    })



@login_required
def attendance_list(request):
    role = request.user.profile.role
    if role == 'STUDENT':
        courses = request.user.courses_enrolled.all()
    elif role == 'LECTURER':
        courses = Course.objects.filter(lecturer=request.user)
    else:
        courses = Course.objects.all()

    selected_course = request.GET.get('course')
    if selected_course:
        sessions = ClassSession.objects.filter(course_id=selected_course)
    else:
        sessions = ClassSession.objects.filter(course__in=courses)

    if role == 'STUDENT':
        attendances = Attendance.objects.filter(student=request.user, course__in=courses)
    else:
        attendances = Attendance.objects.filter(course__in=courses)

    return render(request, 'dashboard/attendance_list.html', {
        'courses': courses,
        'selected_course': selected_course,
        'attendances': attendances,
    })


@login_required
def checkin(request, session_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    session = get_object_or_404(ClassSession, pk=session_id)

    if Attendance.objects.filter(student=request.user, date=session.date, course=session.course).exists():
        return JsonResponse({'success': False, 'message': 'Already checked in.'})

    Attendance.objects.create(
        student=request.user,
        course=session.course,
        date=session.date,
        time=session.start_time,
        status='present'
    )
    return JsonResponse({'success': True, 'message': 'Checked in!'})

@login_required
def manual_checkin(request):
    if request.method == 'POST':
        form = ManualCheckinForm(user=request.user, data=request.POST)
        if form.is_valid():
            Attendance.objects.create(
                student=form.cleaned_data['student'],
                course=form.cleaned_data['course'],
                date=form.cleaned_data['date'],
                time=form.cleaned_data['time'],
                status=form.cleaned_data['status'],
                reason=form.cleaned_data.get('reason', '')
            )
            return JsonResponse({'success': True, 'message': 'Manual check-in submitted!'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid form submission.'})
    else:
        form = ManualCheckinForm(user=request.user)

    return render(request, 'dashboard/manual_checkin_modal.html', {'form': form})


@login_required
def create_class_session(request):
    if request.user.profile.role != 'LECTURER':
        return redirect('dashboard')

    if request.method == 'POST':
        form = ClassSessionForm(request.user, request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.save()
            messages.success(request, "Class session created successfully.")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid form. Please check your inputs.")
    else:
        form = ClassSessionForm(request.user)

    return render(request, 'dashboard/create_class_session.html', {'form': form})


# Helper to check if user is teacher
def is_teacher(user):
    return user.profile.role == 'LECTURER'

@user_passes_test(is_teacher)
@login_required
def edit_class_session(request, session_id):
    session = get_object_or_404(ClassSession, pk=session_id)

    if request.method == 'POST':
        form = ClassSessionForm(request.user, request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, "Class session updated successfully.")
            return redirect('dashboard')
    else:
        form = ClassSessionForm(request.user, instance=session)

    return render(request, 'dashboard/edit_class_session.html', {'form': form, 'session': session})

@user_passes_test(is_teacher)
@login_required
def delete_class_session(request, session_id):
    session = get_object_or_404(ClassSession, pk=session_id)

    if request.method == 'POST':
        session.delete()
        messages.success(request, "Class session deleted successfully.")
        return redirect('dashboard')

    return render(request, 'dashboard/confirm_delete_session.html', {'session': session})


# notifications/views.py
@login_required
def send_notification(request):
    if request.user.profile.role == 'STUDENT':
        return redirect('view_notifications')  # prevent students from sending

    if request.method == 'POST':
        form = NotificationForm(request.POST, sender=request.user)
        if form.is_valid():
            notif = form.save(commit=False)
            notif.sender = request.user
            notif.save()
            return redirect('view_notifications')
    else:
        form = NotificationForm(sender=request.user)
    return render(request, 'dashboard/send_notification.html', {'form': form})

@login_required
def view_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-timestamp')
    return render(request, 'dashboard/view_notifications.html', {'notifications': notifications})


@login_required
def courses(request):
    role = request.user.profile.role
    if role == 'STUDENT':
        courses = request.user.courses_enrolled.all()
    elif role == 'LECTURER':
        courses = Course.objects.filter(lecturer=request.user)
    else:
        courses = Course.objects.all()

    return render(request, 'dashboard/courses.html', {'courses': courses})


@login_required
def reports(request):
    role = request.user.profile.role
    attendance_data = []

    if role == 'STUDENT':
        courses = request.user.courses_enrolled.all()
        for course in courses:
            sessions = ClassSession.objects.filter(course=course)
            attended = Attendance.objects.filter(student=request.user, course=course, status='present').count()
            total_sessions = sessions.count()
            percentage = round((attended / total_sessions) * 100) if total_sessions > 0 else 0

            attendance_data.append({
                'course': course.name,
                'attended': attended,
                'total': total_sessions,
                'percentage': percentage
            })

        return render(request, 'dashboard/reports.html', {'attendance_data': attendance_data})

    elif role == 'LECTURER':
        courses = Course.objects.filter(lecturer=request.user)
        for course in courses:
            sessions = ClassSession.objects.filter(course=course).order_by('-date')
            for session in sessions:
                students_present = Attendance.objects.filter(session=session, status='present').count()

                attendance_data.append({
                    'course': course.name,
                    'session_date': session.date,
                    'start_time': session.start_time,
                    'end_time': session.end_time,
                    'students_present': students_present,
                })

        return render(request, 'dashboard/report_teacher.html', {'attendance_data': attendance_data})

    else:  # Admins can still see course summaries
        courses = Course.objects.all()
        for course in courses:
            total_sessions = ClassSession.objects.filter(course=course).count()
            sessions_with_checkins = ClassSession.objects.filter(
                course=course,
                attendance__status='present'
            ).distinct().count()
            percentage = round((sessions_with_checkins / total_sessions) * 100) if total_sessions > 0 else 0

            attendance_data.append({
                'course': course.name,
                'attended': sessions_with_checkins,
                'total': total_sessions,
                'percentage': percentage
            })

        return render(request, 'dashboard/reports.html', {'attendance_data': attendance_data})


@login_required
def export_reports_excel(request):
    role = request.user.profile.role

    if role == 'STUDENT':
        courses = request.user.courses_enrolled.all()
    elif role == 'LECTURER':
        courses = Course.objects.filter(lecturer=request.user)
    else:
        courses = Course.objects.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Report"

    # Header row
    headers = ["Course", "Attended", "Total Sessions", "Attendance %"]
    for col_num, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_num, value=header)

    # Data rows
    for row_num, course in enumerate(courses, 2):
        sessions = ClassSession.objects.filter(course=course)
        total_sessions = sessions.count()
        attended = Attendance.objects.filter(student=request.user, course=course, status='present').count()
        percent = round((attended / total_sessions) * 100) if total_sessions > 0 else 0

        ws.cell(row=row_num, column=1, value=course.name)
        ws.cell(row=row_num, column=2, value=attended)
        ws.cell(row=row_num, column=3, value=total_sessions)
        ws.cell(row=row_num, column=4, value=percent)

    # Auto-adjust column width
    for column_cells in ws.columns:
        max_length = max(len(str(cell.value)) for cell in column_cells if cell.value)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = max_length + 2

    # Return Excel file
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=attendance_report.xlsx'
    wb.save(response)
    return response


@login_required
def export_teacher_report_excel(request):
    if request.user.profile.role != 'LECTURER':
        return HttpResponse("Unauthorized", status=403)

    # Create workbook and sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Teacher Report"

    # Header
    headers = ['Course', 'Date', 'Start Time', 'End Time', 'Students Present']
    ws.append(headers)

    # Make headers bold
    for col in range(1, len(headers)+1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    # Populate rows
    courses = Course.objects.filter(teacher=request.user)
    for course in courses:
        sessions = ClassSession.objects.filter(course=course).order_by('-date')
        for session in sessions:
            students_present = Attendance.objects.filter(session=session, status='present').count()
            ws.append([
                course.name,
                session.date.strftime('%Y-%m-%d'),
                str(session.start_time),
                str(session.end_time),
                students_present
            ])

    # Prepare HTTP response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=teacher_report.xlsx'
    wb.save(response)
    return response


@login_required
def messages_page(request):
    return render(request, 'dashboard/messages.html')


@login_required
def settings(request):
    if request.method == 'POST':
        pass
    return render(request, 'dashboard/settings.html')


@require_POST
@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'success': True})


@login_required
def message_view(request):
    messages = Message.objects.filter(recipient=request.user).order_by('-timestamp')
    form = MessageForm()

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            new_message = form.save(commit=False)
            new_message.sender = request.user
            new_message.save()
            return redirect('messages')  # replace with your message URL name

    return render(request, 'dashboard/message.html', {
        'messages': messages,
        'form': form,
    })


@login_required
def export_attendance_excel(request):
    role = request.user.profile.role
    if role == 'STUDENT':
        attendances = Attendance.objects.filter(student=request.user)
    elif role == 'LECTURER':
        attendances = Attendance.objects.filter(course__lecturer=request.user)
    else:
        attendances = Attendance.objects.all()

    # Create an Excel workbook and sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance History"

    # Write header row
    ws.append(['Student', 'Course', 'Date', 'Time', 'Status', 'Reason'])

    # Write attendance rows
    for att in attendances:
        ws.append([
            att.student.username,
            att.course.name,
            att.date.strftime('%Y-%m-%d'),
            att.time.strftime('%H:%M'),
            att.status,
            att.reason or ''
        ])

    # Create response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance_history.xlsx'
    wb.save(response)
    return response

@login_required
def settings(request):
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your account was updated successfully!')
            return redirect('settings')
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'dashboard/settings.html', {'form': form})


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration successful. You can now log in.")
            return redirect('login')
    else:
        form = RegistrationForm()
    return render(request, 'dashboard/register.html', {'form': form})


def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'dashboard/login.html', {'form': form})


def user_logout(request):
    logout(request)
    return redirect('login')
