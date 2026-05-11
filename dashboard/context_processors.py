from .models import Notification, Message

def notification_counts(request):
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

        unread_messages = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

        return {
            'unread_notifications': unread_notifications,
            'unread_messages': unread_messages
        }

    return {}