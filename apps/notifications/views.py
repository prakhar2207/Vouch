
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.conf import settings
from .models import PushSubscription, Notification

class PushSubscriptionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sub_info = request.data
        endpoint = sub_info.get('endpoint')
        keys = sub_info.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return Response({'error': 'Invalid subscription info'}, status=status.HTTP_400_BAD_REQUEST)

        # Update or create
        sub, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={'p256dh': p256dh, 'auth': auth}
        )
        return Response({'success': True, 'created': created})

class NotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifs = Notification.objects.filter(user=request.user)[:50]
        data = [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        } for n in notifs]
        return Response(data)

class NotificationMarkReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(user=request.user, id=pk).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user).update(is_read=True)
        return Response({'success': True})
