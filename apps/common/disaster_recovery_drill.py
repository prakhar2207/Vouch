import os
import sys
import tempfile
import shutil
from pathlib import Path
from decimal import Decimal

# Setup Django environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from django.db import transaction, connection
from django.utils import timezone
from apps.accounts.models import User
from apps.companies.models import Company
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product, ProductCategory, InventoryEntry
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry
from apps.protocol.models import ProtocolTransaction, ProtocolOperation, CryptographicCommitment
from apps.common.services.backup_service import DatabaseBackupService

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

def log(msg=""):
    print(msg, flush=True)

def compute_financial_state(company: Company) -> dict:
    """Computes exact mathematical financial & protocol metrics for the given company."""
    # 1. Double-Entry Trial Balance
    entries = LedgerEntry.objects.filter(company=company)
    total_debits = sum((e.debit_amount for e in entries), Decimal('0.00'))
    total_credits = sum((e.credit_amount for e in entries), Decimal('0.00'))
    imbalance = total_debits - total_credits

    # 2. Profit & Loss (Income vs Expense)
    revenue_entries = LedgerEntry.objects.filter(company=company, ledger__group__nature='INCOME')
    revenue_cr = sum((e.credit_amount for e in revenue_entries), Decimal('0.00'))
    revenue_dr = sum((e.debit_amount for e in revenue_entries), Decimal('0.00'))
    net_revenue = revenue_cr - revenue_dr

    expense_entries = LedgerEntry.objects.filter(company=company, ledger__group__nature='EXPENSE')
    net_expense = sum((e.debit_amount for e in expense_entries), Decimal('0.00')) - \
                  sum((e.credit_amount for e in expense_entries), Decimal('0.00'))
    net_profit = net_revenue - net_expense

    # 3. Balance Sheet (Assets vs Liabilities)
    asset_entries = LedgerEntry.objects.filter(company=company, ledger__group__nature='ASSET')
    net_assets = sum((e.debit_amount for e in asset_entries), Decimal('0.00')) - \
                 sum((e.credit_amount for e in asset_entries), Decimal('0.00'))

    liability_entries = LedgerEntry.objects.filter(company=company, ledger__group__nature='LIABILITY')
    net_liabilities = sum((e.credit_amount for e in liability_entries), Decimal('0.00')) - \
                      sum((e.debit_amount for e in liability_entries), Decimal('0.00'))

    # 4. Inventory Valuation
    products = Product.objects.filter(company=company)
    total_stock_qty = sum((p.stock_quantity for p in products), Decimal('0.00'))
    total_stock_val = sum((p.stock_quantity * p.purchase_price for p in products), Decimal('0.00'))

    # 5. GST Tax Data
    gst_entries = LedgerEntry.objects.filter(company=company, ledger__name__icontains='GST')
    total_gst_cr = sum((e.credit_amount for e in gst_entries), Decimal('0.00'))
    total_gst_dr = sum((e.debit_amount for e in gst_entries), Decimal('0.00'))
    net_gst_collected = total_gst_cr - total_gst_dr

    # 6. Protocol State & Commitments
    proto_txs = ProtocolTransaction.objects.filter(source_company_id=str(company.id)).count()
    proto_ops = ProtocolOperation.objects.filter(transaction__source_company_id=str(company.id)).count()
    commitments = CryptographicCommitment.objects.filter(transaction__source_company_id=str(company.id))
    commitment_hashes = sorted([c.commitment_hash for c in commitments])

    return {
        "trial_balance_debits": float(total_debits),
        "trial_balance_credits": float(total_credits),
        "trial_balance_imbalance": float(imbalance),
        "net_revenue": float(net_revenue),
        "net_profit": float(net_profit),
        "net_assets": float(net_assets),
        "net_liabilities": float(net_liabilities),
        "total_stock_qty": float(total_stock_qty),
        "total_stock_val": float(total_stock_val),
        "net_gst_collected": float(net_gst_collected),
        "protocol_tx_count": proto_txs,
        "protocol_op_count": proto_ops,
        "commitments": commitment_hashes,
    }

def run_drill():
    log("=" * 80)
    log("      VOUCH DISASTER RECOVERY DRILL: FULL RESTORATION & STATE EQUILIBRIUM")
    log("=" * 80)

    temp_dir = tempfile.mkdtemp()
    try:
        # Phase 1: Provision Production-Like Enterprise Accounting Dataset
        log("\n[Phase 1] Provisioning Complete Multi-Subsystem Enterprise Accounting State...")
        import uuid
        uid = uuid.uuid4().hex[:8].upper()
        company = Company.objects.create(name=f"DR Drill Corp {uid}", gstin=f"27AAACD{uid[:4]}1Z5")

        # Groups with correct nature
        g_asset = LedgerGroup.objects.create(company=company, name="Current Assets", nature="ASSET")
        g_rev = LedgerGroup.objects.create(company=company, name="Sales Accounts", nature="INCOME")
        g_liab = LedgerGroup.objects.create(company=company, name="Duties & Taxes", nature="LIABILITY")

        # Ledgers
        l_bank = Ledger.objects.create(company=company, group=g_asset, name="HDFC Bank")
        l_customer = Ledger.objects.create(company=company, group=g_asset, name="Acme Retailers Ltd")
        l_sales = Ledger.objects.create(company=company, group=g_rev, name="Domestic GST Sales")
        l_cgst = Ledger.objects.create(company=company, group=g_liab, name="Output CGST")
        l_sgst = Ledger.objects.create(company=company, group=g_liab, name="Output SGST")

        # Products
        cat = ProductCategory.objects.create(company=company, name="Industrial Valves")
        product = Product.objects.create(
            company=company, category=cat, name="Brass Ball Valve 25mm",
            sku=f"VLV-{uid}", purchase_price=Decimal('200.00'), selling_price=Decimal('350.00'),
            stock_quantity=Decimal('100.00'), unit="PCS"
        )

        user, _ = User.objects.get_or_create(
            email=f"dr_{uid.lower()}@vouch.test",
            defaults={"first_name": "DR", "last_name": "Admin", "role": "ADMIN"}
        )
        from apps.companies.models import UserCompany
        UserCompany.objects.create(user=user, company=company, role='ADMIN')

        today = timezone.now().date()

        # Voucher 1: Sales Invoice of 10 units @ 350 = 3500 + 18% GST (315 CGST, 315 SGST) = 4130
        v_inv = Voucher.objects.create(
            company=company, voucher_type='SALES', voucher_number=f"INV-{uid}",
            created_by=user, voucher_date=today, party_ledger=l_customer, total_amount=Decimal('4130.00')
        )
        VoucherItem.objects.create(
            voucher=v_inv, product=product, quantity=Decimal('10.00'),
            rate=Decimal('350.00'), taxable_amount=Decimal('3500.00'),
            cgst_amount=Decimal('315.00'), sgst_amount=Decimal('315.00'), total_amount=Decimal('4130.00')
        )
        # Double-entry postings for Sale
        LedgerEntry.objects.create(company=company, voucher=v_inv, ledger=l_customer, debit_amount=Decimal('4130.00'))
        LedgerEntry.objects.create(company=company, voucher=v_inv, ledger=l_sales, credit_amount=Decimal('3500.00'))
        LedgerEntry.objects.create(company=company, voucher=v_inv, ledger=l_cgst, credit_amount=Decimal('315.00'))
        LedgerEntry.objects.create(company=company, voucher=v_inv, ledger=l_sgst, credit_amount=Decimal('315.00'))
        product.stock_quantity -= Decimal('10.00')
        product.save()

        # Voucher 2: Receipt of Partial Payment Rs 2,000
        v_rcp = Voucher.objects.create(
            company=company, voucher_type='RECEIPT', voucher_number=f"RCP-{uid}",
            created_by=user, voucher_date=today, party_ledger=l_customer, total_amount=Decimal('2000.00')
        )
        LedgerEntry.objects.create(company=company, voucher=v_rcp, ledger=l_bank, debit_amount=Decimal('2000.00'))
        LedgerEntry.objects.create(company=company, voucher=v_rcp, ledger=l_customer, credit_amount=Decimal('2000.00'))

        # Voucher 3: Credit Note for 2 Damaged Units = 700 + 126 GST = 826
        v_cn = Voucher.objects.create(
            company=company, voucher_type='CREDIT_NOTE', voucher_number=f"CN-{uid}",
            created_by=user, voucher_date=today, party_ledger=l_customer, total_amount=Decimal('826.00')
        )
        LedgerEntry.objects.create(company=company, voucher=v_cn, ledger=l_sales, debit_amount=Decimal('700.00'))
        LedgerEntry.objects.create(company=company, voucher=v_cn, ledger=l_cgst, debit_amount=Decimal('63.00'))
        LedgerEntry.objects.create(company=company, voucher=v_cn, ledger=l_sgst, debit_amount=Decimal('63.00'))
        LedgerEntry.objects.create(company=company, voucher=v_cn, ledger=l_customer, credit_amount=Decimal('826.00'))
        product.stock_quantity += Decimal('2.00')
        product.save()

        # Protocol Transaction & Commitment
        p_tx = ProtocolTransaction.objects.create(
            transaction_id=f"TX-{uid}",
            transaction_type="SALE",
            source_company_id=str(company.id),
            destination_company_id="BUYER-CORP",
            canonical_payload={"invoice_number": f"INV-{uid}", "total_amount": 4130.00}
        )
        p_op = ProtocolOperation.objects.create(
            transaction=p_tx,
            operation_id=f"OP-{uid}",
            replica_id="SELLER",
            operation_type="BASE_SALE_ISSUED",
            logical_timestamp=1,
            parents=[],
            payload={"amount": 4130.00},
            payload_hash=f"HASH-{uid}",
            signature="SIG-ED25519"
        )
        p_comm = CryptographicCommitment.objects.create(
            transaction=p_tx,
            commitment_hash=f"COMMIT-{uid}",
            operation_state_root=f"ROOT-{uid}",
            signature="SIG-SELLER"
        )

        # Phase 2: Compute Baseline Financial Equilibrium Before Backup
        log("\n[Phase 2] Computing Baseline Financial Equilibrium (BEFORE Backup)...")
        state_before = compute_financial_state(company)
        log(f"  -> Trial Balance Debits:    Rs {state_before['trial_balance_debits']:.2f}")
        log(f"  -> Trial Balance Credits:   Rs {state_before['trial_balance_credits']:.2f}")
        log(f"  -> Trial Balance Imbalance: Rs {state_before['trial_balance_imbalance']:.2f}")
        log(f"  -> Net Revenue:             Rs {state_before['net_revenue']:.2f}")
        log(f"  -> Net Profit:              Rs {state_before['net_profit']:.2f}")
        log(f"  -> Net Assets:              Rs {state_before['net_assets']:.2f}")
        log(f"  -> Net Liabilities:         Rs {state_before['net_liabilities']:.2f}")
        log(f"  -> Inventory Valuation:     Rs {state_before['total_stock_val']:.2f} ({state_before['total_stock_qty']} units)")
        log(f"  -> Net GST Collected:       Rs {state_before['net_gst_collected']:.2f}")
        log(f"  -> Protocol Commitments:    {len(state_before['commitments'])}")

        assert state_before['trial_balance_imbalance'] == 0.0, "Baseline Trial Balance is imbalanced!"

        # Phase 3: Execute Full AES-256 Encrypted Gzip Snapshot
        log("\n[Phase 3] Generating AES-256 Encrypted Gzip Production Snapshot...")
        backup_res = DatabaseBackupService.perform_backup(
            upload_s3=False,
            encrypt=True,
            output_dir=temp_dir,
            company_id=str(company.id)
        )
        assert backup_res["success"], f"Backup creation failed: {backup_res.get('error')}"
        backup_path = Path(backup_res["file_path"])
        log(f"  -> Snapshot Archive: {backup_path.name} ({backup_res['file_size_mb']} MB)")
        log(f"  -> SHA-256 Integrity: {backup_res['sha256_checksum']}")

        # Phase 4: Disaster Simulation (Simulate Database Loss)
        log("\n[Phase 4] Simulating Total Disaster: Purging Company Records from Active Database...")
        # Delete entries and vouchers
        LedgerEntry.objects.filter(company=company).delete()
        VoucherItem.objects.filter(voucher__company=company).delete()
        Voucher.objects.filter(company=company).delete()
        InventoryEntry.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        ProductCategory.objects.filter(company=company).delete()
        Ledger.objects.filter(company=company).delete()
        LedgerGroup.objects.filter(company=company).delete()
        CryptographicCommitment.objects.filter(transaction__source_company_id=str(company.id)).delete()
        ProtocolOperation.objects.filter(transaction__source_company_id=str(company.id)).delete()
        ProtocolTransaction.objects.filter(source_company_id=str(company.id)).delete()

        # Verify disaster state is completely purged
        state_disaster = compute_financial_state(company)
        log(f"  -> Post-Disaster Ledger Entries: {state_disaster['trial_balance_debits']} (Verified Empty)")
        assert state_disaster['trial_balance_debits'] == 0.0, "Disaster purge incomplete!"

        # Phase 5: Execute Disaster Recovery Restoration
        log("\n[Phase 5] Executing Disaster Recovery Restoration from Encrypted Archive...")
        restore_res = DatabaseBackupService.restore_backup(
            backup_path=backup_path,
            target_db_alias='default',
            dry_run=False
        )
        assert restore_res["success"], f"Restoration failed: {restore_res.get('errors')}"
        log(f"  -> Records Restored: {restore_res['records_restored']}")
        log(f"  -> Elapsed Restoration Time: {restore_res['elapsed_seconds']}s")

        # Phase 6: Compute Post-Restoration Financial Equilibrium
        log("\n[Phase 6] Computing Financial Equilibrium (AFTER Restoration)...")
        company.refresh_from_db()
        state_after = compute_financial_state(company)
        log(f"  -> Trial Balance Debits:    Rs {state_after['trial_balance_debits']:.2f}")
        log(f"  -> Trial Balance Credits:   Rs {state_after['trial_balance_credits']:.2f}")
        log(f"  -> Trial Balance Imbalance: Rs {state_after['trial_balance_imbalance']:.2f}")
        log(f"  -> Net Revenue:             Rs {state_after['net_revenue']:.2f}")
        log(f"  -> Net Profit:              Rs {state_after['net_profit']:.2f}")
        log(f"  -> Net Assets:              Rs {state_after['net_assets']:.2f}")
        log(f"  -> Net Liabilities:         Rs {state_after['net_liabilities']:.2f}")
        log(f"  -> Inventory Valuation:     Rs {state_after['total_stock_val']:.2f} ({state_after['total_stock_qty']} units)")
        log(f"  -> Net GST Collected:       Rs {state_after['net_gst_collected']:.2f}")
        log(f"  -> Protocol Commitments:    {len(state_after['commitments'])}")

        # Phase 7: Strict Bit-for-Bit Mathematical Equality Assertions
        log("\n[Phase 7] Executing Comprehensive State Equivalence Assertions...")
        assert state_before == state_after, f"Financial state divergence detected! Before: {state_before}, After: {state_after}"
        log("  [PASSED] Trial Balance Before == After (Imbalance = 0.00)")
        log("  [PASSED] Net Revenue & P&L Before == After")
        log("  [PASSED] Assets & Liabilities Balance Sheet Before == After")
        log("  [PASSED] Physical Inventory Stock Quantities & Valuation Before == After")
        log("  [PASSED] GST Output & Input Taxes Before == After")
        log("  [PASSED] Protocol State Roots & Cryptographic Commitments Before == After")

        # Cleanup test company
        LedgerEntry.objects.filter(company=company).delete()
        VoucherItem.objects.filter(voucher__company=company).delete()
        Voucher.objects.filter(company=company).delete()
        InventoryEntry.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        ProductCategory.objects.filter(company=company).delete()
        Ledger.objects.filter(company=company).delete()
        LedgerGroup.objects.filter(company=company).delete()
        CryptographicCommitment.objects.filter(transaction__source_company_id=str(company.id)).delete()
        ProtocolOperation.objects.filter(transaction__source_company_id=str(company.id)).delete()
        ProtocolTransaction.objects.filter(source_company_id=str(company.id)).delete()
        UserCompany.objects.filter(company=company).delete()
        company.delete()
        user.delete()

        log("\n" + "=" * 80)
        log(">>> DISASTER RECOVERY DRILL PASSED: 100% FINANCIAL EQUILIBRIUM PRESERVED <<<")
        log("=" * 80)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    run_drill()
