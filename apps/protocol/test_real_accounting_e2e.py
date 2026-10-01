import os
import sys
import time
import uuid
from decimal import Decimal

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.utils import timezone
from django.db import transaction

from apps.accounts.models import User
from apps.companies.models import Company, UserCompany
from apps.inventory.models import Product, Warehouse
from apps.ledgers.models import Ledger, LedgerGroup
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.accounting.services.voucher_service import VoucherService

from apps.protocol.schema import (
    CanonicalTransaction, ProtocolEntity, TransactionLine, 
    TaxSummary, TransactionTotals
)
from apps.protocol.operation import AccountingOperation, OperationType, OperationClass
from apps.protocol.crdt import DE_CRDT
from apps.protocol.compensation import CompensationEngine
from apps.protocol.bridge import LedgerBridge
from apps.protocol.sync_service import SyncService
from apps.protocol.key_manager import ProtocolKeyManager
from apps.protocol.crypto import ProtocolCrypto, CrossLedgerCommitment
from apps.protocol.invariants import InvariantEngine
from apps.protocol.models import (
    ProtocolTransaction, ProtocolOperation, CryptographicCommitment, 
    ProtocolBridgeExecution, EntityMapping
)


def run_real_accounting_e2e():
    print("================================================================================")
    print("   VOUCH DISTRIBUTED ACCOUNTING: REAL POSTGRES/SQLITE DATABASE E2E TEST         ")
    print("================================================================================")
    print("Executing end-to-end distributed accounting scenario with real database persistence,")
    print("dual Ed25519 signatures, CRDT merge, automated compensation, and LedgerBridge.\n")

    # -------------------------------------------------------------------------
    # STAGE 0: PROVISION REAL DATABASE COMPANIES & USERS
    # -------------------------------------------------------------------------
    print("[Stage 0] Provisioning physical companies, authorized users, and Ed25519 keys...")
    test_run_id = uuid.uuid4().hex[:8].upper()

    user, _ = User.objects.get_or_create(
        email=f"e2e_auditor_{test_run_id}@vouch.example.com",
        defaults={"first_name": "Auditor", "last_name": "MSME"}
    )

    seller_company, _ = Company.objects.get_or_create(
        name=f"Apex Heavy Industries {test_run_id}",
        defaults={
            "gstin": "27AAAAA1234A1Z5",
            "state_code": "27",
            "state_name": "Maharashtra"
        }
    )

    buyer_company, _ = Company.objects.get_or_create(
        name=f"Metro Infra Buildcon {test_run_id}",
        defaults={
            "gstin": "27BBBBB5678B1Z6",
            "state_code": "27",
            "state_name": "Maharashtra"
        }
    )

    UserCompany.objects.get_or_create(user=user, company=seller_company, defaults={"role": "ADMIN"})
    UserCompany.objects.get_or_create(user=user, company=buyer_company, defaults={"role": "ADMIN"})

    # Setup Ed25519 Key Infrastructure
    km = ProtocolKeyManager.get_default()
    seller_replica_id = f"SELLER-NODE-{test_run_id}"
    buyer_replica_id = f"BUYER-NODE-{test_run_id}"
    seller_env = km.generate_keypair(seller_replica_id)
    buyer_env = km.generate_keypair(buyer_replica_id)

    from apps.protocol.models import AuthorizedDevice
    AuthorizedDevice.objects.create(
        device_id=f"DEV-{seller_replica_id}",
        replica_id=seller_replica_id,
        company=seller_company,
        public_key_hex=seller_env.public_key_hex,
        status="ACTIVE"
    )
    AuthorizedDevice.objects.create(
        device_id=f"DEV-{buyer_replica_id}",
        replica_id=buyer_replica_id,
        company=buyer_company,
        public_key_hex=buyer_env.public_key_hex,
        status="ACTIVE"
    )

    print(f"  -> Seller Company: {seller_company.name} (GSTIN: {seller_company.gstin})")
    print(f"  -> Buyer Company:  {buyer_company.name} (GSTIN: {buyer_company.gstin})")
    print(f"  -> Seller Ed25519 PubKey: {seller_env.public_key_hex[:24]}...")
    print(f"  -> Buyer Ed25519 PubKey:  {buyer_env.public_key_hex[:24]}...")

    # -------------------------------------------------------------------------
    # STAGE 1: CANONICAL TRANSACTION CREATION & DETERMINISTIC HASH
    # -------------------------------------------------------------------------
    print("\n[Stage 1] Constructing Canonical Transaction Envelope & Deterministic SHA-256 Digest...")
    tx_id = f"TX-E2E-{test_run_id}"

    seller_entity = ProtocolEntity('GSTIN', seller_company.gstin, seller_company.name, '27')
    buyer_entity = ProtocolEntity('GSTIN', buyer_company.gstin, buyer_company.name, '27')

    item_line = TransactionLine(
        line_id='LINE-01',
        sku='PBV-50',
        name='Precision Ball Valve 50mm Industrial',
        hsn_code='8481',
        quantity=Decimal('10.00'),
        unit='PCS',
        unit_price=Decimal('1000.00'),
        discount_amount=Decimal('0.00'),
        taxable_amount=Decimal('10000.00'),
        tax_rate_percent=Decimal('18.00')
    )

    canonical_tx = CanonicalTransaction(
        protocol_version='1.0',
        transaction_id=tx_id,
        transaction_type='SALE',
        state_version=1,
        issued_at=timezone.now(),
        source_entity=seller_entity,
        destination_entity=buyer_entity,
        items=[item_line],
        tax_summary=TaxSummary(cgst_amount=Decimal('900.00'), sgst_amount=Decimal('900.00')),
        totals=TransactionTotals(
            subtotal=Decimal('10000.00'),
            total_tax=Decimal('1800.00'),
            grand_total=Decimal('11800.00')
        )
    )

    canonical_hash = canonical_tx.canonical_hash
    print(f"  -> Transaction ID: {tx_id}")
    print(f"  -> Total 10 Units @ Rs 1,000 + 18% GST (CGST Rs 900, SGST Rs 900) = Rs 11,800")
    print(f"  -> Deterministic Canonical Digest: {canonical_hash}")

    # Seller issues base sale operation and signs with Ed25519
    op_base = AccountingOperation(
        operation_id=f"OP-BASE-{test_run_id}",
        transaction_id=tx_id,
        replica_id=seller_replica_id,
        operation_type=OperationType.TRANSACTION_ISSUED,
        payload={
            "grand_total": 11800.0,
            "taxable_amount": 10000.0,
            "total_tax": 1800.0,
            "cgst_amount": 900.0,
            "sgst_amount": 900.0,
            "igst_amount": 0.0,
            "quantity": 10.0
        },
        logical_timestamp=1,
        parents=[]
    ).sign(seller_env.private_key_hex)
    print(f"  -> Base Sale Op {op_base.operation_id} signed by Seller.")

    # -------------------------------------------------------------------------
    # STAGE 2: CONCURRENT OFFLINE DISCONNECTED MUTATIONS
    # -------------------------------------------------------------------------
    print("\n[Stage 2] Simulating Disconnected Offline Concurrent Operations...")
    print("  -> Buyer operates offline: Inspects shipment and REJECTS 2 damaged units.")

    # Buyer creates signed rejection operation
    op_reject = CompensationEngine.generate_item_rejection(
        transaction=canonical_tx,
        line_id='LINE-01',
        quantity_rejected=Decimal('2.00'),
        replica_id=buyer_replica_id,
        logical_timestamp=2,
        parent_operation_id=op_base.operation_id
    ).sign(buyer_env.private_key_hex)
    print(f"  -> Buyer signed rejection op: {op_reject.operation_id} (Rejected 2 units, Rs 2,360 total reversal)")

    # Concurrently, Seller receives partial bank payment of Rs 5,900
    print("  -> Concurrently, Seller receives bank wire of Rs 5,900 and logs payment allocation.")
    op_payment = AccountingOperation(
        operation_id=f"OP-PAY-{test_run_id}",
        transaction_id=tx_id,
        replica_id=seller_replica_id,
        operation_type=OperationType.PAYMENT_ALLOCATED,
        payload={
            "amount": 5900.0,
            "payment_reference": f"NEFT-{test_run_id}",
            "payment_mode": "BANK"
        },
        logical_timestamp=2,
        parents=[op_base.operation_id]
    ).sign(seller_env.private_key_hex)
    print(f"  -> Seller signed payment op: {op_payment.operation_id} (Paid Rs 5,900)")

    # -------------------------------------------------------------------------
    # STAGE 3: 2-WAY SYNCHRONIZATION & AUTOMATED COMPENSATION PIPELINE
    # -------------------------------------------------------------------------
    print("\n[Stage 3] Reconnection: Executing SyncService with Mandatory Signature Verification...")
    server_ops = [op_base, op_payment]
    client_ops = [op_base.to_dict(), op_reject.to_dict()]

    sync_result = SyncService.process_sync_payload(
        transaction_id=tx_id,
        client_replica_id=seller_replica_id,
        client_operations=client_ops,
        server_operations=server_ops,
        authenticated_tenant_id=str(seller_company.id),
        seller_identity=str(seller_company.gstin),
        buyer_identity=str(buyer_company.gstin),
        canonical_tx=canonical_tx,
        canonical_tx_hash=canonical_hash,
        verify_signatures=True,
        company=seller_company,
        persist_to_db=True,
        user=user
    )

    assert sync_result['status'] == 'SYNC_SUCCESS', f"Sync failed: {sync_result}"
    print(f"  -> CRDT Sync Status: {sync_result['status']}")

    # Verify reciprocal Credit Note was generated automatically
    converged_ops = sync_result['bridge_result']['posted_vouchers']
    print(f"  -> State Commitment: {sync_result['state_commitment']}")
    print(f"  -> Seller Ledger State Root: {sync_result['merkle_state_roots']['seller_ledger_root']}")
    print(f"  -> Buyer Ledger State Root:  {sync_result['merkle_state_roots']['buyer_ledger_root']}")

    # -------------------------------------------------------------------------
    # STAGE 4: SELLER LEDGER BRIDGE EXECUTION & PHYSICAL DB VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[Stage 4] Verifying Authoritative Vouch Accounting Records on Seller...")
    seller_bridge_res = sync_result['bridge_result']
    assert seller_bridge_res['status'] == 'BRIDGE_SUCCESS', f"Bridge failed: {seller_bridge_res}"
    print(f"  -> Bridge execution status: {seller_bridge_res['status']}")
    print(f"  -> Total physical vouchers created: {seller_bridge_res['vouchers_count']}")

    # Inspect physical vouchers created in the database for the Seller
    seller_vouchers = Voucher.objects.filter(company=seller_company, external_invoice_number=tx_id).order_by('voucher_date', 'id')
    print(f"\n  [Seller Physical Database Vouchers]")
    for v in seller_vouchers:
        print(f"    * Voucher #{v.voucher_number} [{v.voucher_type}] Status: {v.status} Total: Rs {v.total_amount}")
        assert v.status == 'POSTED', f"Voucher {v.voucher_number} is not POSTED: {v.status}"

    # Verify the 3 physical vouchers exist: SALES, CREDIT_NOTE, RECEIPT
    v_types = [v.voucher_type for v in seller_vouchers]
    assert 'SALES' in v_types, "Sales voucher missing!"
    assert 'CREDIT_NOTE' in v_types, "Reciprocal Credit Note voucher missing!"
    assert 'RECEIPT' in v_types, "Receipt voucher missing!"

    # Verify double-entry ledger balance on Seller
    seller_entries = LedgerEntry.objects.filter(voucher__in=seller_vouchers)
    total_debits = sum(e.debit_amount for e in seller_entries)
    total_credits = sum(e.credit_amount for e in seller_entries)
    diff = abs(total_debits - total_credits)
    print(f"\n  [Seller Double-Entry Ledger Trial Balance]")
    print(f"    * Total Debits:  Rs {total_debits}")
    print(f"    * Total Credits: Rs {total_credits}")
    print(f"    * Imbalance:     Rs {diff}")
    assert diff < Decimal('0.01'), f"Double-entry violation on Seller! Debits != Credits (Diff: {diff})"

    # Verify customer ledger closing balance: 11,800 (Sale) - 2,360 (Return) - 5,900 (Payment) = 3,540 Dr
    customer_ledger = Ledger.objects.filter(company=seller_company, gstin__iexact=buyer_company.gstin).first()
    assert customer_ledger is not None, "Customer ledger not found!"
    cust_entries = LedgerEntry.objects.filter(ledger=customer_ledger)
    cust_net = sum(e.debit_amount - e.credit_amount for e in cust_entries)
    print(f"\n  [Customer Party Ledger Balance for '{customer_ledger.name}']")
    print(f"    * Net Outstanding Receivable: Rs {cust_net} (Expected: Rs 3540.00)")
    assert cust_net == Decimal('3540.00'), f"Incorrect customer balance: {cust_net} != 3540.00"

    # -------------------------------------------------------------------------
    # STAGE 5: BUYER LEDGER BRIDGE EXECUTION & PHYSICAL DB VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[Stage 5] Executing Authoritative LedgerBridge on Buyer Side...")
    # Reconstruct converged CRDT operations to execute on Buyer side
    buyer_crdt = DE_CRDT(replica_id=buyer_replica_id, transaction_id=tx_id, tenant_id=str(buyer_company.id))
    for op in server_ops + [op_reject]:
        buyer_crdt.apply_operation(op)

    buyer_bridge_res = LedgerBridge.execute_converged_accounting(
        company=buyer_company,
        canonical_tx=canonical_tx,
        converged_operations=buyer_crdt.get_operations(),
        user=user
    )

    assert buyer_bridge_res['status'] == 'BRIDGE_SUCCESS', f"Buyer bridge failed: {buyer_bridge_res}"
    print(f"  -> Buyer Bridge Status: {buyer_bridge_res['status']}")

    buyer_vouchers = Voucher.objects.filter(company=buyer_company, external_invoice_number=tx_id).order_by('voucher_date', 'id')
    print(f"\n  [Buyer Physical Database Vouchers]")
    for v in buyer_vouchers:
        print(f"    * Voucher #{v.voucher_number} [{v.voucher_type}] Status: {v.status} Total: Rs {v.total_amount}")
        assert v.status == 'POSTED', f"Buyer voucher {v.voucher_number} is not POSTED: {v.status}"

    buyer_v_types = [v.voucher_type for v in buyer_vouchers]
    assert 'PURCHASE' in buyer_v_types, "Purchase voucher missing!"
    assert 'DEBIT_NOTE' in buyer_v_types, "Debit Note voucher missing!"
    assert 'PAYMENT' in buyer_v_types, "Payment voucher missing!"

    # Verify double-entry ledger balance on Buyer
    buyer_entries = LedgerEntry.objects.filter(voucher__in=buyer_vouchers)
    buyer_debits = sum(e.debit_amount for e in buyer_entries)
    buyer_credits = sum(e.credit_amount for e in buyer_entries)
    buyer_diff = abs(buyer_debits - buyer_credits)
    print(f"\n  [Buyer Double-Entry Ledger Trial Balance]")
    print(f"    * Total Debits:  Rs {buyer_debits}")
    print(f"    * Total Credits: Rs {buyer_credits}")
    print(f"    * Imbalance:     Rs {buyer_diff}")
    assert buyer_diff < Decimal('0.01'), f"Double-entry violation on Buyer! Debits != Credits (Diff: {buyer_diff})"

    # Verify supplier ledger closing balance: 11,800 (Purchase) - 2,360 (Return) - 5,900 (Payment) = 3,540 Cr
    supplier_ledger = Ledger.objects.filter(company=buyer_company, gstin__iexact=seller_company.gstin).first()
    assert supplier_ledger is not None, "Supplier ledger not found!"
    supp_entries = LedgerEntry.objects.filter(ledger=supplier_ledger)
    supp_net = sum(e.credit_amount - e.debit_amount for e in supp_entries)
    print(f"\n  [Supplier Party Ledger Balance for '{supplier_ledger.name}']")
    print(f"    * Net Outstanding Payable: Rs {supp_net} (Expected: Rs 3540.00)")
    assert supp_net == Decimal('3540.00'), f"Incorrect supplier balance: {supp_net} != 3540.00"

    # Perfect Mirror Equilibrium Check: Seller Receivable == Buyer Payable
    print("\n[Stage 6] Cross-Enterprise Equilibrium Validation:")
    print(f"  -> Seller Net Receivable: Rs {cust_net}")
    print(f"  -> Buyer Net Payable:     Rs {supp_net}")
    assert cust_net == supp_net, f"Equilibrium broken! Seller Receivable {cust_net} != Buyer Payable {supp_net}"
    print("  [CONFIRMED] Perfect mathematical cross-enterprise balance equality (Rs 3,540.00).")

    # -------------------------------------------------------------------------
    # STAGE 7: AUDIT LOG & CRYPTOGRAPHIC COMMITMENT VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[Stage 7] Verifying Django ORM Audit Trails & State Commitments...")
    ptx = ProtocolTransaction.objects.filter(transaction_id=tx_id).first()
    assert ptx is not None, "ProtocolTransaction record missing from database!"

    comm = CryptographicCommitment.objects.filter(transaction=ptx).first()
    assert comm is not None, "CryptographicCommitment record missing from database!"
    print(f"  -> Stored Commitment Hash: {comm.commitment_hash}")
    print(f"  -> Stored State Root:      {comm.operation_state_root}")

    bridge_audit = ProtocolBridgeExecution.objects.filter(transaction_id=tx_id, company_id=str(seller_company.id)).first()
    assert bridge_audit is not None, "ProtocolBridgeExecution audit record missing!"
    print(f"  -> Bridge Execution ID:    {bridge_audit.execution_id}")
    print(f"  -> Idempotency Key:        {bridge_audit.idempotency_key[:32]}...")

    print("\n================================================================================")
    print("   >>> REAL ACCOUNTING E2E TEST PASSED WITH 100% MATHEMATICAL PRECISION <<<     ")
    print("================================================================================\n")


if __name__ == '__main__':
    run_real_accounting_e2e()
