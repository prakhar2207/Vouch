import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.db import transaction
from apps.companies.models import Company
from apps.gst.models import GSTRegistration
from apps.gst.services.gstin_service import GSTINService
from apps.gst.services.audit_service import GSTAuditService
from apps.gst.exceptions import (
    GSTINValidationError,
    DuplicateSubmissionError,
    GSTRegistrationAccessDenied,
)
from apps.gst.services.gst_calculator import VALID_GST_STATE_CODES

logger = logging.getLogger('apps.gst.registration_service')


STATE_CODE_TO_NAME = {
    '01': 'Jammu and Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab', '04': 'Chandigarh',
    '05': 'Uttarakhand', '06': 'Haryana', '07': 'Delhi', '08': 'Rajasthan',
    '09': 'Uttar Pradesh', '10': 'Bihar', '11': 'Sikkim', '12': 'Arunachal Pradesh',
    '13': 'Nagaland', '14': 'Manipur', '15': 'Mizoram', '16': 'Tripura',
    '17': 'Meghalaya', '18': 'Assam', '19': 'West Bengal', '20': 'Jharkhand',
    '21': 'Odisha', '22': 'Chhattisgarh', '23': 'Madhya Pradesh', '24': 'Gujarat',
    '25': 'Daman and Diu', '26': 'Dadra and Nagar Haveli and Daman and Diu', '27': 'Maharashtra',
    '28': 'Andhra Pradesh', '29': 'Karnataka', '30': 'Goa', '31': 'Lakshadweep',
    '32': 'Kerala', '33': 'Tamil Nadu', '34': 'Puducherry', '35': 'Andaman and Nicobar Islands',
    '36': 'Telangana', '37': 'Andhra Pradesh (New)', '38': 'Ladakh', '97': 'Other Territory', '99': 'Centre Jurisdiction'
}


class GSTRegistrationService:
    """
    Dedicated Service for managing Multi-State / Multi-GSTIN Company Registrations.
    Enforces tenant isolation, PAN stem invariance, local format validation,
    duplicate prevention, atomic primary switching, and verification state transitions.
    """

    @classmethod
    def list_registrations(cls, company: Company, include_inactive: bool = True) -> List[GSTRegistration]:
        """
        Lists all GST registrations for a company tenant.
        """
        qs = GSTRegistration.objects.filter(company=company)
        if not include_inactive:
            qs = qs.filter(status='ACTIVE')
        return list(qs.order_by('-is_primary', 'state_code'))

    @classmethod
    def get_registration(cls, company: Company, registration_id: str) -> GSTRegistration:
        """
        Retrieves a single registration with strict tenant isolation.
        """
        reg = GSTRegistration.objects.filter(company=company, id=registration_id).first()
        if not reg:
            raise GSTRegistrationAccessDenied(f"GST Registration '{registration_id}' does not exist for this company.")
        return reg

    @classmethod
    def verify_preview(cls, company: Company, gstin: str, user: Any = None) -> Dict[str, Any]:
        """
        Performs pre-save verification of a GSTIN against local Luhn MOD-36 checks and Sandbox API.
        Returns the normalized taxpayer profile for user review without modifying the database.
        """
        clean_gstin = (gstin or '').strip().upper()
        res = GSTINService.verify_gstin(clean_gstin, company=company, user=user)
        return res

    @classmethod
    def create_registration(
        cls,
        company: Company,
        gstin: str,
        state_code: Optional[str] = None,
        legal_name: Optional[str] = None,
        trade_name: Optional[str] = None,
        address: Optional[str] = None,
        pincode: Optional[str] = None,
        taxpayer_type: str = 'REGULAR',
        is_primary: bool = False,
        auto_verify: bool = True,
        user: Any = None
    ) -> GSTRegistration:
        """
        Creates and optionally verifies a new GST registration for a company.
        Guarantees tenant isolation, duplicate prevention, and PAN stem consistency.
        """
        clean_gstin = (gstin or '').strip().upper()

        # 1. Local Format Check
        fmt = GSTINService.validate_format(clean_gstin)
        if not fmt["valid"]:
            raise GSTINValidationError(fmt["error"])

        resolved_state = state_code or clean_gstin[:2]
        if resolved_state not in VALID_GST_STATE_CODES:
            raise GSTINValidationError(f"Invalid state code '{resolved_state}' in GSTIN.")

        # 2. Duplicate Check within Tenant
        existing = GSTRegistration.objects.filter(company=company, gstin=clean_gstin).first()
        if existing:
            raise DuplicateSubmissionError(
                f"GST Registration with GSTIN '{clean_gstin}' already exists for {company.name}."
            )

        # 3. PAN Stem Invariant: All registrations for an enterprise entity must share the same PAN stem
        clean_pan = clean_gstin[2:12]
        existing_first = GSTRegistration.objects.filter(company=company).first()
        if existing_first:
            existing_pan = existing_first.gstin[2:12]
            if clean_pan != existing_pan:
                raise GSTINValidationError(
                    f"PAN stem mismatch: New GSTIN PAN '{clean_pan}' does not match existing company PAN '{existing_pan}'. "
                    f"All multi-state registrations for an entity must share the identical 10-character PAN stem."
                )

        # 4. Optional Auto-Verification via Sandbox
        verification_status = 'NOT_VERIFIED'
        last_verified_at = None
        provider_ref = ''
        reg_status = 'ACTIVE'

        resolved_legal = legal_name or company.legal_name or company.name
        resolved_trade = trade_name or company.name
        resolved_address = address or company.address or ''
        resolved_pin = pincode or company.pincode or ''
        resolved_type = taxpayer_type

        if auto_verify:
            verify_res = GSTINService.verify_gstin(clean_gstin, company=company, user=user)
            if verify_res.get("success"):
                verification_status = 'VERIFIED'
                last_verified_at = timezone.now()
                provider_ref = verify_res.get("correlation_id", "")
                resolved_legal = verify_res.get("legal_name") or resolved_legal
                resolved_trade = verify_res.get("trade_name") or resolved_trade
                resolved_address = verify_res.get("address") or resolved_address
                resolved_pin = verify_res.get("pincode") or resolved_pin
                resolved_type = verify_res.get("taxpayer_type") or resolved_type

                raw_status = (verify_res.get("status") or "").upper()
                if raw_status in ['CANCELLED', 'INACTIVE']:
                    reg_status = 'CANCELLED'
                    verification_status = 'INACTIVE'
                elif raw_status == 'SUSPENDED':
                    reg_status = 'SUSPENDED'
            else:
                if verify_res.get("source") == "provider_unconfigured":
                    verification_status = 'NOT_VERIFIED'
                else:
                    verification_status = 'PROVIDER_UNAVAILABLE'

        with transaction.atomic():
            # Serialized lock to prevent concurrent double-primary race conditions
            has_other_regs = GSTRegistration.objects.select_for_update().filter(company=company).exists()
            should_be_primary = is_primary or (not has_other_regs)

            if should_be_primary:
                GSTRegistration.objects.select_for_update().filter(company=company, is_primary=True).update(is_primary=False)

            state_name = STATE_CODE_TO_NAME.get(resolved_state, f"State {resolved_state}")

            reg = GSTRegistration.objects.create(
                company=company,
                gstin=clean_gstin,
                legal_name=resolved_legal[:255],
                trade_name=resolved_trade[:255],
                state_code=resolved_state,
                state_name=state_name[:100],
                address=resolved_address,
                pincode=resolved_pin[:10],
                taxpayer_type=resolved_type[:30],
                status=reg_status,
                verification_status=verification_status,
                last_verified_at=last_verified_at,
                provider_reference_id=provider_ref,
                is_primary=should_be_primary
            )

            # Sync primary GSTIN to company model if primary
            if should_be_primary:
                company.gstin = clean_gstin
                company.state_code = resolved_state
                company.state_name = state_name
                company.save(update_fields=['gstin', 'state_code', 'state_name'])

            GSTAuditService.log_action(
                company=company,
                gst_registration=reg,
                action='CREATE_REGISTRATION',
                status_code=201,
                is_success=True,
                request_summary={"gstin": clean_gstin, "state_code": resolved_state, "is_primary": should_be_primary},
                response_summary={"id": str(reg.id), "verification_status": verification_status},
                user=user
            )

        return reg

    @classmethod
    def verify_existing_registration(
        cls,
        company: Company,
        registration_id: str,
        force_refresh: bool = True,
        user: Any = None
    ) -> Dict[str, Any]:
        """
        Re-verifies an existing registration with Sandbox, updating its verification status and details.
        """
        reg = cls.get_registration(company, registration_id)
        verify_res = GSTINService.verify_gstin(reg.gstin, company=company, force_refresh=force_refresh, user=user)

        if verify_res.get("success"):
            reg.verification_status = 'VERIFIED'
            reg.last_verified_at = timezone.now()
            reg.provider_reference_id = verify_res.get("correlation_id", "")
            
            raw_status = (verify_res.get("status") or "").upper()
            if raw_status in ['CANCELLED', 'INACTIVE']:
                reg.status = 'CANCELLED'
                reg.verification_status = 'INACTIVE'
            elif raw_status == 'SUSPENDED':
                reg.status = 'SUSPENDED'
            elif raw_status == 'ACTIVE':
                reg.status = 'ACTIVE'

            reg.save(update_fields=['verification_status', 'last_verified_at', 'provider_reference_id', 'status'])

            GSTAuditService.log_action(
                company=company,
                gst_registration=reg,
                action='VERIFY_REGISTRATION',
                status_code=200,
                is_success=True,
                request_summary={"registration_id": str(reg.id), "gstin": reg.gstin},
                response_summary={"verification_status": reg.verification_status, "status": reg.status},
                user=user
            )
            return {
                "success": True,
                "registration_id": str(reg.id),
                "verification_status": reg.verification_status,
                "data": verify_res
            }
        else:
            err = verify_res.get("error", "Verification failed")
            if "unconfigured" in str(err).lower():
                reg.verification_status = 'NOT_VERIFIED'
            elif "timeout" in str(err).lower() or "504" in str(err):
                reg.verification_status = 'PROVIDER_UNAVAILABLE'
            else:
                reg.verification_status = 'FAILED'
            reg.save(update_fields=['verification_status'])

            return {
                "success": False,
                "registration_id": str(reg.id),
                "verification_status": reg.verification_status,
                "error": err
            }

    @classmethod
    def update_registration(
        cls,
        company: Company,
        registration_id: str,
        data: Dict[str, Any],
        user: Any = None
    ) -> GSTRegistration:
        """
        Updates metadata on an existing GST registration with atomic primary exclusivity.
        """
        reg = cls.get_registration(company, registration_id)
        allowed_fields = [
            'trade_name', 'legal_name', 'address', 'pincode', 'taxpayer_type',
            'einvoice_username', 'eway_username', 'is_primary', 'status'
        ]

        with transaction.atomic():
            for field in allowed_fields:
                if field in data:
                    setattr(reg, field, data[field])

            if data.get('is_primary'):
                GSTRegistration.objects.select_for_update().filter(company=company, is_primary=True).exclude(id=reg.id).update(is_primary=False)
                reg.is_primary = True
                company.gstin = reg.gstin
                company.state_code = reg.state_code
                company.state_name = reg.state_name
                company.save(update_fields=['gstin', 'state_code', 'state_name'])

            reg.save()

            GSTAuditService.log_action(
                company=company,
                gst_registration=reg,
                action='UPDATE_REGISTRATION',
                status_code=200,
                is_success=True,
                request_summary={"registration_id": str(reg.id), "fields": list(data.keys())},
                user=user
            )
        return reg

    @classmethod
    def deactivate_registration(cls, company: Company, registration_id: str, user: Any = None) -> GSTRegistration:
        """
        Marks a registration as INACTIVE without deleting historical accounting vouchers.
        If the deactivated registration was primary, promotes next active registration to primary.
        """
        reg = cls.get_registration(company, registration_id)
        with transaction.atomic():
            reg.status = 'INACTIVE'
            if reg.is_primary:
                next_active = (
                    GSTRegistration.objects.select_for_update()
                    .filter(company=company, status='ACTIVE')
                    .exclude(id=reg.id)
                    .first()
                )
                if next_active:
                    next_active.is_primary = True
                    next_active.save(update_fields=['is_primary'])
                    company.gstin = next_active.gstin
                    company.state_code = next_active.state_code
                    company.state_name = next_active.state_name
                    company.save(update_fields=['gstin', 'state_code', 'state_name'])
                    reg.is_primary = False
            reg.save(update_fields=['status', 'is_primary'])

            GSTAuditService.log_action(
                company=company,
                gst_registration=reg,
                action='DEACTIVATE_REGISTRATION',
                status_code=200,
                is_success=True,
                request_summary={"registration_id": str(reg.id), "status": "INACTIVE"},
                user=user
            )
        return reg

    @classmethod
    def reactivate_registration(cls, company: Company, registration_id: str, user: Any = None) -> GSTRegistration:
        """
        Reactivates an INACTIVE registration.
        If no primary active registration exists, sets this registration as primary.
        """
        reg = cls.get_registration(company, registration_id)
        with transaction.atomic():
            reg.status = 'ACTIVE'
            has_active_primary = GSTRegistration.objects.filter(company=company, status='ACTIVE', is_primary=True).exists()
            if not has_active_primary:
                reg.is_primary = True
                company.gstin = reg.gstin
                company.state_code = reg.state_code
                company.state_name = reg.state_name
                company.save(update_fields=['gstin', 'state_code', 'state_name'])
            reg.save(update_fields=['status', 'is_primary'])

            GSTAuditService.log_action(
                company=company,
                gst_registration=reg,
                action='REACTIVATE_REGISTRATION',
                status_code=200,
                is_success=True,
                request_summary={"registration_id": str(reg.id), "status": "ACTIVE"},
                user=user
            )
        return reg
