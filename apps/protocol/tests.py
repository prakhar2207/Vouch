import uuid
import time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies.models import Company, UserCompany
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

        canonical_tx = CanonicalTransaction(
            protocol_version="1.0",
            transaction_id=tx_id,
            transaction_type="SALE",
            state_version=1,
            issued_at=timezone.now(),
            source_entity=ProtocolEntity("GSTIN", "27AAAAA1234A1Z5", "Seller", "27"),
            destination_entity=ProtocolEntity("GSTIN", "27BBBBB5678B1Z6", "Buyer", "27"),
            items=[
                TransactionLine("L1", "ITEM-1", "Item", "8481", Decimal("10.00"), "PCS", Decimal("100.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("18.00"))
            ],
            tax_summary=TaxSummary(cgst_amount=Decimal("90.00"), sgst_amount=Decimal("90.00")),
            totals=TransactionTotals(subtotal=Decimal("1000.00"), total_tax=Decimal("180.00"), grand_total=Decimal("1180.00"))
        )

        res = SyncService.process_sync_payload(
            transaction_id=tx_id,
            client_replica_id="BUYER",
            client_operations=[base_op.to_dict(), rej_op.to_dict()],
            server_operations=[base_op],
            authenticated_tenant_id="TENANT-01",
            canonical_tx=canonical_tx,
            canonical_tx_hash=canonical_tx.canonical_hash
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

        from apps.protocol.models import AuthorizedDevice
        AuthorizedDevice.objects.get_or_create(
            device_id="CLI-DEV-01",
            defaults={
                "replica_id": "CLI-TEST-01",
                "company": self.company,
                "public_key_hex": cli_env.public_key_hex,
                "key_id": cli_env.key_id,
                "status": "ACTIVE"
            }
        )

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

        raw_canonical = {
            "protocol_version": "1.0",
            "transaction_id": "TX-API-TEST-001",
            "transaction_type": "SALE",
            "state_version": 1,
            "issued_at": "2026-10-01T10:00:00",
            "source_entity": {
                "type": "GSTIN",
                "value": str(self.company.gstin or self.company.id),
                "name": self.company.name,
                "state_code": "27"
            },
            "destination_entity": {
                "type": "GSTIN",
                "value": "27BBBBB5678B1Z6",
                "name": "Buyer Corp",
                "state_code": "27"
            },
            "items": [
                {
                    "line_id": "L1",
                    "sku": "VALVE-01",
                    "name": "Industrial Valve",
                    "hsn_code": "8481",
                    "quantity": "10.00",
                    "unit": "PCS",
                    "unit_price": "100.00",
                    "discount_amount": "0.00",
                    "taxable_amount": "1000.00",
                    "tax_rate_percent": "18.00"
                }
            ],
            "tax_summary": {
                "cgst": "90.00",
                "sgst": "90.00",
                "igst": "0.00",
                "cess": "0.00",
                "total_tax": "180.00"
            },
            "totals": {
                "subtotal": "1000.00",
                "total_tax": "180.00",
                "shipping": "0.00",
                "discount": "0.00",
                "grand_total": "1180.00"
            },
            "causal_dependencies": []
        }
        reconstructed = CanonicalTransaction.from_dict(raw_canonical)
        payload = {
            "transaction_id": "TX-API-TEST-001",
            "client_replica_id": "CLI-TEST-01",
            "company_id": str(self.company.id),
            "canonical_tx_hash": reconstructed.canonical_hash,
            "canonical_transaction": raw_canonical,
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

    def test_unregistered_device_rejection(self):
        """Verifies that an unknown, unregistered replica device is rejected fail-closed."""
        c = APIClient()
        c.force_authenticate(user=self.user)
        sync_payload = {
            "transaction_id": "TX-UNREG-01",
            "client_replica_id": "REP-UNKNOWN-GHOST-DEVICE",
            "company_id": str(self.company.id),
            "canonical_tx_hash": "HASH-UNREG-01",
            "client_operations": []
        }
        res = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["status"], "SYNC_REJECTED")
        self.assertIn("Unregistered device", res.json()["reason"])

    def test_device_cross_company_isolation(self):
        """Verifies that a device registered to Company B cannot submit operations for Company A."""
        from apps.protocol.models import AuthorizedDevice
        c = APIClient()
        c.force_authenticate(user=self.user)

        other_company = Company.objects.create(name="Rival Enterprise 99", gstin="27RIVAAAA1234A1Z")
        priv_k, pub_k = ProtocolCrypto.generate_keypair()
        AuthorizedDevice.objects.create(
            device_id="DEV-RIVAL-01",
            replica_id="REP-RIVAL-01",
            company=other_company,
            public_key_hex=pub_k,
            key_id="KID-RIVAL-01",
            status="ACTIVE"
        )

        sync_payload = {
            "transaction_id": "TX-CROSS-01",
            "client_replica_id": "REP-RIVAL-01",
            "company_id": str(self.company.id),
            "canonical_tx_hash": "HASH-CROSS-01",
            "client_operations": []
        }
        res = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["status"], "SYNC_REJECTED")
        self.assertIn("not an authorized device for company", res.json()["reason"])

    def test_device_rotation_api(self):
        """Verifies POST /api/v1/protocol/devices/rotate/ enforces authorization, logs audit trail, and replaces key."""
        from apps.protocol.models import AuthorizedDevice, DeviceKeyRotationAudit
        c = APIClient()
        c.force_authenticate(user=self.user)

        priv_orig, pub_orig = ProtocolCrypto.generate_keypair()
        priv_new, pub_new = ProtocolCrypto.generate_keypair()

        AuthorizedDevice.objects.create(
            device_id="DEV-ROTATE-TEST",
            replica_id="REP-ROTATE-TEST",
            company=self.company,
            public_key_hex=pub_orig,
            key_id="KID-OLD-01",
            status="ACTIVE"
        )

        # 1. Admin Authorization Rotation
        rotate_payload = {
            "device_id": "DEV-ROTATE-TEST",
            "new_public_key_hex": pub_new,
            "new_key_id": "KID-NEW-02",
            "company_id": str(self.company.id)
        }
        res = c.post('/api/v1/protocol/devices/rotate/', data=rotate_payload, format='json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ROTATED")
        self.assertEqual(data["authorization_method"], "COMPANY_ADMIN")
        self.assertIn("audit_id", data)

        device = AuthorizedDevice.objects.get(device_id="DEV-ROTATE-TEST")
        self.assertEqual(device.public_key_hex, pub_new)
        self.assertEqual(device.key_id, "KID-NEW-02")
        self.assertEqual(device.status, "ACTIVE")

        # Verify audit trail record in DB
        audit_records = DeviceKeyRotationAudit.objects.filter(device=device)
        self.assertEqual(audit_records.count(), 1)
        self.assertEqual(audit_records.first().old_public_key_hex, pub_orig)
        self.assertEqual(audit_records.first().new_public_key_hex, pub_new)
        self.assertEqual(audit_records.first().authorization_method, "COMPANY_ADMIN")

        # 2. Cryptographic Proof Rotation (Signed by current active key priv_new)
        priv_v3, pub_v3 = ProtocolCrypto.generate_keypair()
        rot_msg = f"ROTATE:DEV-ROTATE-TEST:{pub_v3}:KID-V3"
        rot_sig = ProtocolCrypto.sign(rot_msg, priv_new)

        rot_crypto_payload = {
            "device_id": "DEV-ROTATE-TEST",
            "new_public_key_hex": pub_v3,
            "new_key_id": "KID-V3",
            "rotation_signature": rot_sig,
            "company_id": str(self.company.id)
        }
        res_crypto = c.post('/api/v1/protocol/devices/rotate/', data=rot_crypto_payload, format='json')
        self.assertEqual(res_crypto.status_code, 200)
        self.assertEqual(res_crypto.json()["authorization_method"], "CRYPTOGRAPHIC_PROOF")
        self.assertEqual(DeviceKeyRotationAudit.objects.filter(device=device).count(), 2)

        # 3. Unauthorized User Rotation Rejection (Non-admin without valid signature)
        non_admin_user = User.objects.create_user(email="viewer@vouch.example.com", password="Pass123!Password", role="VIEWER")
        UserCompany.objects.create(user=non_admin_user, company=self.company, role='VIEWER')
        c_unauth = APIClient()
        c_unauth.force_authenticate(user=non_admin_user)
        priv_v4, pub_v4 = ProtocolCrypto.generate_keypair()
        unauth_payload = {
            "device_id": "DEV-ROTATE-TEST",
            "new_public_key_hex": pub_v4,
            "new_key_id": "KID-V4",
            "company_id": str(self.company.id)
        }
        res_unauth = c_unauth.post('/api/v1/protocol/devices/rotate/', data=unauth_payload, format='json')
        self.assertEqual(res_unauth.status_code, 403)
        self.assertIn("UNAUTHORIZED", res_unauth.json()["status"])

    def test_canonical_transaction_reconstruction_and_tamper_detection(self):
        """Verifies that the server reconstructs CanonicalTransaction and rejects claimed hash mismatches."""
        from apps.protocol.models import AuthorizedDevice
        from apps.protocol.schema import CanonicalTransaction
        c = APIClient()
        c.force_authenticate(user=self.user)

        priv_k, pub_k = ProtocolCrypto.generate_keypair()
        AuthorizedDevice.objects.create(
            device_id="DEV-CANON-01",
            replica_id="REP-CANON-01",
            company=self.company,
            public_key_hex=pub_k,
            key_id="KID-CANON-01",
            status="ACTIVE"
        )

        raw_canonical = {
            "protocol_version": "1.0",
            "transaction_id": "TX-CANON-01",
            "transaction_type": "SALE",
            "state_version": 1,
            "issued_at": "2026-10-01T10:00:00",
            "source_entity": {
                "type": "GSTIN",
                "value": str(self.company.gstin or self.company.id),
                "name": self.company.name,
                "state_code": "27"
            },
            "destination_entity": {
                "type": "GSTIN",
                "value": "27BBBBB5678B1Z6",
                "name": "Buyer Corp",
                "state_code": "27"
            },
            "items": [
                {
                    "line_id": "L1",
                    "sku": "ITEM-1",
                    "name": "Item 1",
                    "hsn_code": "1234",
                    "quantity": "10.00",
                    "unit": "PCS",
                    "unit_price": "100.00",
                    "discount_amount": "0.00",
                    "taxable_amount": "1000.00",
                    "tax_rate_percent": "18.00"
                }
            ],
            "tax_summary": {
                "cgst": "90.00",
                "sgst": "90.00",
                "igst": "0.00",
                "cess": "0.00",
                "total_tax": "180.00"
            },
            "totals": {
                "subtotal": "1000.00",
                "total_tax": "180.00",
                "shipping": "0.00",
                "discount": "0.00",
                "grand_total": "1180.00"
            },
            "causal_dependencies": []
        }
        reconstructed = CanonicalTransaction.from_dict(raw_canonical)
        true_hash = reconstructed.canonical_hash

        op_data = {
            "operation_id": "OP-CANON-01",
            "transaction_id": "TX-CANON-01",
            "replica_id": "REP-CANON-01",
            "operation_type": "TRANSACTION_ISSUED",
            "payload": {"grand_total": 1180.0, "taxable_amount": 1000.0, "total_tax": 180.0},
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

        # 1. Attacker sends tampered/claimed hash mismatch
        bad_payload = {
            "transaction_id": "TX-CANON-01",
            "client_replica_id": "REP-CANON-01",
            "company_id": str(self.company.id),
            "canonical_transaction": raw_canonical,
            "canonical_tx_hash": "FORGED_HASH_1234567890",
            "client_operations": [op_data]
        }
        bad_res = c.post('/api/v1/protocol/sync/', data=bad_payload, format='json')
        self.assertEqual(bad_res.status_code, 400)
        self.assertEqual(bad_res.json()["status"], "SYNC_REJECTED")
        self.assertIn("Canonical transaction hash mismatch", bad_res.json()["reason"])

        # 2. Honest client sends genuine canonical transaction & verified hash -> Success
        good_payload = {
            "transaction_id": "TX-CANON-01",
            "client_replica_id": "REP-CANON-01",
            "company_id": str(self.company.id),
            "canonical_transaction": raw_canonical,
            "canonical_tx_hash": true_hash,
            "client_operations": [op_data]
        }
        good_res = c.post('/api/v1/protocol/sync/', data=good_payload, format='json')
        self.assertEqual(good_res.status_code, 200)
        self.assertEqual(good_res.json()["status"], "SYNC_SUCCESS")

    def test_device_duplicate_registration_rejected_409(self):
        """Verifies POST /api/v1/protocol/devices/register/ returns 409 Conflict when device_id already exists."""
        from apps.protocol.models import AuthorizedDevice
        c = APIClient()
        c.force_authenticate(user=self.user)

        priv_k, pub_k = ProtocolCrypto.generate_keypair()
        reg_payload = {
            "device_id": "DEV-EXISTS-409",
            "replica_id": "REP-EXISTS-409",
            "public_key_hex": pub_k,
            "device_name": "Terminal Alpha",
            "company_id": str(self.company.id)
        }
        # First registration: 201 Created
        res1 = c.post('/api/v1/protocol/devices/register/', data=reg_payload, format='json')
        self.assertEqual(res1.status_code, 201)

        # Second registration with same device_id: 409 Conflict
        res2 = c.post('/api/v1/protocol/devices/register/', data=reg_payload, format='json')
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.json()["status"], "DEVICE_ALREADY_REGISTERED")

        # Third registration with different device_id but same replica_id: 409 Conflict
        priv_k2, pub_k2 = ProtocolCrypto.generate_keypair()
        reg_payload2 = {
            "device_id": "DEV-DIFFERENT-409",
            "replica_id": "REP-EXISTS-409",
            "public_key_hex": pub_k2,
            "device_name": "Terminal Beta",
            "company_id": str(self.company.id)
        }
        res3 = c.post('/api/v1/protocol/devices/register/', data=reg_payload2, format='json')
        self.assertEqual(res3.status_code, 409)
        self.assertEqual(res3.json()["status"], "REPLICA_ALREADY_BOUND")

    def test_new_transaction_missing_canonical_payload_rejected(self):
        """Verifies that a brand-new transaction cannot be created with just an arbitrary hash assertion."""
        from apps.protocol.models import AuthorizedDevice
        c = APIClient()
        c.force_authenticate(user=self.user)

        priv_k, pub_k = ProtocolCrypto.generate_keypair()
        AuthorizedDevice.objects.get_or_create(
            device_id="DEV-NOCANON-01",
            defaults={
                "replica_id": "REP-NOCANON-01",
                "company": self.company,
                "public_key_hex": pub_k,
                "status": "ACTIVE"
            }
        )

        payload = {
            "transaction_id": "TX-BRAND-NEW-UNKNOWN",
            "client_replica_id": "REP-NOCANON-01",
            "company_id": str(self.company.id),
            "canonical_tx_hash": "ARBITRARY_HASH_CLAIM",
            "client_operations": []
        }
        res = c.post('/api/v1/protocol/sync/', data=payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["status"], "SYNC_REJECTED")
        self.assertIn("requires a complete canonical_transaction payload", res.json()["reason"])

    def test_unauthorized_third_party_replica_operation_rejected(self):
        """Verifies that an operation signed by a third-party company device is rejected from transaction sync."""
        from apps.protocol.models import AuthorizedDevice
        c = APIClient()
        c.force_authenticate(user=self.user)

        # Local device for self.company
        priv_loc, pub_loc = ProtocolCrypto.generate_keypair()
        AuthorizedDevice.objects.get_or_create(
            device_id="DEV-LOCAL-AUTH",
            defaults={"replica_id": "REP-LOCAL-AUTH", "company": self.company, "public_key_hex": pub_loc, "status": "ACTIVE"}
        )

        # Rogue third-party company
        rogue_company = Company.objects.create(name="Third Party Spy Corp", gstin="27SPYCO1234A1Z9")
        priv_rogue, pub_rogue = ProtocolCrypto.generate_keypair()
        AuthorizedDevice.objects.create(
            device_id="DEV-ROGUE-01",
            replica_id="REP-ROGUE-01",
            company=rogue_company,
            public_key_hex=pub_rogue,
            status="ACTIVE"
        )

        raw_canonical = {
            "protocol_version": "1.0",
            "transaction_id": "TX-INTERCEPT-01",
            "transaction_type": "SALE",
            "state_version": 1,
            "issued_at": "2026-10-01T10:00:00",
            "source_entity": {"type": "GSTIN", "value": self.company.gstin, "name": self.company.name, "state_code": "27"},
            "destination_entity": {"type": "GSTIN", "value": "27BBBBB5678B1Z6", "name": "Buyer Corp", "state_code": "27"},
            "items": [{"line_id": "L1", "sku": "ITEM-1", "name": "Item", "hsn_code": "8481", "quantity": "1.00", "unit": "PCS", "unit_price": "100.00", "discount_amount": "0.00", "taxable_amount": "100.00", "tax_rate_percent": "18.00"}],
            "tax_summary": {"cgst": "9.00", "sgst": "9.00", "igst": "0.00", "cess": "0.00", "total_tax": "18.00"},
            "totals": {"subtotal": "100.00", "total_tax": "18.00", "shipping": "0.00", "discount": "0.00", "grand_total": "118.00"},
            "causal_dependencies": []
        }
        reconstructed = CanonicalTransaction.from_dict(raw_canonical)

        # Rogue operation signed by rogue replica
        rogue_op_data = {
            "operation_id": "OP-ROGUE-01",
            "transaction_id": "TX-INTERCEPT-01",
            "replica_id": "REP-ROGUE-01",
            "operation_type": "PAYMENT_ALLOCATED",
            "payload": {"amount": 500.0, "payment_reference": "ROGUE-PAY"},
            "logical_timestamp": 2,
            "parents": []
        }
        rogue_op = AccountingOperation(
            operation_id=rogue_op_data["operation_id"],
            transaction_id=rogue_op_data["transaction_id"],
            replica_id=rogue_op_data["replica_id"],
            operation_type=OperationType.PAYMENT_ALLOCATED,
            payload=rogue_op_data["payload"],
            logical_timestamp=2,
            parents=[]
        )
        rogue_op_data["signature"] = ProtocolCrypto.sign(rogue_op.payload_hash, priv_rogue)

        sync_payload = {
            "transaction_id": "TX-INTERCEPT-01",
            "client_replica_id": "REP-LOCAL-AUTH",
            "company_id": str(self.company.id),
            "canonical_transaction": raw_canonical,
            "canonical_tx_hash": reconstructed.canonical_hash,
            "client_operations": [rogue_op_data]
        }
        res = c.post('/api/v1/protocol/sync/', data=sync_payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["status"], "SYNC_REJECTED")
        self.assertIn("not a participant in transaction", res.json()["reason"])

