from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils.timezone import now, localtime
from django.contrib import messages
from datetime import date
from .models import Course, ClassSession, Attendance, Notification, Profile, Message
from .forms import (
    ManualCheckinForm, RegistrationForm, ClassSessionForm, MessageForm,
    NotificationForm, UserUpdateForm, StudentCourseEnrollmentForm, ManageCourseStudentsForm, CourseForm, CustomLoginForm
)
from django.contrib.auth.forms import AuthenticationForm
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from django.db.models import Q
from django.contrib.auth.models import User

from django.utils.timezone import make_aware
from datetime import datetime

def get_session_status(session):
    now_dt = localtime(now())

    start_dt = make_aware(datetime.combine(session.date, session.start_time))
    end_dt = make_aware(datetime.combine(session.date, session.end_time))

    if now_dt < start_dt:
        return "UPCOMING"
    elif now_dt > end_dt:
        return "CLOSED"
    else:
        return "ACTIVE"

# -------------------------
# Dashboard
# -------------------------
@login_required
def dashboard(request):
    current_dt = localtime(now())
    today = current_dt.date()
    current_time = current_dt.time()
    role = request.user.profile.role

    today_sessions = ClassSession.objects.none()

    if role == 'LECTURER':
        today_sessions = ClassSession.objects.filter(
            course__lecturer=request.user,
            date=today
        )
    elif role == 'STUDENT':
        today_sessions = ClassSession.objects.filter(
            course__students=request.user,
            date=today
        )

    session_data = []
    unchecked_sessions = []

    for session in today_sessions:
        status = get_session_status(session)

        attendance = None
        if role == 'STUDENT':
            attendance = Attendance.objects.filter(
                student=request.user,
                session=session
            ).first()

            # Only allow check-in if ACTIVE
            if status == "ACTIVE" and not attendance:
                unchecked_sessions.append(session)

        session_data.append({
            "session": session,
            "attendance": attendance,
            "session_status": status
        })

    # STUDENT STATS
    overall_attendance = 0
    if role == "STUDENT":
        records = Attendance.objects.filter(student=request.user)
        present = records.filter(status='present').count()
        total = records.count()

        overall_attendance = round((present / total) * 100) if total else 0

    # LECTURER STATS
    lecturer_stats = {}
    if role == "LECTURER":
        sessions = ClassSession.objects.filter(course__lecturer=request.user)

        total_students = sum(s.course.students.count() for s in sessions)
        present = Attendance.objects.filter(
            session__in=sessions,
            status='present'
        ).count()

        lecturer_stats = {
            "attendance_percentage": round((present / total_students) * 100) if total_students else 0,
            "checked_in_students": present,
            "total_students": total_students,
            "absent_students": total_students - present
        }

    return render(request, 'dashboard/dashboard.html', {
        "session_data": session_data,
        "unchecked_sessions": unchecked_sessions,
        "overall_attendance": overall_attendance,
        "lecturer_stats": lecturer_stats,
        "role": role
    })

# -------------------------
# Attendance List (STUDENT ONLY 🔥)
# -------------------------
@login_required
def attendance_list(request):
    if request.user.profile.role != 'STUDENT':
        return redirect('dashboard')  # 🚫 block lecturers

    courses = request.user.courses_enrolled.all()
    selected_course = request.GET.get('course')

    if selected_course:
        attendances = Attendance.objects.filter(
            student=request.user,
            course_id=selected_course
        )
    else:
        attendances = Attendance.objects.filter(
            student=request.user,
            course__in=courses
        )

    return render(request, 'dashboard/attendance_list.html', {
        'courses': courses,
        'selected_course': selected_course,
        'attendances': attendances,
    })

# -------------------------
# Search
# -------------------------
def search_results(request):
    query = request.GET.get('q', '')
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(email__icontains=query)
    )
    profiles = Profile.objects.filter(
        Q(registration_number__icontains=query) |
        Q(role__icontains=query)
    )
    context = {
        'query': query,
        'users': users,
        'profiles': profiles,
    }
    return render(request, 'dashboard/search_results.html', context)


# -------------------------
# Teacher: Students Checked In
# -------------------------
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

    unique_students = User.objects.filter(id__in=student_ids).select_related('profile')

    return render(request, 'dashboard/teacher_students_checked_in.html', {
        'checked_in_students': unique_students
    })


# -------------------------
# Attendance List
# -------------------------
@login_required
def attendance_list(request):
    role = request.user.profile.role

    if role == "STUDENT":
        courses = request.user.courses_enrolled.all()
        attendances = Attendance.objects.filter(student=request.user, course__in=courses)

    elif role == "LECTURER":
        courses = Course.objects.filter(lecturer=request.user)
        attendances = Attendance.objects.filter(course__in=courses)

    else:
        courses = Course.objects.all()
        attendances = Attendance.objects.all()

    selected_course = request.GET.get("course")
    if selected_course:
        attendances = attendances.filter(course_id=selected_course)

    return render(request, "dashboard/attendance_list.html", {
        "courses": courses,
        "attendances": attendances,
        "selected_course": selected_course
    })


# -------------------------
# Check-in (via UI button)
# -------------------------

@login_required
def checkin(request, session_id):
    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    session = get_object_or_404(ClassSession, id=session_id)

    current_dt = localtime(now())
    status = get_session_status(session)

    if status != "ACTIVE":
        messages.error(request, "This session is not active.")
        return redirect("dashboard")

    Attendance.objects.update_or_create(
        student=request.user,
        session=session,
        defaults={
            "course": session.course,
            "date": session.date,
            "time": current_dt.time(),
            "status": "present",
            "marked_by": request.user
        }
    )

    return redirect("checkin_success")


@login_required
def checkin_success(request):
    return render(request, 'dashboard/checkin_success.html')    
# -------------------------
# Manual Check-in (Lecturer via UI form)
# -------------------------

@login_required
def manual_checkin(request):
    if request.user.profile.role != "LECTURER":
        return redirect("dashboard")

    if request.method == "POST":
        form = ManualCheckinForm(request.POST, user=request.user)

        if form.is_valid():
            student = form.cleaned_data["student"]
            course = form.cleaned_data["course"]
            date_val = form.cleaned_data["date"]
            time_val = form.cleaned_data["time"]
            status = form.cleaned_data["status"]
            reason = form.cleaned_data["reason"]

            # FIXED: get correct session (LATEST + EXACT MATCH)
            session = ClassSession.objects.filter(
                course=course,
                date=date_val
            ).order_by("-start_time").first()

            if not session:
                messages.error(request, "No session found.")
                return redirect("attendance_list")

            current_dt = localtime(now())
            session_status = get_session_status(session)

            if session_status != "ACTIVE":
                messages.error(request, "Cannot mark attendance outside active session.")
                return redirect("attendance_list")

            Attendance.objects.update_or_create(
                student=student,
                session=session,
                defaults={
                    "course": course,
                    "date": date_val,
                    "time": time_val,
                    "status": status,
                    "reason": reason,
                    "marked_by": request.user
                }
            )

            messages.success(request, "Attendance marked successfully.")
            return redirect("attendance_list")

    else:
        form = ManualCheckinForm(user=request.user)

    return render(request, "dashboard/manual_checkin_modal.html", {
        "form": form
    })

# -------------------------
# Create Class Session (Lecturer)
# -------------------------
@login_required
def create_class_session(request):
    if request.user.profile.role != "LECTURER":
        return redirect("dashboard")

    if request.method == "POST":
        form = ClassSessionForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Session created")
            return redirect("dashboard")

    else:
        form = ClassSessionForm(request.user)

    return render(request, "dashboard/create_class_session.html", {"form": form})

# -------------------------
# Edit / Delete Class Session (Lecturer)
# -------------------------
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


@login_required
def courses(request):
    role = request.user.profile.role

    # -------------------------
    # STUDENT LOGIC
    # -------------------------
    if role == 'STUDENT':
        enrolled_courses = request.user.courses_enrolled.all()
        available_courses = Course.objects.exclude(students=request.user)

        if request.method == 'POST':
            action = request.POST.get('action')
            course_id = request.POST.get('course_id')

            if course_id:
                course = get_object_or_404(Course, id=course_id)

                if action == 'enroll':
                    course.students.add(request.user)
                    messages.success(request, f"You have enrolled in {course.name}")

                elif action == 'unenroll':
                    course.students.remove(request.user)
                    messages.success(request, f"You have unenrolled from {course.name}")

            return redirect('courses')

        context = {
            'role': role,
            'enrolled_courses': enrolled_courses,
            'available_courses': available_courses,
        }

    # -------------------------
    # LECTURER LOGIC
    # -------------------------
    elif role == 'LECTURER':
        lecturer_courses = Course.objects.filter(lecturer=request.user)
        all_students = User.objects.filter(profile__role='STUDENT')

        if request.method == 'POST':
            action = request.POST.get('action')
            course_id = request.POST.get('course_id')
            student_id = request.POST.get('student_id')

            if course_id:
                course = get_object_or_404(Course, id=course_id, lecturer=request.user)

                if action == 'add_student' and student_id:
                    student = get_object_or_404(User, id=student_id)
                    course.students.add(student)
                    messages.success(request, f"Student added to {course.name}")

                elif action == 'remove_student' and student_id:
                    student = get_object_or_404(User, id=student_id)
                    course.students.remove(student)
                    messages.success(request, f"Student removed from {course.name}")

            return redirect('courses')

        context = {
            'role': role,
            'lecturer_courses': lecturer_courses,
            'all_students': all_students,
        }

    # -------------------------
    # ADMIN LOGIC
    # -------------------------
    else:
        all_courses = Course.objects.all()

        context = {
            'role': role,
            'all_courses': all_courses,
        }

    return render(request, 'dashboard/courses.html', context)

# -------------------------
# Add Course (Lecturer)
# -------------------------
@login_required
def add_course(request):
    if request.user.profile.role != 'LECTURER':
        return HttpResponse("Unauthorized", status=403)

    if request.method == 'POST':
        form = CourseForm(request.POST)

        if form.is_valid():
            course = form.save(commit=False)
            course.lecturer = request.user  # auto assign lecturer
            course.save()
            form.save_m2m()

            print("COURSE SAVED:", course)  # debug
            messages.success(request, "Course created successfully!")
            return redirect('courses')
        else:
            print("FORM ERRORS:", form.errors)
            messages.error(request, form.errors)

    else:
        form = CourseForm()

    return render(request, 'dashboard/add_course.html', {'form': form})
# -------------------------
# Notifications
# -------------------------
@login_required
def send_notification(request):
    if request.user.profile.role == 'STUDENT':
        return redirect('view_notifications')

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


@require_POST
@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'success': True})


# -------------------------
# Reports
# -------------------------

@login_required
def reports(request):
    role = request.user.profile.role
    attendance_data = []

    # =========================
    # STUDENT REPORT
    # =========================
    if role == 'STUDENT':
        courses = request.user.courses_enrolled.all()

        for course in courses:
            total_sessions = ClassSession.objects.filter(course=course).count()

            attended = Attendance.objects.filter(
                student=request.user,
                session__course=course,
                status__iexact='present'
            ).count()

            percentage = round(
                (attended / total_sessions) * 100
            ) if total_sessions > 0 else 0

            attendance_data.append({
                'course': course.name,
                'attended': attended,
                'total': total_sessions,
                'percentage': percentage
            })

        return render(request, 'dashboard/reports.html', {
            'attendance_data': attendance_data
        })

    # =========================
    # LECTURER REPORT
    # =========================
    elif role == 'LECTURER':
        courses = Course.objects.filter(lecturer=request.user)

        for course in courses:
            sessions = ClassSession.objects.filter(course=course).order_by('-date')

            for session in sessions:
                students_present = Attendance.objects.filter(
                    session=session,
                    status__iexact='present'
                ).count()

                attendance_data.append({
                    'course': course.name,
                    'session_date': session.date,
                    'start_time': session.start_time,
                    'end_time': session.end_time,
                    'students_present': students_present,
                })

        return render(request, 'dashboard/report_teacher.html', {
            'attendance_data': attendance_data
        })

    # =========================
    # ADMIN REPORT
    # =========================
    else:
        courses = Course.objects.all()

        for course in courses:
            total_sessions = ClassSession.objects.filter(course=course).count()

            total_present = Attendance.objects.filter(
                session__course=course,
                status__iexact='present'
            ).count()

            total_records = Attendance.objects.filter(
                session__course=course
            ).count()

            percentage = round(
                (total_present / total_records) * 100
            ) if total_records > 0 else 0

            attendance_data.append({
                'course': course.name,
                'attended': total_present,
                'total': total_records,
                'percentage': percentage
            })

        return render(request, 'dashboard/reports.html', {
            'attendance_data': attendance_data
        })


# -------------------------
# Export Reports (Student / Admin)
# -------------------------
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

    headers = ["Course", "Attended", "Total Sessions", "Attendance %"]
    for col_num, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_num, value=header)

    for row_num, course in enumerate(courses, 2):
        sessions = ClassSession.objects.filter(course=course)
        total_sessions = sessions.count()
        attended = Attendance.objects.filter(
            student=request.user, course=course, status='present'
        ).count()
        percent = round((attended / total_sessions) * 100) if total_sessions > 0 else 0

        ws.cell(row=row_num, column=1, value=course.name)
        ws.cell(row=row_num, column=2, value=attended)
        ws.cell(row=row_num, column=3, value=total_sessions)
        ws.cell(row=row_num, column=4, value=percent)

    for column_cells in ws.columns:
        max_length = max(len(str(cell.value)) for cell in column_cells if cell.value)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = max_length + 2

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance_report.xlsx'
    wb.save(response)
    return response


# -------------------------
# Export Teacher Report (fixed: was using Course.objects.filter(teacher=...) — now 'lecturer')
# -------------------------
@login_required
def export_teacher_report_excel(request):
    if request.user.profile.role != 'LECTURER':
        return HttpResponse("Unauthorized", status=403)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Teacher Report"

    headers = ['Course', 'Date', 'Start Time', 'End Time', 'Students Present']
    ws.append(headers)

    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True)

    # Fixed: changed 'teacher' to 'lecturer' to match the Course model field
    courses = Course.objects.filter(lecturer=request.user)
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

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=teacher_report.xlsx'
    wb.save(response)
    return response


# -------------------------
# Export Attendance History (all roles)
# -------------------------
@login_required
def export_attendance_excel(request):
    role = request.user.profile.role
    if role == 'STUDENT':
        attendances = Attendance.objects.filter(student=request.user)
    elif role == 'LECTURER':
        attendances = Attendance.objects.filter(course__lecturer=request.user)
    else:
        attendances = Attendance.objects.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance History"

    ws.append(['Student', 'Course', 'Date', 'Time', 'Status', 'Reason'])

    for att in attendances:
        ws.append([
            att.student.username,
            att.course.name,
            att.date.strftime('%Y-%m-%d'),
            att.time.strftime('%H:%M'),
            att.status,
            att.reason or ''
        ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=attendance_history.xlsx'
    wb.save(response)
    return response


# -------------------------
# Messages
# -------------------------
@login_required
def messages_page(request):
    return render(request, 'dashboard/messages.html')


@login_required
def message_view(request):
    user_messages = Message.objects.filter(recipient=request.user).order_by('-timestamp')
    form = MessageForm()

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            new_message = form.save(commit=False)
            new_message.sender = request.user
            new_message.save()
            return redirect('messages')

    return render(request, 'dashboard/message.html', {
        'messages': user_messages,
        'form': form,
    })


# -------------------------
# Settings
# -------------------------
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


# -------------------------
# Auth: Register, Login, Logout
# -------------------------
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
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)

            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid password")

        except User.DoesNotExist:
            messages.error(request, "User with this email does not exist")

    return render(request, 'dashboard/login.html')

def user_logout(request):
    logout(request)
    return redirect('login')