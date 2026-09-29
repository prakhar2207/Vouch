import json
from pywebpush import webpush, WebPushException
from django.conf import settings
from .models import PushSubscription, Notification
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def send_notification(user, title, message, link=None):
        Notification.objects.create(user=user, title=title, message=message, link=link)
        subs = PushSubscription.objects.filter(user=user)
        payload = json.dumps({'title': title, 'body': message, 'url': link})
        for sub in subs:
            try:
                webpush(
                    subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={'sub': settings.VAPID_SUBJECT}
                )
            except WebPushException as ex:
                if ex.response and getattr(ex.response, 'status_code', 500) in [404, 410]:
                    sub.delete()
                else:
                    logger.error(str(ex))
