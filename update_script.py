old_code = '''        inward_req, _ = InwardVoucherRequest.objects.update_or_create(
            source_voucher=voucher,
            target_company=target_company,
            defaults={
                "source_company": voucher.company,
                "payload": payload,
                "status": "PENDING",
            }
        )

        return inward_req'''

new_code = '''        inward_req, created = InwardVoucherRequest.objects.update_or_create(
            source_voucher=voucher,
            target_company=target_company,
            defaults={
                "source_company": voucher.company,
                "payload": payload,
                "status": "PENDING",
            }
        )

        if created:
            try:
                from apps.notifications.services import NotificationService
                for uc in target_company.users.all():
                    NotificationService.send_notification(
                        user=uc.user,
                        title="New Inward EDI Request",
                        message=f"{voucher.company.name} sent you a purchase bill request (#{voucher.voucher_number}) for ₹{voucher.total_amount:,.2f}.",
                        link="/network/inbox"
                    )
            except Exception as e:
                import traceback
                logger.error(f"Failed to send EDI notification: {e} \\n {traceback.format_exc()}")

        return inward_req'''

with open('apps/accounting/services/edi_service.py', 'rb') as f:
    text = f.read().decode('utf-8-sig')

if old_code in text:
    text = text.replace(old_code, new_code)
    with open('apps/accounting/services/edi_service.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Success')
else:
    print('Failed')
