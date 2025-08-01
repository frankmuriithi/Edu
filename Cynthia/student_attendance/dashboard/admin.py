from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Profile, Course, Attendance, Notification

# Inline admin for Profile
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'

# Extend User admin to show Profile info
class CustomUserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else "N/A"
    get_role.short_description = 'Role'

    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active')

# Unregister the original User admin
admin.site.unregister(User)

# Register the updated User admin
admin.site.register(User, CustomUserAdmin)

# Register other models
admin.site.register(Course)
admin.site.register(Attendance)
admin.site.register(Notification)
