from django import forms
from django.contrib.auth.models import User
from .models import Profile, Attendance, Course, ClassSession, Message, Notification


class ManualCheckinForm(forms.ModelForm):
    student = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Student",
        help_text="Select a student from the course."
    )

    class Meta:
        model = Attendance
        fields = ['student', 'course', 'date', 'time', 'status', 'reason']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}),
            'reason': forms.Textarea(attrs={'placeholder': 'Reason if absent...', 'rows': 2}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filter courses taught by the current teacher
        teacher_courses = Course.objects.filter(teacher=user)
        self.fields['course'].queryset = teacher_courses

        # If a course is pre-selected (POST), limit students to enrolled in that course
        if 'course' in self.data:
            try:
                course_id = int(self.data.get('course'))
                course = Course.objects.get(id=course_id, teacher=user)
                self.fields['student'].queryset = course.students.all()
            except (ValueError, Course.DoesNotExist):
                self.fields['student'].queryset = User.objects.none()
        else:
            self.fields['student'].queryset = User.objects.none()


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)
    registration_number = forms.CharField(max_length=20, required=False)  # Made optional by default

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean_registration_number(self):
        role = self.cleaned_data.get('role')
        reg_no = self.cleaned_data.get('registration_number')

        if role == 'STUDENT' and not reg_no:
            raise forms.ValidationError("Registration number is required for students.")

        # If not student, registration number should be empty
        if role in ['LECTURER', 'ADMIN']:
            return None  # Return None

        return reg_no

    def save(self, commit=True):
       user = super().save(commit=False)
       user.set_password(self.cleaned_data['password'])

       if commit:
        user.save()

        # Ensure profile exists
        profile, created = Profile.objects.get_or_create(user=user)
        profile.role = self.cleaned_data['role']

        # Handle registration_number correctly
        if profile.role == 'STUDENT':
            profile.registration_number = self.cleaned_data['registration_number']
        else:
            profile.registration_number = None  # or None, depending on model definition

        profile.save()

       return user

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
            self.fields['course'].help_text = "⚠️ Profile not linked to teacher."


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['recipient', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your message...'}),
        }


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

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
