import uuid
import time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

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
        base_op = AccountingOperation(
            operation_id="OP-BASE",
            transaction_id=tx_id,
            replica_id="SELLER",
            operation_type=OperationType.TRANSACTION_ISSUED,
            payload={"grand_total": 1180.0, "total_tax": 180.0, "taxable_amount": 1000.0, "quantity": 10.0},
            logical_timestamp=1
        )

        rej_op = AccountingOperation(
            operation_id="OP-REJ",
            transaction_id=tx_id,
            replica_id="BUYER",
            operation_type=OperationType.ITEM_REJECTED,
            payload={"quantity": 2.0, "taxable_amount": 200.0, "tax_amount": 36.0, "line_id": "L1"},
            logical_timestamp=2,
            parents=["OP-BASE"]
        )

        res = SyncService.process_sync_payload(
            transaction_id=tx_id,
            client_replica_id="BUYER",
            client_operations=[base_op.to_dict(), rej_op.to_dict()],
            server_operations=[base_op],
            authenticated_tenant_id="TENANT-01"
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
