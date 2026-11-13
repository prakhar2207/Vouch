import json
import base64
import urllib.request
import urllib.error
import ssl
import logging
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """
    Transactional Email Backend using Resend's REST API over HTTPS (Port 443).
    Bypasses cloud provider firewall restrictions on raw SMTP ports (25, 465, 587).
    """

    def __init__(self, api_key=None, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or getattr(settings, 'RESEND_API_KEY', None)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        if not self.api_key:
            err = "RESEND_API_KEY is not configured in settings or environment."
            logger.error(err)
            if self.fail_silently:
                return 0
            raise ValueError(err)

        sent_count = 0
        for message in email_messages:
            try:
                if self._send_single(message):
                    sent_count += 1
            except Exception as e:
                logger.error(f"Resend delivery failed for {message.to}: {e}")
                if not self.fail_silently:
                    raise

        return sent_count

    def _send_single(self, message):
        url = "https://api.resend.com/emails"

        # Determine primary recipient list
        recipients = list(message.to)
        if not recipients:
            return False

        # Format from address: if using onboarding default, sanitize
        from_email = message.from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'SriLekh <onboarding@resend.dev>')

        payload = {
            "from": from_email,
            "to": recipients,
            "subject": message.subject or "",
        }

        if message.body:
            payload["text"] = message.body

        # Extract HTML alternative if present
        if hasattr(message, 'alternatives'):
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    payload["html"] = content
                    break

        # Reply-To header
        if message.reply_to:
            payload["reply_to"] = message.reply_to if isinstance(message.reply_to, str) else message.reply_to[0]

        # Extra headers
        if hasattr(message, 'extra_headers') and message.extra_headers:
            payload["headers"] = {k: str(v) for k, v in message.extra_headers.items() if not k.lower().startswith('content-')}

        # Attachments if present
        if hasattr(message, 'attachments') and message.attachments:
            payload_attachments = []
            for att in message.attachments:
                if isinstance(att, tuple) and len(att) >= 2:
                    filename = att[0]
                    content = att[1]
                    if isinstance(content, str):
                        content = content.encode('utf-8')
                    b64_content = base64.b64encode(content).decode('ascii')
                    payload_attachments.append({
                        "filename": filename,
                        "content": b64_content,
                    })
            if payload_attachments:
                payload["attachments"] = payload_attachments

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "SriLekh-ERP/1.0"
            },
            method="POST"
        )

        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
                resp_data = json.loads(res.read().decode('utf-8'))
                resend_id = resp_data.get('id')
                logger.info(f"Resend accepted email to {recipients}: id={resend_id}")
                if hasattr(message, 'extra_headers') and resend_id:
                    message.extra_headers['X-Resend-ID'] = resend_id
                return True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='replace')
            logger.error(f"Resend API error (HTTP {e.code}): {err_body}")
            raise RuntimeError(f"Resend API error (HTTP {e.code}): {err_body}") from e
