from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# -------------------------
# User Profile with Roles
# -------------------------
class Profile(models.Model):
    ROLE_CHOICES = [
        ('STUDENT', 'Student'),
        ('LECTURER', 'Lecturer'),
        ('ADMIN', 'Administrator'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    registration_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    staff_number = models.CharField(max_length=30, unique=True, null=True, blank=True)  # For lecturers
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=30, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username


# Automatically create or update profile when User is created or saved
@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()


# -------------------------
# Course Model
# -------------------------
class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    lecturer = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        limit_choices_to={'profile__role': 'LECTURER'},
        related_name='courses_taught'
    )
    students = models.ManyToManyField(
        User, related_name='courses_enrolled', blank=True,
        limit_choices_to={'profile__role': 'STUDENT'}
    )

    def __str__(self):
        return f"{self.code} - {self.name}"


# -------------------------
# Class Session Model
# -------------------------
class ClassSession(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=100)

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.course} on {self.date} at {self.start_time}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    reason = models.TextField(blank=True, null=True)

    # ✅ NEW FIELD
    marked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendance"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'session')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student} - {self.course.name} on {self.date}: {self.status}"
# -------------------------
# Notification Model
# -------------------------
class Notification(models.Model):
    sender = models.ForeignKey(User, related_name='sent_notifications', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_notifications', on_delete=models.CASCADE, null=True)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"From {self.sender} to {self.recipient} at {self.timestamp}"


# -------------------------
# Message Model
# -------------------------
class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'From {self.sender} to {self.recipient} at {self.timestamp}'