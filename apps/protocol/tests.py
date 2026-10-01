import uuid
import time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.accounts.models import User
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, LedgerEntry
from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine, 
    TaxSummary, TransactionTotals
)
from apps.protocol.operation import AccountingOperation, OperationType, OperationClass
from apps.protocol.compensation import CompensationEngine
from apps.protocol.bridge import LedgerBridge
from apps.protocol.sync_service import SyncService, MultiTenantSecurityError
from apps.protocol.handshake import EdiStateMachine, EdiState, IllegalStateTransitionError
from apps.protocol.models import EdiSession
from apps.protocol.crypto import ProtocolCrypto, Ed25519Signer, CrossLedgerCommitment, CryptographicSecurityError
from apps.protocol.key_manager import ProtocolKeyManager, ReplayProtectionEngine, SecurityViolationError

class ProtocolLedgerBridgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='testuser@vouch.example.com',
            password='TestPassword123!',
            first_name='Test',
            last_name='User'
        )
        self.seller_company = Company.objects.create(
            name="Vouch Seller Pvt Ltd",
            gstin="27AABCS1234F1Z1",
            state_code="27"
        )
        self.buyer_company = Company.objects.create(
            name="Vouch Buyer Corp",
            gstin="27AABCB9999E1Z2",
            state_code="27"
        )
        from apps.companies.models import UserCompany
        UserCompany.objects.create(user=self.user, company=self.seller_company, role='ADMIN')
        UserCompany.objects.create(user=self.user, company=self.buyer_company, role='ADMIN')

        self.seller_entity = ProtocolEntity('GSTIN', self.seller_company.gstin, self.seller_company.name, '27')
        self.buyer_entity = ProtocolEntity('GSTIN', self.buyer_company.gstin, self.buyer_company.name, '27')

        self.line = TransactionLine(
            line_id='LINE-01',
            sku='TEST-VALVE-01',
            name='Industrial Valve 20mm',
            hsn_code='8481',
            quantity=Decimal('10.00'),
            unit='PCS',
            unit_price=Decimal('1000.00'),
            discount_amount=Decimal('0.00'),
            taxable_amount=Decimal('10000.00'),
            tax_rate_percent=Decimal('18.00')
        )

        self.canonical_tx = CanonicalTransaction(
            protocol_version='1.0',
            transaction_id=f'TX-{uuid.uuid4().hex[:12].upper()}',
            transaction_type='SALE',
            state_version=1,
            issued_at=timezone.now(),
            source_entity=self.seller_entity,
            destination_entity=self.buyer_entity,
            items=[self.line],
            tax_summary=TaxSummary(cgst_amount=Decimal('900.00'), sgst_amount=Decimal('900.00')),
            totals=TransactionTotals(
                subtotal=Decimal('10000.00'),
                total_tax=Decimal('1800.00'),
                grand_total=Decimal('11800.00')
            )
        )

    def test_seller_end_to_end_bridge_execution(self):
        """Tests that Seller executes Sales Invoice, Credit Note for rejection, and Receipt for payment."""
        # 1. Buyer rejects 2 units
        rejection_op = CompensationEngine.generate_item_rejection(
            transaction=self.canonical_tx,
            line_id='LINE-01',
            quantity_rejected=Decimal('2.00'),
            replica_id='BUYER-REPLICA',
            logical_timestamp=2,
            parent_operation_id='ROOT'
        )

        # 2. Derived Reciprocal Credit Note for Seller
        cn_op = CompensationEngine.generate_reciprocal_seller_credit_note(
            rejection_op=rejection_op,
            seller_replica_id='SELLER-REPLICA',
            logical_timestamp=3
        )

        # 3. Buyer pays remaining ₹9,440
        pay_op = AccountingOperation(
            operation_id=f'OP-PAY-{uuid.uuid4().hex[:8].upper()}',
            transaction_id=self.canonical_tx.transaction_id,
            replica_id='BUYER-REPLICA',
            operation_type=OperationType.PAYMENT_ALLOCATED,
            operation_class=OperationClass.COMMUTATIVE,
            payload={'amount': 9440.00},
            logical_timestamp=4,
            parents=[cn_op.operation_id]
        )

        # Bridge execution on Seller company
        res = LedgerBridge.execute_converged_accounting(
            company=self.seller_company,
            canonical_tx=self.canonical_tx,
            converged_operations=[cn_op, pay_op],
            user=self.user
        )

        self.assertEqual(res['status'], 'BRIDGE_SUCCESS')
        self.assertEqual(res['role'], 'SELLER')
        self.assertEqual(res['vouchers_count'], 3)

        # Verify all vouchers are POSTED and double-entry balanced
        for v_num in res['posted_vouchers']:
            v = Voucher.objects.get(company=self.seller_company, voucher_number=v_num)
            self.assertEqual(v.status, 'POSTED')
            debits = sum(e.debit_amount for e in v.ledger_entries.all())
            credits = sum(e.credit_amount for e in v.ledger_entries.all())
            self.assertEqual(debits, credits)

    def test_buyer_end_to_end_bridge_execution(self):
        """Tests that Buyer executes Purchase Bill, Debit Note for rejection, and Payment voucher."""
        rejection_op = CompensationEngine.generate_item_rejection(
            transaction=self.canonical_tx,
            line_id='LINE-01',
            quantity_rejected=Decimal('2.00'),
            replica_id='BUYER-REPLICA',
            logical_timestamp=2,
            parent_operation_id='ROOT'
        )

        pay_op = AccountingOperation(
            operation_id=f'OP-PAY-{uuid.uuid4().hex[:8].upper()}',
            transaction_id=self.canonical_tx.transaction_id,
            replica_id='BUYER-REPLICA',
            operation_type=OperationType.PAYMENT_ALLOCATED,
            operation_class=OperationClass.COMMUTATIVE,
            payload={'amount': 9440.00},
            logical_timestamp=3,
            parents=[rejection_op.operation_id]
        )

        # Bridge execution on Buyer company
        res = LedgerBridge.execute_converged_accounting(
            company=self.buyer_company,
            canonical_tx=self.canonical_tx,
            converged_operations=[rejection_op, pay_op],
            user=self.user
        )

        self.assertEqual(res['status'], 'BRIDGE_SUCCESS')
        self.assertEqual(res['role'], 'BUYER')
        self.assertEqual(res['vouchers_count'], 3)

        for v_num in res['posted_vouchers']:
            v = Voucher.objects.get(company=self.buyer_company, voucher_number=v_num)
            self.assertEqual(v.status, 'POSTED')
            debits = sum(e.debit_amount for e in v.ledger_entries.all())
            credits = sum(e.credit_amount for e in v.ledger_entries.all())
            self.assertEqual(debits, credits)


class ProtocolSyncAndStateMachineTests(TestCase):
    def test_edi_state_machine_persistence(self):
        """Verifies EdiStateMachine persists state transitions in EdiSession model."""
        sid = f"SESS-{uuid.uuid4().hex[:8].upper()}"
        sm = EdiStateMachine(session_id=sid, timeout_seconds=300, persist=True)
        self.assertEqual(sm.current_state, EdiState.DISCOVER)

        sm.advance(EdiState.CAPABILITY_EXCHANGE, {"counterparty": "BUYER-01"})
        sm.advance(EdiState.AUTHENTICATE, {"auth_method": "Ed25519"})

        # Reload from database
        db_record = EdiSession.objects.get(session_id=sid)
        self.assertEqual(db_record.current_state, "AUTHENTICATE")
        self.assertEqual(len(db_record.transition_history), 3)

        # Reload new instance
        sm_reloaded = EdiStateMachine(session_id=sid, persist=True)
        self.assertEqual(sm_reloaded.current_state, EdiState.AUTHENTICATE)

    def test_edi_illegal_state_jump_rejected(self):
        """Verifies state machine blocks illegal transition jumps."""
        sid = f"SESS-{uuid.uuid4().hex[:8].upper()}"
        sm = EdiStateMachine(session_id=sid, persist=False)
        with self.assertRaises(IllegalStateTransitionError):
            sm.advance(EdiState.COMMIT) # Cannot skip directly to COMMIT

    def test_sync_service_atomic_compensation(self):
        """Verifies SyncService automatically generates reciprocal Credit Note on Item Rejection."""
        tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
        km = ProtocolKeyManager.get_default()
        seller_env = km.generate_keypair("SELLER")
        buyer_env = km.generate_keypair("BUYER")

        base_op = AccountingOperation(
            operation_id="OP-BASE",
            transaction_id=tx_id,
            replica_id="SELLER",
            operation_type=OperationType.TRANSACTION_ISSUED,
            payload={"grand_total": 1180.0, "total_tax": 180.0, "taxable_amount": 1000.0, "quantity": 10.0},
            logical_timestamp=1
        ).sign(seller_env.private_key_hex)

        rej_op = AccountingOperation(
            operation_id="OP-REJ",
            transaction_id=tx_id,
            replica_id="BUYER",
            operation_type=OperationType.ITEM_REJECTED,
            payload={"quantity": 2.0, "taxable_amount": 200.0, "tax_amount": 36.0, "line_id": "L1"},
            logical_timestamp=2,
            parents=["OP-BASE"]
        ).sign(buyer_env.private_key_hex)

        res = SyncService.process_sync_payload(
            transaction_id=tx_id,
            client_replica_id="BUYER",
            client_operations=[base_op.to_dict(), rej_op.to_dict()],
            server_operations=[base_op],
            authenticated_tenant_id="TENANT-01",
            canonical_tx_hash="HASH-TEST-001"
        )

        self.assertEqual(res['status'], 'SYNC_SUCCESS')
        self.assertIsNotNone(res['state_commitment'])
        self.assertIn('seller_ledger_root', res['merkle_state_roots'])
        self.assertIn('buyer_ledger_root', res['merkle_state_roots'])

        # Verify reciprocal Credit Note was generated for server/client
        recip_found = any(
            op['operation_type'] == OperationType.CREDIT_NOTE_ISSUED
            for op in res['server_operations_to_apply']
        )
        self.assertTrue(recip_found)


class ProtocolCryptoTests(TestCase):
    def test_fail_closed_ed25519_signatures(self):
        """Verifies fail-closed behavior on corrupted keys and forged signatures."""
        priv_a, pub_a = ProtocolCrypto.generate_keypair()
        priv_b, pub_b = ProtocolCrypto.generate_keypair()

        msg = "IMMUTABLE_ACCOUNTING_PAYLOAD"
        sig_a = ProtocolCrypto.sign(msg, priv_a)

        # Valid verification
        self.assertTrue(ProtocolCrypto.verify(msg, sig_a, pub_a))

        # Tampered message
        self.assertFalse(ProtocolCrypto.verify("TAMPERED_MESSAGE", sig_a, pub_a))

        # Signature from wrong key
        self.assertFalse(ProtocolCrypto.verify(msg, sig_a, pub_b))

        # Corrupted signature
        self.assertFalse(ProtocolCrypto.verify(msg, "ff" * 64, pub_a))

    def test_independent_dual_cross_ledger_commitment(self):
        """Verifies independent state roots and dual party counter-signing in CrossLedgerCommitment."""
        priv_seller, pub_seller = ProtocolCrypto.generate_keypair()
        priv_buyer, pub_buyer = ProtocolCrypto.generate_keypair()

        commitment = CrossLedgerCommitment(
            transaction_id="TX-COMMIT-01",
            transaction_state_root="f0" * 32,
            operation_state_root="f1" * 32,
            seller_ledger_root="f2" * 32,
            seller_inventory_root="f3" * 32,
            buyer_ledger_root="f4" * 32,
            buyer_inventory_root="f5" * 32,
            seller_identity="27AAAAA0000A1Z5",
            buyer_identity="27BBBBB1111B1Z2"
        )

        signed_seller = commitment.sign_seller(priv_seller)
        dual_signed = signed_seller.sign_buyer(priv_buyer)

        verification = dual_signed.verify_signatures(
            seller_public_key_hex=pub_seller,
            buyer_public_key_hex=pub_buyer
        )

        self.assertTrue(verification['seller_valid'])
        self.assertTrue(verification['buyer_valid'])

class AdvancedProtocolMechanismsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='advuser@vouch.example.com',
            password='TestPassword123!',
            first_name='Adv',
            last_name='User'
        )
        self.company = Company.objects.create(
            name="Adv Test Corp",
            gstin="27ADVTT1234F1Z9",
            state_code="27"
        )
        from apps.companies.models import UserCompany
        UserCompany.objects.create(user=self.user, company=self.company, role='ADMIN')

    def test_ledger_bridge_idempotency_caching(self):
        """Verifies that duplicate execution of LedgerBridge is cached and creates 0 duplicate vouchers."""
        from apps.protocol.schema import ProtocolEntity, TransactionLine, TaxSummary, TransactionTotals
        
        seller_entity = ProtocolEntity('GSTIN', self.company.gstin, self.company.name, '27')
        buyer_entity = ProtocolEntity('GSTIN', '27BUYER9999F1Z1', 'Buyer Firm', '27')
        line = TransactionLine(
            line_id='L-IDEM',
            sku='IDEM-SKU',
            name='Idempotent Item',
            hsn_code='8481',
            quantity=Decimal('5.00'),
            unit='PCS',
            unit_price=Decimal('100.00'),
            discount_amount=Decimal('0.00'),
            taxable_amount=Decimal('500.00'),
            tax_rate_percent=Decimal('18.00')
        )
        tx = CanonicalTransaction(
            protocol_version='1.0',
            transaction_id='TX-IDEMPOTENCY-01',
            transaction_type='SALE',
            state_version=1,
            issued_at=timezone.now(),
            source_entity=seller_entity,
            destination_entity=buyer_entity,
            items=[line],
            tax_summary=TaxSummary(cgst_amount=Decimal('45.00'), sgst_amount=Decimal('45.00')),
            totals=TransactionTotals(subtotal=Decimal('500.00'), total_tax=Decimal('90.00'), grand_total=Decimal('590.00'))
        )

        # First execution
        res1 = LedgerBridge.execute_converged_accounting(
            company=self.company,
            canonical_tx=tx,
            converged_operations=[],
            user=self.user
        )
        self.assertEqual(res1['status'], 'BRIDGE_SUCCESS')
        initial_voucher_count = Voucher.objects.filter(company=self.company).count()

        # Second execution with exact same transaction & operations
        res2 = LedgerBridge.execute_converged_accounting(
            company=self.company,
            canonical_tx=tx,
            converged_operations=[],
            user=self.user
        )
        self.assertEqual(res2['status'], 'BRIDGE_SUCCESS')
        self.assertTrue(res2.get('idempotent_cached'))
        final_voucher_count = Voucher.objects.filter(company=self.company).count()

        # Zero duplicate vouchers created
        self.assertEqual(initial_voucher_count, final_voucher_count)

    def test_bounded_semantic_mapping_engine(self):
        """Verifies multi-tier heuristic and token similarity matching."""
        from apps.protocol.mapping import SemanticMappingEngine, MappingConfidence

        catalog = [
            {"sku": "PIPE-20MM-SS", "name": "Stainless Steel Pipe 20mm Industrial", "hsn_code": "7306"},
            {"sku": "VALVE-BRASS-50", "name": "Brass Ball Valve 50mm", "hsn_code": "8481"},
        ]

        # Tier 1: Exact SKU
        m1 = SemanticMappingEngine.match_product("PIPE-20MM-SS", "Any Name", "7306", catalog)
        self.assertIsNotNone(m1)
        self.assertEqual(m1[0]['sku'], "PIPE-20MM-SS")
        self.assertEqual(m1[1], 1.0)
        self.assertEqual(m1[2], MappingConfidence.HEURISTIC)

        # Tier 2: Normalized SKU (dashes omitted, lowercase)
        m2 = SemanticMappingEngine.match_product("pipe20mmss", "Different Name", "0000", catalog)
        self.assertIsNotNone(m2)
        self.assertEqual(m2[0]['sku'], "PIPE-20MM-SS")
        self.assertEqual(m2[1], 0.95)

        # Tier 3: HSN code + Token Overlap
        m3 = SemanticMappingEngine.match_product("FOREIGN-V", "Brass Ball Valve High Pressure", "8481", catalog)
        self.assertIsNotNone(m3)
        self.assertEqual(m3[0]['sku'], "VALVE-BRASS-50")
        self.assertGreaterEqual(m3[1], 0.70)

    def test_key_manager_rotation_and_revocation(self):
        """Verifies key manager lifecycle: generation, rotation, and revocation fail-closed."""
        from apps.protocol.key_manager import ProtocolKeyManager, SecurityViolationError

        km = ProtocolKeyManager()
        k1 = km.generate_keypair("REPLICA-A")
        self.assertIsNotNone(k1.public_key_hex)

        # Can retrieve active key
        pub = km.get_public_key("REPLICA-A")
        self.assertEqual(pub, k1.public_key_hex)

        # Key rotation creates new key
        k2 = km.rotate_key("REPLICA-A")
        self.assertNotEqual(k1.key_id, k2.key_id)
        pub_rotated = km.get_public_key("REPLICA-A")
        self.assertEqual(pub_rotated, k2.public_key_hex)

        # Revocation causes fail-closed exception
        km.revoke_key(k2.key_id)
        with self.assertRaises(SecurityViolationError):
            km.get_public_key(k2.key_id)

    def test_replay_protection_sliding_window(self):
        """Verifies replay engine rejects replayed nonces and stale timestamps."""
        from apps.protocol.key_manager import ReplayProtectionEngine, SecurityViolationError

        rpe = ReplayProtectionEngine(window_seconds=300)
        now = time.time()

        # Valid consumption
        rpe.validate_and_consume("NODE-1", "NONCE-001", now)

        # Replay same nonce -> Rejection
        with self.assertRaises(SecurityViolationError):
            rpe.validate_and_consume("NODE-1", "NONCE-001", now)

        # Stale timestamp beyond 300s window -> Rejection
        with self.assertRaises(SecurityViolationError):
            rpe.validate_and_consume("NODE-1", "NONCE-002", now - 400)

    def test_protocol_sync_api_view(self):
        """Tests POST /api/v1/protocol/sync/ REST endpoint enforcing auth and signatures."""
        from rest_framework.test import APIClient
        c = APIClient()

        # 1. Anonymous access is strictly rejected
        anon_resp = c.post('/api/v1/protocol/sync/', data={"transaction_id": "TX-API-TEST-001"}, format='json')
        self.assertEqual(anon_resp.status_code, 401)

        # 2. Authenticated access with Ed25519-signed operation succeeds
        c.force_authenticate(user=self.user)
        km = ProtocolKeyManager.get_default()
        cli_env = km.generate_keypair("CLI-TEST-01")

        op_data = {
            "operation_id": "OP-API-001",
            "transaction_id": "TX-API-TEST-001",
            "replica_id": "CLI-TEST-01",
            "operation_type": "TRANSACTION_ISSUED",
            "payload": {
                "grand_total": 1180.0,
                "taxable_amount": 1000.0,
                "total_tax": 180.0,
                "cgst_amount": 90.0,
                "sgst_amount": 90.0
            },
            "logical_timestamp": 1,
            "parents": []
        }
        test_op = AccountingOperation(
            operation_id=op_data["operation_id"],
            transaction_id=op_data["transaction_id"],
            replica_id=op_data["replica_id"],
            operation_type=OperationType.TRANSACTION_ISSUED,
            payload=op_data["payload"],
            logical_timestamp=op_data["logical_timestamp"],
            parents=op_data["parents"]
        )
        op_data["signature"] = ProtocolCrypto.sign(test_op.payload_hash, cli_env.private_key_hex)

        payload = {
            "transaction_id": "TX-API-TEST-001",
            "client_replica_id": "CLI-TEST-01",
            "company_id": str(self.company.id),
            "canonical_tx_hash": "HASH-TX-API-001",
            "client_operations": [op_data]
        }
        resp = c.post('/api/v1/protocol/sync/', data=payload, format='json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(resp_data['status'], 'SYNC_SUCCESS')
        self.assertIn('state_commitment', resp_data)
        self.assertIn('merkle_state_roots', resp_data)

    def test_device_registration_and_revocation_api(self):
        """Verifies cryptographic device registration endpoint and subsequent revocation enforcement."""
        from apps.protocol.models import AuthorizedDevice
        c = APIClient()
        c.force_authenticate(user=self.user)

        # 1. Register device
        priv_k, pub_k = ProtocolCrypto.generate_keypair()
        reg_payload = {
            "device_id": "DEV-TEST-PHONE-99",
            "replica_id": "REP-TEST-PHONE-99",
            "public_key_hex": pub_k,
            "device_name": "Warehouse Scanner Tab",
            "company_id": str(self.company.id)
        }
        res = c.post('/api/v1/protocol/devices/register/', data=reg_payload, format='json')
        self.assertIn(res.status_code, [200, 201])
        data = res.json()
        self.assertEqual(data["status"], "REGISTERED")
        self.assertEqual(data["replica_id"], "REP-TEST-PHONE-99")

        # Verify record in DB
        device = AuthorizedDevice.objects.get(device_id="DEV-TEST-PHONE-99")
        self.assertEqual(device.status, "ACTIVE")
        self.assertEqual(device.public_key_hex, pub_k)

        # 2. Revoke device in DB
        device.status = "REVOKED"
        device.save()

        # 3. Attempt sync with revoked device - must be rejected fail-closed
        op_data = {
            "operation_id": "OP-REVOKED-01",
            "transaction_id": "TX-REV-01",
            "replica_id": "REP-TEST-PHONE-99",
            "operation_type": "TRANSACTION_ISSUED",
            "payload": {"grand_total": 500.0, "taxable_amount": 500.0, "total_tax": 0.0},
            "logical_timestamp": 1,
            "parents": []
        }
        op = AccountingOperation(
            operation_id=op_data["operation_id"],
            transaction_id=op_data["transaction_id"],
            replica_id=op_data["replica_id"],
            operation_type=OperationType.TRANSACTION_ISSUED,
            payload=op_data["payload"],
            logical_timestamp=1,
            parents=[]
        )
        op_data["signature"] = ProtocolCrypto.sign(op.payload_hash, priv_k)

        sync_payload = {
            "transaction_id": "TX-REV-01",
            "client_replica_id": "REP-TEST-PHONE-99",
            "company_id": str(self.company.id),
            "canonical_tx_hash": "HASH-REV-01",
            "client_operations": [op_data]
        }
        sync_resp = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        self.assertEqual(sync_resp.status_code, 400)
        self.assertEqual(sync_resp.json()["status"], "SYNC_REJECTED")
        self.assertIn("REVOKED", sync_resp.json()["reason"])

