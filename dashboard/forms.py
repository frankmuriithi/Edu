from django import forms
from django.contrib.auth.models import User
from .models import Profile, Attendance, Course, ClassSession, Message, Notification


# -------------------------
# Manual Check-in Form (for Lecturers)
# -------------------------
from django import forms
from .models import Attendance, Course
from django.contrib.auth.models import User
from django.utils.text import slugify


class ManualCheckinForm(forms.ModelForm):
    student = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Student"
    )

    class Meta:
        model = Attendance
        fields = ['student', 'course', 'date', 'time', 'status', 'reason']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['course'].queryset = Course.objects.filter(lecturer=user)

        # Always start with empty unless course is selected
        self.fields['student'].queryset = User.objects.filter(profile__role='STUDENT')

        # If course is selected (POST or initial form edit)
        course_id = None

        if 'course' in self.data:
            course_id = self.data.get('course')
        elif self.initial.get('course'):
            course_id = self.initial.get('course')

        if course_id:
            try:
                course = Course.objects.get(id=course_id)
                self.fields['student'].queryset = course.students.all()
            except Course.DoesNotExist:
                self.fields['student'].queryset = User.objects.none()


class RegistrationForm(forms.ModelForm):
    full_name = forms.CharField(
        max_length=150,
        label="Full Name",
        help_text="Enter your first and last name (e.g. Jose Kim)"
    )

    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)

    registration_number = forms.CharField(max_length=20, required=False)
    staff_number = forms.CharField(max_length=30, required=False)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password']

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name').strip()
        parts = name.split()

        if len(parts) < 2:
            raise forms.ValidationError("Enter at least first and last name.")

        return name

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')

        if role == 'STUDENT' and not cleaned_data.get('registration_number'):
            self.add_error('registration_number', "Required for students.")

        if role == 'LECTURER' and not cleaned_data.get('staff_number'):
            self.add_error('staff_number', "Required for lecturers.")

        return cleaned_data

    def generate_username(self, full_name):
        base_username = slugify(full_name)  # jose-kim
        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}-{counter}"
            counter += 1

        return username

    def save(self, commit=True):
        user = super().save(commit=False)

        full_name = self.cleaned_data['full_name'].strip().split()

        # Split names
        user.first_name = full_name[0]
        user.last_name = " ".join(full_name[1:])

        # 🔥 AUTO USERNAME (no spaces, always valid)
        user.username = self.generate_username(" ".join(full_name))

        user.set_password(self.cleaned_data['password'])

        if commit:
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            role = self.cleaned_data.get('role')
            profile.role = role

            if role == 'STUDENT':
                profile.registration_number = self.cleaned_data.get('registration_number')
                profile.staff_number = None

            elif role == 'LECTURER':
                profile.staff_number = self.cleaned_data.get('staff_number')
                profile.registration_number = None

            else:
                profile.registration_number = None
                profile.staff_number = None

            profile.save()

        return user




class CustomLoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    registration_number = forms.CharField(required=False)
    staff_number = forms.CharField(required=False)

    def clean(self):
        cleaned_data = super().clean()

        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        reg_no = cleaned_data.get('registration_number')
        staff_no = cleaned_data.get('staff_number')

        user = authenticate(username=username, password=password)

        if not user:
            raise forms.ValidationError("Invalid username or password.")

        profile = user.profile

        # 🔥 VALIDATION BASED ON ROLE
        if profile.role == 'STUDENT':
            if not reg_no:
                raise forms.ValidationError("Registration number is required.")
            if profile.registration_number != reg_no:
                raise forms.ValidationError("Invalid registration number.")

        elif profile.role == 'LECTURER':
            if not staff_no:
                raise forms.ValidationError("Staff number is required.")
            if profile.staff_number != staff_no:
                raise forms.ValidationError("Invalid staff number.")

        self.user = user
        return cleaned_data

    def get_user(self):
        return self.user
    
        
# -------------------------
# Class Session Form (for Lecturers)
# -------------------------
class ClassSessionForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ['course', 'date', 'start_time', 'end_time', 'location']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'location': forms.TextInput(attrs={'placeholder': 'e.g. Room 202'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            lecturer_courses = Course.objects.filter(lecturer=user)
            self.fields['course'].queryset = lecturer_courses
            if not lecturer_courses.exists():
                self.fields['course'].help_text = "⚠️ You are not assigned to any courses."
        except AttributeError:
            self.fields['course'].queryset = Course.objects.none()
            self.fields['course'].help_text = "⚠️ Profile not linked to lecturer."


# -------------------------
# -------------------------
class StudentCourseEnrollmentForm(forms.Form):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Select Courses to Enroll In",
        help_text="Choose one or more courses you want to join."
    )

    def __init__(self, student, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show courses the student is NOT already enrolled in
        already_enrolled = student.courses_enrolled.all()
        self.fields['courses'].queryset = Course.objects.exclude(
            id__in=already_enrolled.values_list('id', flat=True)
        )


# -------------------------
# Manage Course Students Form (for Lecturers)
# Allows lecturers to add or remove students from their courses via the system UI.
# -------------------------
class ManageCourseStudentsForm(forms.Form):
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Enrolled Students",
        help_text="Check students who should be enrolled in this course. Uncheck to remove them."
    )

    def __init__(self, course, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show all students in the system
        all_students = User.objects.filter(profile__role='STUDENT').select_related('profile')
        self.fields['students'].queryset = all_students
        # Pre-select currently enrolled students
        if not kwargs.get('data'):
            self.fields['students'].initial = course.students.values_list('id', flat=True)


class CourseForm(forms.ModelForm):
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(profile__role='STUDENT'),
        widget=forms.SelectMultiple(attrs={'size': 5}),
        required=False
    )

    class Meta:
        model = Course
        fields = ['name', 'code', 'description', 'students']

    def save(self, commit=True):
        course = super().save(commit=False)

        if commit:
            course.save()
            self.save_m2m()  # saves students

        return course
    
# -------------------------
# Message Form
# -------------------------
class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['recipient', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your message...'}),
        }


# -------------------------
# Notification Form
# -------------------------
class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ['recipient', 'message']

    def __init__(self, *args, **kwargs):
        sender = kwargs.pop('sender', None)
        super().__init__(*args, **kwargs)

        if sender:
            role = sender.profile.role
            if role == 'ADMIN':
                self.fields['recipient'].queryset = User.objects.exclude(id=sender.id)
            elif role == 'LECTURER':
                self.fields['recipient'].queryset = User.objects.filter(profile__role='STUDENT')
            else:
                self.fields['recipient'].queryset = User.objects.none()


# -------------------------
# User Update Form
# -------------------------
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }