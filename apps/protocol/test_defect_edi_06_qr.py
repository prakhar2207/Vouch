import time
import uuid
import threading
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.conf import settings
from django.core.cache import cache

from apps.protocol.crypto import ProtocolCrypto, Ed25519Signer
from apps.protocol.qr_bootstrap import QRSessionManager, QRBootstrapPayload, SecurityViolation
from apps.protocol.models import ProtocolConsumedNonce


class DefectEDI06QRConfigurationSecurityTests(TestCase):
    """
    Dedicated Security Verification Suite for DEFECT-EDI-06:
    Fail-closed QR Replay Protection across all production, staging, and non-test configurations.
    """

    def setUp(self):
        self.priv_key, self.pub_key = ProtocolCrypto.generate_keypair()
        self.issuer_id = f"ISSUER_{uuid.uuid4().hex[:8]}"
        self.public_keys = {self.issuer_id: self.pub_key}
        self.signer = Ed25519Signer()
        self.manager = QRSessionManager(signer=self.signer, public_keys=self.public_keys)
        # Clear cache
        cache.clear()

    def _create_signed_payload(self, nonce: str = None, expires_in: int = 300) -> QRBootstrapPayload:
        now = int(time.time())
        payload = QRBootstrapPayload(
            protocol_version="1.0",
            transaction_id=f"TX-{uuid.uuid4().hex[:8]}",
            session_id=f"SES-{uuid.uuid4().hex[:8]}",
            nonce=nonce or f"NONCE-{uuid.uuid4().hex[:12]}",
            issuer_id=self.issuer_id,
            transaction_digest="SHA256:FAKE_DIGEST",
            expires_at=now + expires_in
        )
        sig = ProtocolCrypto.sign(payload.serialize_for_signature(), self.priv_key)
        payload.signature = sig
        return payload

    def test_01_production_debug_false_fails_closed_when_stores_down(self):
        """Production configuration (DEBUG=False) MUST fail closed if Redis and DB are down."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with override_settings(DEBUG=False, TESTING=False):
            with patch.object(cache, 'add', side_effect=Exception("Redis connection refused")):
                with patch.object(ProtocolConsumedNonce.objects, 'create', side_effect=Exception("DB connection down")):
                    with self.assertRaises(SecurityViolation) as ctx:
                        self.manager.initiate_session_from_scan(qr_str, now)
                    self.assertIn("Durable replay protection store is unavailable", str(ctx.exception))

    def test_02_alternate_production_settings_fails_closed(self):
        """Alternate production settings module with DEBUG=False MUST fail closed."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with override_settings(DEBUG=False, TESTING=False):
            with patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": "config.settings.custom_production"}):
                with patch.object(cache, 'add', side_effect=Exception("Redis unavailable")):
                    with patch.object(ProtocolConsumedNonce.objects, 'create', side_effect=Exception("DB unavailable")):
                        with self.assertRaises(SecurityViolation) as ctx:
                            self.manager.initiate_session_from_scan(qr_str, now)
                        self.assertIn("Durable replay protection store is unavailable", str(ctx.exception))

    def test_03_staging_environment_fails_closed(self):
        """Staging environment (ENVIRONMENT='staging') MUST fail closed."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with override_settings(DEBUG=False, TESTING=False, ENVIRONMENT="staging"):
            with patch.object(cache, 'add', side_effect=Exception("Redis down")):
                with patch.object(ProtocolConsumedNonce.objects, 'create', side_effect=Exception("DB down")):
                    with self.assertRaises(SecurityViolation) as ctx:
                        self.manager.initiate_session_from_scan(qr_str, now)
                    self.assertIn("Durable replay protection store is unavailable", str(ctx.exception))

    def test_04_isolated_test_settings_permits_local_fallback(self):
        """Explicitly isolated test environment (TESTING=True, DEBUG=True) permits in-memory fallback."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with override_settings(DEBUG=True, TESTING=True, ENVIRONMENT="test"):
            with patch.object(cache, 'add', side_effect=Exception("Redis disabled")):
                with patch.object(ProtocolConsumedNonce.objects, 'create', side_effect=Exception("DB disabled")):
                    # First scan succeeds via in-memory set
                    session = self.manager.initiate_session_from_scan(qr_str, now)
                    self.assertIsNotNone(session)
                    self.assertIn(payload.nonce, self.manager.used_nonces)

                    # Replay attempt fails
                    with self.assertRaises(SecurityViolation) as ctx:
                        self.manager.initiate_session_from_scan(qr_str, now)
                    self.assertIn("Replay Attack Detected", str(ctx.exception))

    def test_05_tier1_redis_unavailable_falls_back_to_durable_database(self):
        """When Redis is unavailable, Tier 2 durable database persists the nonce."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with patch.object(cache, 'add', side_effect=Exception("Redis down")):
            session = self.manager.initiate_session_from_scan(qr_str, now)
            self.assertIsNotNone(session)

            # Check that nonce was durably recorded in database
            nonce_record = ProtocolConsumedNonce.objects.filter(
                issuer_id=payload.issuer_id,
                nonce=payload.nonce
            ).first()
            self.assertIsNotNone(nonce_record)

            # Replay scan fails via database unique constraint
            with self.assertRaises(SecurityViolation) as ctx:
                self.manager.initiate_session_from_scan(qr_str, now)
            self.assertIn("Replay Attack Detected", str(ctx.exception))

    def test_06_tier2_database_unavailable_succeeds_via_redis(self):
        """When Database is unavailable, Tier 1 Redis atomic cache consumes the nonce."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        with patch.object(ProtocolConsumedNonce.objects, 'create', side_effect=Exception("DB down")):
            session = self.manager.initiate_session_from_scan(qr_str, now)
            self.assertIsNotNone(session)

            # Replay scan fails via Redis
            with self.assertRaises(SecurityViolation) as ctx:
                self.manager.initiate_session_from_scan(qr_str, now)
            self.assertIn("Replay Attack Detected", str(ctx.exception))

    def test_07_forged_qr_does_not_consume_nonce(self):
        """Signature verification occurs BEFORE nonce consumption, defeating Nonce Starvation DoS."""
        payload = self._create_signed_payload()
        # Tamper with signature
        payload.signature = "a" * 128
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        # Forged scan fails at signature check
        with self.assertRaises(SecurityViolation) as ctx:
            self.manager.initiate_session_from_scan(qr_str, now)
        self.assertIn("signature validation failed", str(ctx.exception).lower())

        # Verify nonce was NOT consumed in DB or cache
        self.assertFalse(ProtocolConsumedNonce.objects.filter(nonce=payload.nonce).exists())
        self.assertNotIn(payload.nonce, self.manager.used_nonces)

        # Subsequent scan with legitimate signature SUCCEEDS using the same nonce!
        valid_payload = self._create_signed_payload(nonce=payload.nonce)
        valid_qr = valid_payload.encode_to_qr_string()
        session = self.manager.initiate_session_from_scan(valid_qr, now)
        self.assertIsNotNone(session)

    def test_08_concurrent_nonce_consumption(self):
        """Concurrent workers attempting to scan the same QR nonce: exactly one succeeds."""
        payload = self._create_signed_payload()
        qr_str = payload.encode_to_qr_string()
        now = int(time.time())

        results = []
        errors = []

        def worker():
            from django.db import connections, OperationalError
            connections.close_all()
            for attempt in range(5):
                try:
                    session = self.manager.initiate_session_from_scan(qr_str, now)
                    results.append(session.session_id)
                    break
                except SecurityViolation as ex:
                    errors.append(str(ex))
                    break
                except (OperationalError, Exception) as ex:
                    if "database table is locked" in str(ex) or "database is locked" in str(ex):
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    errors.append(str(ex))
                    break
            connections.close_all()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 1, "Exactly one worker must succeed in consuming the nonce.")
        self.assertEqual(len(errors), 1, "The second worker must be rejected with replay violation.")
        self.assertIn("Replay Attack Detected", errors[0])
