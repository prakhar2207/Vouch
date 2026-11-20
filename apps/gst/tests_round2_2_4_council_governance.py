import uuid
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.companies.models import Company
from apps.accounting.models import Voucher, VoucherItem
from apps.ledgers.models import LedgerGroup, Ledger
from apps.inventory.models import Product
from apps.gst.models import GSTRegistration
from apps.gst.services.rate_reference_service import (
    GSTRateScheduleService,
    StatutoryChangeEntry
)

User = get_user_model()


class GSTRound224CouncilGovernanceTests(TestCase):
    """
    SriLekh GST — Round 2.2.4: 57th Council Directives, CBIC Clarifications & Statutory Compliance Register.

    Statutory Invariants & Verifications:
    1. Mandatory Sandbox Tenant Isolation Invariant (Apex Belting Store only: 4e62863a-08f9-4e99-b0bd-64873acfdd33).
    2. Sublimation Paper (HSN 4809) — CBIC Circular No. 265/11/2026-GST:
       - Attracts 18% standard rate under Schedule III S.No. 112.
       - Past periods regularised on "as is where is" basis prior to 28-Oct-2026.
       - 12% on or after 28-Oct-2026 is STATUTORY_MISMATCH (expected 18%).
       - 12% before 28-Oct-2026 with AS_IS_WHERE_IS_REGULARIZATION is VALID.
    3. Toys (HSN 9503) — CBIC Circular No. 265/11/2026-GST:
       - Standard 12% rate under Schedule II S.No. 228.
       - General electronic parts/batteries not adapted solely for toys attract 18% under Chapter 85.
       - Video/arcade games attract 28% under heading 9504.
    4. Used Motor Vehicles under Margin Scheme — Notif 8/2018-CT(Rate) & Cir 265:
       - 18% or 12% on margin of supply; 0% Compensation Cess.
       - Non-zero cess is STATUTORY_MISMATCH.
       - ITC Scope: Dealer CANNOT claim ITC on purchase of used vehicle; repair parts and overheads ELIGIBLE under Section 16.
    5. Seaweed-Extract Bio-Stimulants (HSN 3101) — CBIC Circular No. 265/11/2026-GST:
       - Attracts 5% (Schedule I S.No. 182) strictly conditional on FCO 1985 registration.
       - Unregistered products classified under 3808/3824 @ 18% (STATUTORY_MISMATCH).
       - Missing FCO attribute under strict classification returns REVIEW_REQUIRED.
    6. CBIC Instruction No. 02/2026-GST (30-Oct-2026):
       - Arrest-related safeguards under Section 69.
       - E-Way Bill minor clerical error protections (no detention, max Rs. 1,000 penalty under Section 125).
       - Rs. 10,000 threshold for issuing Show Cause Notices for petty tax mismatches.
       - INVARIANT: Pure administrative guidance; zero effect on tax rates or return calculations.
    7. Statutory Governance Taxonomy & Query API:
       - Structured legal sources, issuing authorities, affected modules, enforceability flags.
    8. Double-Entry Accounting Immutability:
       - Zero mutation of posted vouchers or ledger balances.
    """

    def setUp(self):
        # Mandatory Dedicated Sandbox Tenant Isolation Invariant
        self.company = Company.objects.create(
            id=uuid.UUID('4e62863a-08f9-4e99-b0bd-64873acfdd33'),
            name='Apex Belting & Industrial Store (Demo)'
        )
        assert str(self.company.id) == '4e62863a-08f9-4e99-b0bd-64873acfdd33', (
            "CRITICAL SECURITY INVARIANT VIOLATION: Tests must strictly run against sandbox company!"
        )

        self.owner_user = User.objects.create_user(
            email='governance_auditor@apexbelting.demo',
            password='audit_secure_password_123'
        )

        self.reg_primary = GSTRegistration.objects.create(
            company=self.company,
            gstin='27AAACA9999A1Z5',
            legal_name='Apex Belting & Industrial Store',
            trade_name='Apex Belting Store',
            state_code='27',
            state_name='Maharashtra',
            is_primary=True,
            status='ACTIVE'
        )

    # =========================================================================
    # 1. Sublimation Paper (HSN 4809) — CBIC Circular No. 265/11/2026-GST
    # =========================================================================

    def test_sublimation_paper_standard_18_percent(self):
        """Sublimation paper under heading 4809 attracts 18% GST (Schedule III S.No. 112)."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('18.00'),
            is_interstate=False
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)
        self.assertEqual(res["applied_cess"], 0.00)
        self.assertIn("Circular No. 265", res["notification_reference"])

    def test_sublimation_paper_12_percent_post_circular_is_mismatch(self):
        """Applying 12% on or after 28-Oct-2026 is STATUTORY_MISMATCH (expected 18%)."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)
        self.assertIn("Circular No. 265/11/2026-GST", res["issue"]["description"])

    def test_sublimation_paper_past_period_as_is_where_is_regularization(self):
        """
        Applying 12% prior to 28-Oct-2026 with AS_IS_WHERE_IS_REGULARIZATION
        is regularised and treated as VALID per Circular 265/11/2026-GST.
        """
        # With condition tag
        res_with_tag = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 6, 15),
            applied_rate=Decimal('12.00'),
            is_interstate=False,
            conditions=['AS_IS_WHERE_IS_REGULARIZATION']
        )
        self.assertEqual(res_with_tag["status"], "VALID")
        self.assertTrue(res_with_tag["is_statutorily_valid"])
        self.assertEqual(res_with_tag["expected_rate"], 12.00)
        self.assertIn("Circular No. 265/11/2026-GST", res_with_tag["notification_reference"])

        # With product attribute
        res_with_attr = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 6, 15),
            applied_rate=Decimal('12.00'),
            is_interstate=False,
            product_attributes={'as_is_where_is': True}
        )
        self.assertEqual(res_with_attr["status"], "VALID")
        self.assertTrue(res_with_attr["is_statutorily_valid"])

    def test_sublimation_paper_past_period_without_regularization_tag(self):
        """Applying 12% prior to 28-Oct-2026 without regularization flag is STATUTORY_MISMATCH."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 6, 15),
            applied_rate=Decimal('12.00'),
            is_interstate=False
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)

    # =========================================================================
    # 2. Toys (HSN 9503) — CBIC Circular No. 265/11/2026-GST
    # =========================================================================

    def test_toys_standard_12_percent(self):
        """Toys under heading 9503 attract standard 12% GST (Schedule II S.No. 228)."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 12.00)
        self.assertEqual(res["applied_cess"], 0.00)

    def test_toys_general_electronic_part_disqualification(self):
        """
        General electronic parts/batteries cannot claim 12% under heading 9503;
        they attract 18% under Chapter 85 (Circular 265/11/2026-GST).
        """
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False,
            conditions=['GENERAL_ELECTRONIC_COMPONENT']
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)
        self.assertIn("Chapter 85", res["issue"]["description"])

        # With product attribute
        res_attr = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False,
            product_attributes={'is_general_electronic_part': True}
        )
        self.assertEqual(res_attr["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_attr["expected_rate"], 18.00)

    def test_toys_arcade_game_heading_9504_disqualification(self):
        """Arcade/video games cannot claim 12% under 9503; they attract 28% under heading 9504."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False,
            conditions=['ARCADE_GAME_9504']
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 28.00)
        self.assertIn("heading 9504", res["issue"]["description"])

    # =========================================================================
    # 3. Used Motor Vehicles Margin Scheme — Notif 8/2018-CT(Rate) & Cir 265
    # =========================================================================

    def test_used_motor_vehicles_margin_scheme_rate_and_zero_cess(self):
        """Used motor vehicles under Margin Scheme attract 18% on margin with 0% cess."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('18.00'),
            applied_cess=Decimal('0.00'),
            is_interstate=False,
            conditions=['MARGIN_SCHEME']
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)
        self.assertEqual(res["expected_cess"], 0.00)
        self.assertIn("8/2018", res["notification_reference"])

    def test_used_motor_vehicles_margin_scheme_cess_is_mismatch(self):
        """Applying non-zero compensation cess under Margin Scheme is STATUTORY_MISMATCH."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('18.00'),
            applied_cess=Decimal('22.00'),
            is_interstate=False,
            conditions=['MARGIN_SCHEME']
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_cess"], 0.00)
        self.assertIn("GST_COMPENSATION_CESS_MISMATCH", res["issue"]["code"])

    def test_used_motor_vehicles_margin_scheme_standard_28_is_mismatch(self):
        """Applying standard 28% to used vehicles under Margin Scheme is STATUTORY_MISMATCH."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='8703',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('28.00'),
            applied_cess=Decimal('0.00'),
            is_interstate=False,
            conditions=['MARGIN_SCHEME']
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)

    def test_margin_scheme_itc_differentiation(self):
        """
        Circular No. 265/11/2026-GST clarifies ITC scope under Margin Scheme:
        - Used vehicle purchase: BLOCKED (INELIGIBLE_MARGIN_SCHEME_VEHICLE).
        - Spares / repair parts: ELIGIBLE under Section 16.
        - General overheads / rent: ELIGIBLE under Section 16.
        """
        # Purchase of used vehicle: strictly blocked
        elig_veh, ok_veh, reason_veh = GSTRateScheduleService.evaluate_margin_scheme_itc('USED_VEHICLE_PURCHASE')
        self.assertEqual(elig_veh, 'INELIGIBLE_MARGIN_SCHEME_VEHICLE')
        self.assertFalse(ok_veh)
        self.assertIn("strictly blocked", reason_veh)

        # Spares and repair parts: eligible under Section 16
        elig_parts, ok_parts, reason_parts = GSTRateScheduleService.evaluate_margin_scheme_itc('REPAIR_PARTS_SPARES')
        self.assertEqual(elig_parts, 'ELIGIBLE')
        self.assertTrue(ok_parts)
        self.assertIn("Section 16", reason_parts)

        # General business overheads and rent: eligible under Section 16
        elig_rent, ok_rent, reason_rent = GSTRateScheduleService.evaluate_margin_scheme_itc('GENERAL_OVERHEADS_RENT')
        self.assertEqual(elig_rent, 'ELIGIBLE')
        self.assertTrue(ok_rent)
        self.assertIn("Section 16", reason_rent)

    # =========================================================================
    # 4. Seaweed-Extract Bio-Stimulants (HSN 3101) — Circular 265/11/2026-GST
    # =========================================================================

    def test_bio_stimulants_fco_registered_qualifies_for_5_percent(self):
        """Bio-stimulants registered under FCO 1985 attract 5% (Schedule I S.No. 182)."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='3101',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            conditions=['FCO_REGISTERED_BIO_STIMULANT']
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 5.00)
        self.assertIn("182", res["notification_reference"])

        # With product attributes
        res_attr = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='3101',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            product_attributes={'is_bio_stimulant': True, 'is_fco_registered': True}
        )
        self.assertEqual(res_attr["status"], "VALID")
        self.assertTrue(res_attr["is_statutorily_valid"])

    def test_bio_stimulants_unregistered_is_mismatch_attracts_18_percent(self):
        """
        Unregistered bio-stimulants cannot claim 5% under heading 3101;
        they attract 18% under heading 3808/3824 (Circular 265/11/2026-GST).
        """
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='3101',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            conditions=['UNREGISTERED_BIO_STIMULANT']
        )
        self.assertEqual(res["status"], "STATUTORY_MISMATCH")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertEqual(res["expected_rate"], 18.00)
        self.assertIn("Fertiliser (Control) Order", res["issue"]["description"])

        # With product attributes
        res_attr = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='3101',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            product_attributes={'is_bio_stimulant': True, 'is_fco_registered': False}
        )
        self.assertEqual(res_attr["status"], "STATUTORY_MISMATCH")
        self.assertEqual(res_attr["expected_rate"], 18.00)

    def test_bio_stimulants_strict_classification_requires_fco_attribute(self):
        """Under strict classification, missing FCO registration attribute returns REVIEW_REQUIRED."""
        res = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='3101',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('5.00'),
            is_interstate=False,
            strict_classification=True,
            product_attributes={'is_bio_stimulant': True}
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertFalse(res["is_statutorily_valid"])
        self.assertIn("is_fco_registered", res["missing_attributes"])

    # =========================================================================
    # 5. CBIC Instruction No. 02/2026-GST (30-Oct-2026) Guidance
    # =========================================================================

    def test_instruction_02_eway_bill_minor_clerical_typo(self):
        """E-way bill minor clerical error guidance prevents vehicle detention and Section 129 penalty."""
        guidance = GSTRateScheduleService.evaluate_administrative_guidance(
            issue_type='EWAY_BILL_MINOR_ERROR',
            context={'is_minor_clerical_error': True}
        )
        self.assertEqual(guidance["instruction_reference"], "CBIC Instruction No. 02/2026-GST")
        self.assertTrue(guidance["is_binding_on_department"])
        self.assertFalse(guidance["statutory_rate_affected"])
        self.assertFalse(guidance["return_calculation_affected"])
        self.assertIn("No detention", guidance["summary"])
        self.assertIn("Rs. 1,000", guidance["details"])

    def test_instruction_02_arrest_safeguards_section_69(self):
        """Arrest safeguards require Principal Commissioner approval and organized evasion."""
        guidance = GSTRateScheduleService.evaluate_administrative_guidance(
            issue_type='ARREST_SAFEGUARD'
        )
        self.assertEqual(guidance["instruction_reference"], "CBIC Instruction No. 02/2026-GST & 57th Council Press Release")
        self.assertTrue(guidance["is_binding_on_department"])
        self.assertFalse(guidance["statutory_rate_affected"])
        self.assertFalse(guidance["return_calculation_affected"])
        self.assertIn("Section 69", guidance["summary"])
        self.assertIn("Principal Commissioner", guidance["details"])

    def test_instruction_02_scn_threshold_10k(self):
        """Show Cause Notice threshold of Rs. 10,000 for petty tax discrepancies."""
        # Below threshold (Rs. 6,500 mismatch)
        guidance_low = GSTRateScheduleService.evaluate_administrative_guidance(
            issue_type='SCN_THRESHOLD',
            context={'tax_mismatch_amount': Decimal('6500.00')}
        )
        self.assertTrue(guidance_low["is_below_statutory_threshold"])
        self.assertFalse(guidance_low["statutory_rate_affected"])
        self.assertFalse(guidance_low["return_calculation_affected"])
        self.assertIn("Rs. 10,000", guidance_low["summary"])

        # Above threshold (Rs. 25,000 mismatch)
        guidance_high = GSTRateScheduleService.evaluate_administrative_guidance(
            issue_type='SCN_THRESHOLD',
            context={'tax_mismatch_amount': Decimal('25000.00')}
        )
        self.assertFalse(guidance_high["is_below_statutory_threshold"])

    # =========================================================================
    # 6. Statutory Governance Taxonomy & Query API
    # =========================================================================

    def test_statutory_change_register_taxonomy_completeness(self):
        """Statutory change register contains all 12 tracked entries with full taxonomy fields."""
        entries = GSTRateScheduleService.get_statutory_change_register()
        self.assertEqual(len(entries), 12)

        ref_ids = [e.reference_id for e in entries]
        expected_refs = [
            '55TH-01', '56TH-01', '56TH-02', '56TH-03',
            '57TH-PRESS', '57TH-01', '57TH-02',
            'CIR-265-4809', 'CIR-265-9503', 'CIR-265-USED-VEH', 'CIR-265-3101',
            'INS-02-2026'
        ]
        for ref in expected_refs:
            self.assertIn(ref, ref_ids, f"Missing reference_id {ref} in register")

        # Verify all entries have valid taxonomy fields
        valid_sources = {
            'GAZETTED_NOTIFICATION', 'STATUTORY_AMENDMENT', 'CBIC_CIRCULAR',
            'CBIC_INSTRUCTION', 'GST_COUNCIL_RECOMMENDATION', 'OFFICIAL_FAQ', 'PENDING_LEGAL_ACTION'
        }
        valid_modules = {'RATE_ENGINE', 'CLASSIFICATION', 'ITC_ELIGIBILITY', 'RETURN_PREP', 'COMPLIANCE_GUIDANCE', 'NONE'}

        for entry in entries:
            self.assertIn(entry.legal_source, valid_sources)
            self.assertIn(entry.affected_module, valid_modules)
            self.assertIsNotNone(entry.last_reviewed_date)

    def test_filter_change_register_by_legal_source_and_module(self):
        """Filter register by legal source and affected module."""
        circ_entries = GSTRateScheduleService.get_statutory_change_register(legal_source='CBIC_CIRCULAR')
        self.assertEqual(len(circ_entries), 4)

        ins_entries = GSTRateScheduleService.get_statutory_change_register(legal_source='CBIC_INSTRUCTION')
        self.assertEqual(len(ins_entries), 1)
        self.assertEqual(ins_entries[0].reference_id, 'INS-02-2026')

        rate_entries = GSTRateScheduleService.get_statutory_change_register(affected_module='RATE_ENGINE')
        self.assertGreaterEqual(len(rate_entries), 5)

    def test_enforceability_checks(self):
        """Enforceability check distinguishes gazetted/enforceable law from administrative/pending items."""
        # Active gazetted notification is enforceable
        self.assertTrue(GSTRateScheduleService.is_legally_enforceable('56TH-01'))
        self.assertTrue(GSTRateScheduleService.is_legally_enforceable('55TH-01'))

        # CBIC Circular is enforceable
        self.assertTrue(GSTRateScheduleService.is_legally_enforceable('CIR-265-4809'))
        self.assertTrue(GSTRateScheduleService.is_legally_enforceable('CIR-265-9503'))

        # Administrative instruction is binding on department, but NOT enforceable tax law
        self.assertFalse(GSTRateScheduleService.is_legally_enforceable('INS-02-2026'))

        # Pending Council recommendations are NOT legally enforceable
        self.assertFalse(GSTRateScheduleService.is_legally_enforceable('57TH-01'))
        self.assertFalse(GSTRateScheduleService.is_legally_enforceable('57TH-PRESS'))

    # =========================================================================
    # 7. Double-Entry Accounting Immutability & Persistence Isolation
    # =========================================================================

    def test_double_entry_accounting_immutability(self):
        """
        Verify that rate validation, classification, and governance queries
        are strictly pure functions with zero side-effects or mutations on accounting ledgers.
        """
        # Create standard accounting ledger structure
        lg_sales = LedgerGroup.objects.create(
            company=self.company,
            name='Sales Accounts',
            nature='INCOME'
        )
        lg_debtors = LedgerGroup.objects.create(
            company=self.company,
            name='Sundry Debtors',
            nature='ASSET'
        )

        l_sales = Ledger.objects.create(
            company=self.company,
            group=lg_sales,
            name='Industrial Sales A/c'
        )
        l_customer = Ledger.objects.create(
            company=self.company,
            group=lg_debtors,
            name='Customer Demo A/c'
        )

        prod = Product.objects.create(
            company=self.company,
            name='Sublimation Transfer Paper Pack',
            hsn_code='4809',
            unit='BOX'
        )

        # Create sample voucher
        voucher = Voucher.objects.create(
            company=self.company,
            voucher_type='SALES',
            voucher_number='INV-2026-GOV-001',
            voucher_date=date(2026, 11, 1),
            status='POSTED',
            narration='Sublimation paper sales invoice',
            created_by=self.owner_user
        )
        VoucherItem.objects.create(
            voucher=voucher,
            product=prod,
            quantity=Decimal('10.00'),
            rate=Decimal('500.00'),
            taxable_amount=Decimal('5000.00'),
            hsn_code='4809'
        )

        # Snapshot voucher state before governance service calls
        v_count_before = Voucher.objects.filter(company=self.company).count()
        vi_count_before = VoucherItem.objects.filter(voucher=voucher).count()
        l_count_before = Ledger.objects.filter(company=self.company).count()

        # Execute multiple governance and rate engine evaluations
        r1 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='4809',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('18.00'),
            is_interstate=False
        )
        r2 = GSTRateScheduleService.validate_tax_rate(
            hsn_sc='9503',
            tx_date=date(2026, 11, 1),
            applied_rate=Decimal('12.00'),
            is_interstate=False
        )
        r3 = GSTRateScheduleService.evaluate_administrative_guidance('EWAY_BILL_MINOR_ERROR')
        r4 = GSTRateScheduleService.get_statutory_change_register()

        # Verify zero database mutations
        v_count_after = Voucher.objects.filter(company=self.company).count()
        vi_count_after = VoucherItem.objects.filter(voucher=voucher).count()
        l_count_after = Ledger.objects.filter(company=self.company).count()

        self.assertEqual(v_count_before, v_count_after)
        self.assertEqual(vi_count_before, vi_count_after)
        self.assertEqual(l_count_before, l_count_after)
        self.assertEqual(voucher.status, 'POSTED')
