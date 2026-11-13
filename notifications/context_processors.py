from django.db.models import Count, Max, Q

from .models import Notification


def inbox(request):
    if not request.user.is_authenticated:
        return {}
    stats = Notification.objects.current().filter(recipient=request.user).aggregate(unread=Count("pk", filter=Q(read_at__isnull=True)), latest=Max("pk"))
    return {"notification_unread_count": stats["unread"], "notification_latest_id": stats["latest"] or 0}
