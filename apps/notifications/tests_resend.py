import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from django.core.mail import EmailMultiAlternatives
from apps.notifications.backends.resend_backend import ResendEmailBackend


class ResendEmailBackendTests(SimpleTestCase):
    def test_missing_api_key_raises_error(self):
        backend = ResendEmailBackend(api_key=None, fail_silently=False)
        msg = EmailMultiAlternatives("Subject", "Body", "from@example.com", ["to@example.com"])
        with self.assertRaises(ValueError):
            backend.send_messages([msg])

    def test_send_messages_empty_list(self):
        backend = ResendEmailBackend(api_key="re_test_123")
        self.assertEqual(backend.send_messages([]), 0)

    @patch("urllib.request.urlopen")
    def test_successful_http_send(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"id": "resend_msg_001"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        backend = ResendEmailBackend(api_key="re_test_key_xyz")
        msg = EmailMultiAlternatives(
            subject="Test OTP Code",
            body="Your OTP code is 654321",
            from_email="SriLekh Support <support@srilekh.com>",
            to=["user@example.com"],
            reply_to=["support@srilekh.com"],
        )
        msg.attach_alternative("<p>Your OTP code is <b>654321</b></p>", "text/html")
        msg.attach("invoice.txt", b"Hello invoice", "text/plain")

        sent = backend.send_messages([msg])
        self.assertEqual(sent, 1)

        # Verify urllib call
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.resend.com/emails")
        self.assertEqual(req.headers["Authorization"], "Bearer re_test_key_xyz")
        self.assertEqual(req.headers["Content-type"], "application/json")

        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["from"], "SriLekh Support <support@srilekh.com>")
        self.assertEqual(payload["to"], ["user@example.com"])
        self.assertEqual(payload["subject"], "Test OTP Code")
        self.assertEqual(payload["text"], "Your OTP code is 654321")
        self.assertEqual(payload["html"], "<p>Your OTP code is <b>654321</b></p>")
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(payload["attachments"][0]["filename"], "invoice.txt")
        self.assertEqual(msg.extra_headers.get("X-Resend-ID"), "resend_msg_001")
