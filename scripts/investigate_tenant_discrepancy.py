import os
import sys
import socket
from collections import Counter
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# JioFiber WAN DNS Workaround for Neon PostgreSQL
_orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, *args, **kwargs):
    if 'neon.tech' in host:
        return _orig_getaddrinfo('52.76.246.190', port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = patched_getaddrinfo

import django
django.setup()

from apps.accounting.models import Voucher, LedgerEntry, Company
from apps.audit.models import AuditLog

from django.db.models import Sum

PROTECTED_ID = '5d2e5dea-ff86-4871-b2af-fe1c5a05c03c'

def investigate():
    print("=" * 80, flush=True)
    print("PHASE 2: INVESTIGATION OF PROTECTED TENANT BASELINE DISCREPANCY", flush=True)
    print("=" * 80, flush=True)
    company = Company.objects.filter(id=PROTECTED_ID).first()
    assert company is not None, f"Protected company {PROTECTED_ID} not found!"
    print(f"Company: {company.name} ({company.id})", flush=True)
    
    qs = Voucher.objects.filter(company=company).order_by('created_at')
    total_count = qs.count()
    print(f"Total Vouchers: {total_count}", flush=True)
    
    # Status breakdown
    counts = Counter(qs.values_list('status', flat=True))
    print(f"Status Breakdown: {dict(counts)}", flush=True)
    
    types = Counter(qs.values_list('voucher_type', flat=True))
    print(f"Type Breakdown: {dict(types)}", flush=True)
    
    # Check creation dates
    print("\n--- CHRONOLOGICAL CREATION TIMELINE ---", flush=True)
    dates = list(qs.values_list('created_at', flat=True))
    creation_dates = Counter(dt.date() for dt in dates)
    for dt, cnt in sorted(creation_dates.items()):
        print(f"  Date {dt}: {cnt} voucher(s) created", flush=True)

    # Let's inspect the vouchers in chronological slice 470 to 484
    # Defer heavy binary attachment fields for rapid WAN query
    vouchers = list(qs.defer('attachment_data', 'attachment_mime').select_related('party_ledger')[465:485])
    print("\n--- SLICE 466 TO 484 VOUCHERS ---", flush=True)
    for idx, v in enumerate(vouchers, start=466):
        entries = list(LedgerEntry.objects.filter(voucher=v).select_related('ledger'))
        d_sum = sum(e.debit_amount for e in entries)
        c_sum = sum(e.credit_amount for e in entries)
        bal_str = f"Bal: ₹{d_sum} == ₹{c_sum}" if d_sum == c_sum else f"UNBALANCED: D={d_sum}, C={c_sum}"
        party_name = v.party_ledger.name if v.party_ledger else "NoParty"
        print(f"[{idx:03d}] {v.voucher_number} | {v.voucher_type:<8} | Date: {v.voucher_date} | Created: {v.created_at} | Status: {v.status:<7} | Amt: ₹{v.total_amount:>10.2f} | Party: {party_name} | {bal_str}", flush=True)

    print("\n--- DETAILED INSPECTION OF VOUCHERS 471 TO 484 ---", flush=True)
    for idx, v in enumerate(vouchers[5:], start=471):
        logs = list(AuditLog.objects.filter(record_id=v.id))
        log_info = ', '.join([f'{l.action} by {l.user} ({l.created_at})' for l in logs]) if logs else 'No AuditLog'
        orig = getattr(v, 'original_invoice', None)
        orig_str = f"OrigInvoice={orig.voucher_number}" if orig else "NoOrig"
        print(f"[{idx}] {v.voucher_number} ({v.voucher_type}) | CreatedBy: {v.created_by} | {orig_str} | Narration: '{v.narration}'", flush=True)
        if logs:
            print(f"     AuditLog: {log_info}", flush=True)
    totals = LedgerEntry.objects.filter(company=company).aggregate(
        total_debit=Sum('debit_amount'),
        total_credit=Sum('credit_amount')
    )
    total_debits = totals['total_debit'] or Decimal('0.00')
    total_credits = totals['total_credit'] or Decimal('0.00')
    print(f"\nOverall Books Equilibrium: Total Debits = ₹{total_debits:.2f}, Total Credits = ₹{total_credits:.2f}", flush=True)
    assert total_debits == total_credits, f"EQUILIBRIUM BREACH: Debits ({total_debits}) != Credits ({total_credits})"
    print("Mathematical Equilibrium Invariant: PERFECTLY BALANCED (Total Debits == Total Credits)", flush=True)
    print("=" * 80, flush=True)

if __name__ == '__main__':
    investigate()
