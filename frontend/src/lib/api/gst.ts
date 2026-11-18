import axios from 'axios';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken } from '@/utils/auth';

function getHeaders(companyId?: string) {
  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (companyId) {
    headers['X-Company-ID'] = companyId;
  }
  return headers;
}

export interface GSTTaxpayerDetails {
  success: boolean;
  gstin: string;
  legal_name: string;
  trade_name: string;
  state_code: string;
  state_name: string;
  address: string;
  pincode: string;
  taxpayer_type: string;
  status: string;
  registration_date?: string;
  center_jurisdiction?: string;
  state_jurisdiction?: string;
  is_cached?: boolean;
  is_mock?: boolean;
  error?: string;
}

export interface GSTRegistration {
  id: string;
  company: string;
  gstin: string;
  state_code: string;
  state_name?: string;
  legal_name: string;
  trade_name: string;
  address: string;
  pincode: string;
  taxpayer_type: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'CANCELLED' | 'INACTIVE';
  verification_status: 'NOT_VERIFIED' | 'PENDING' | 'VERIFIED' | 'INVALID' | 'INACTIVE' | 'FAILED' | 'PROVIDER_UNAVAILABLE' | 'EXPIRED';
  last_verified_at?: string;
  provider_reference_id?: string;
  is_primary: boolean;
  has_portal_auth?: boolean;
  has_einvoice_auth?: boolean;
  has_eway_auth?: boolean;
  created_at: string;
  updated_at: string;
}

export interface EWayBillData {
  id?: string;
  eway_bill_number: string;
  ewb_number?: string;
  ewb_date?: string;
  valid_upto: string;
  valid_until?: string;
  status: string;
  status_display?: string;
  eway_bill_date?: string;
  vehicle_no?: string;
  vehicle_number?: string;
  vehicle_type?: string;
  distance_km?: number;
  trans_mode?: string;
  transport_mode?: string;
  trans_mode_display?: string;
  transporter_id?: string;
  transporter_name?: string;
  trans_doc_no?: string;
  cancelled_at?: string;
}

export type EWayBillDetails = EWayBillData;

export interface EInvoiceData {
  id: string;
  irn: string;
  ack_number: string;
  ack_date: string;
  signed_qr_code?: string;
  status: 'GENERATED' | 'CANCELLED' | 'FAILED';
  cancel_reason?: string;
  cancel_remarks?: string;
  cancelled_at?: string;
}

export interface GSTR2BMismatchDetails {
  category: string;
  confidence_score?: number;
  confidence_level?: 'EXACT_MATCH' | 'HIGH_CONFIDENCE' | 'AMBIGUOUS' | 'MISMATCH' | 'NO_MATCH';
  statutory_itc_eligibility?: 'ELIGIBLE' | 'INELIGIBLE' | 'REVIEW_REQUIRED' | 'BLOCKED_SEC17_5' | 'REVERSAL_REQUIRED';
  statutory_reason?: string;
  explanation?: string;
  days_difference?: number;
  book_voucher_number?: string | null;
  book_date?: string | null;
  book_total?: number | null;
  gstr2b_total?: number;
  taxable_diff?: number;
  tax_diff?: number;
}

export interface GSTR2BRecordItem {
  id: string;
  supplier_gstin: string;
  supplier_trade_name: string;
  invoice_number: string;
  invoice_date: string;
  invoice_value: string;
  taxable_value: string;
  igst_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  cess_amount: string;
  itc_availability: string;
  match_category: string;
  is_reconciled: boolean;
  review_status: string;
  mismatch_explanation: string;
  review_notes?: string;
}

export interface GSTAuditLogItem {
  id: string;
  action: string;
  gstin: string;
  status: 'SUCCESS' | 'FAILURE' | 'PENDING';
  error_message?: string;
  created_at: string;
}

export interface GSTPayloadValidationIssue {
  error_code: string;
  severity: 'ERROR' | 'WARNING' | 'INFORMATION';
  section: string;
  record_identifier: string;
  description: string;
  recommended_correction: string;
}

export interface GSTPayloadValidationResult {
  is_valid: boolean;
  blocking_errors_count: number;
  warnings_count: number;
  conformance_standard: string;
  validated_at: string;
  issues: GSTPayloadValidationIssue[];
}

export interface OfficialGSTR1Payload {
  gstin: string;
  fp: string;
  version?: string;
  cur_gt?: number;
  gt?: number;
  b2b?: Array<{
    ctin: string;
    inv: Array<{
      inum: string;
      idt: string;
      val: number;
      pos: string;
      rchrg: string;
      inv_typ: string;
      itms: Array<{
        num: number;
        itm_det: {
          rt: number;
          txval: number;
          iamt: number;
          camt: number;
          samt: number;
          csamt: number;
        };
      }>;
    }>;
  }>;
  b2cl?: Array<{
    pos: string;
    inv: Array<{
      inum: string;
      idt: string;
      val: number;
      inv_typ: string;
      itms: Array<{
        num: number;
        itm_det: {
          rt: number;
          txval: number;
          iamt: number;
          csamt: number;
        };
      }>;
    }>;
  }>;
  b2cs?: Array<{
    sply_ty: string;
    pos: string;
    typ?: string;
    rt: number;
    txval: number;
    iamt: number;
    camt: number;
    samt: number;
    csamt: number;
  }>;
  cdnr?: any[];
  cdnur?: any[];
  exp?: any[];
  nil?: {
    inv: Array<{
      nil_amt: number;
      expt_amt: number;
      ngsup_amt: number;
    }>;
  };
  hsn?: {
    data: Array<{
      num: number;
      hsn_sc: string;
      desc?: string;
      uqc?: string;
      qty?: number;
      val?: number;
      txval: number;
      iamt: number;
      camt: number;
      samt: number;
      csamt: number;
    }>;
  };
  doc_issue?: {
    doc_det: Array<{
      doc_num: number;
      doc_typ: string;
      from: string;
      to: string;
      totnum: number;
      canc: number;
      net_issue: number;
    }>;
  };
}

export interface OfficialGSTR3BPayload {
  gstin: string;
  ret_period: string;
  filing_typ: 'GSTR3B';
  version?: string;
  sup_details: {
    osup_det: { txval: number; iamt: number; camt: number; samt: number; csamt: number };
    osup_zero: { txval: number; iamt: number; csamt: number };
    osup_nil_exmp: { txval: number };
    isup_rev: { txval: number; iamt: number; camt: number; samt: number; csamt: number };
    osup_nongst: { txval: number };
  };
  inter_sup: {
    unreg_details: Array<{ pos: string; txval: number; iamt: number }>;
    comp_details: any[];
    uin_details: any[];
  };
  itc_elg: {
    itc_avl: {
      import_goods: { iamt: number; csamt: number };
      import_services: { iamt: number; csamt: number };
      isup_rev: { iamt: number; camt: number; samt: number; csamt: number };
      isd: { iamt: number; camt: number; samt: number; csamt: number };
      all_other: { txval?: number; iamt: number; camt: number; samt: number; csamt: number };
    };
    itc_rev: {
      rule42_43: { iamt: number; camt: number; samt: number; csamt: number };
      others: { iamt: number; camt: number; samt: number; csamt: number };
    };
    itc_net: { iamt: number; camt: number; samt: number; csamt: number };
    itc_inelg: {
      as_per_sec_17_5: { iamt: number; camt: number; samt: number; csamt: number };
      others: { iamt: number; camt: number; samt: number; csamt: number };
    };
  };
  inward_sup: {
    isup_details: Array<{ ty: string; inter: number; intra: number }>;
  };
}

export interface GSTExportResult {
  success: boolean;
  return_type: string;
  return_period: string;
  format: 'JSON' | 'REVIEW_REPORT' | 'RECON_REPORT';
  conformance_standard?: string;
  portal_uploadable?: boolean;
  export_classification?: string;
  portal_compatibility_notice?: string;
  payload_hash?: string;
  validation_summary?: GSTPayloadValidationResult;
  payload?: OfficialGSTR1Payload | OfficialGSTR3BPayload | any;
  exported_at?: string;
  error?: string;
  drift_detected?: boolean;
}

export const gstApi = {
  /**
   * Unified GSTIN Verification against Sandbox / Cache with Luhn check and enrichment preview
   */
  async verifyGSTIN(gstin: string, partyId?: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/verify-gstin/`;
    const res = await axios.post(url, { gstin, party_id: partyId, company_id: companyId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Applies verified taxpayer data to an existing party ledger record
   */
  async applyPartyEnrichment(payload: {
    party_id: string;
    apply_legal_name?: boolean;
    apply_trade_name?: boolean;
    apply_state?: boolean;
    apply_address?: boolean;
    verified_data?: any;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/party/enrich/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * List GST Registrations (multi-state/multi-GSTIN)
   */
  async getRegistrations(companyId: string): Promise<GSTRegistration[]> {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data?.registrations || res.data?.data || res.data || [];
  },

  /**
   * Pre-check / Preview GSTIN details before creating a registration
   */
  async verifyRegistrationPreview(companyId: string, gstin: string) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/verify-preview/`;
    const res = await axios.post(url, { gstin }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Create a new GST Registration
   */
  async createRegistration(companyId: string, data: Partial<GSTRegistration> & { auto_verify?: boolean }) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/`;
    const res = await axios.post(url, data, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Re-verify an existing GST Registration against Sandbox
   */
  async verifyRegistration(companyId: string, registrationId: string, forceRefresh: boolean = true) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/${registrationId}/verify/`;
    const res = await axios.post(url, { force_refresh: forceRefresh }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Update metadata on an existing GST Registration
   */
  async updateRegistration(companyId: string, registrationId: string, data: Partial<GSTRegistration>) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/${registrationId}/`;
    const res = await axios.put(url, data, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Mark a GST Registration as INACTIVE
   */
  async deactivateRegistration(companyId: string, registrationId: string) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/${registrationId}/deactivate/`;
    const res = await axios.post(url, {}, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Reactivate an inactive GST Registration
   */
  async reactivateRegistration(companyId: string, registrationId: string) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/${companyId}/${registrationId}/reactivate/`;
    const res = await axios.post(url, {}, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * GST Workspace Overview
   */
  async getOverview(registrationId?: string, companyId?: string) {
    const params = registrationId ? `?registration_id=${registrationId}` : '';
    const url = `${API_BASE_URL}/api/v1/gst/overview/${params}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * GSTR-1 Workspace data
   */
  async getGSTR1Workspace(period?: string, registrationId?: string, companyId?: string) {
    const query = new URLSearchParams();
    if (period) query.set('period', period);
    if (registrationId) query.set('registration_id', registrationId);
    const url = `${API_BASE_URL}/api/v1/gst/returns/gstr1/workspace/?${query.toString()}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Submit GSTR-1 return to Sandbox
   */
  async submitGSTR1(payload: {
    period: string;
    registration_id?: string;
    tables: Record<string, any>;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/returns/gstr1/submit/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * GSTR-3B Workspace summary
   */
  async getGSTR3BWorkspace(period?: string, registrationId?: string, companyId?: string) {
    const query = new URLSearchParams();
    if (period) query.set('period', period);
    if (registrationId) query.set('registration_id', registrationId);
    const url = `${API_BASE_URL}/api/v1/gst/returns/gstr3b/workspace/?${query.toString()}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * GSTR-2B Reconciliation list with 11 categories filter
   */
  async getGSTR2BReconciliation(params?: {
    registration_id?: string;
    return_period?: string;
    match_category?: string;
    search?: string;
  }, companyId?: string) {
    const query = new URLSearchParams(params as Record<string, string>);
    const url = `${API_BASE_URL}/api/v1/gst/reconciliation/gstr2b/?${query.toString()}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Sync GSTR-2B directly from Sandbox
   */
  async syncGSTR2BFromSandbox(payload: {
    year: string | number;
    month: string | number;
    registration_id?: string;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reconciliation/gstr2b/sync/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Review a GSTR-2B record (ACCEPT, REJECT, DISPUTE)
   */
  async reviewGSTR2BRecord(recordId: string, action: string, notes?: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reconciliation/gstr2b/records/${recordId}/review/`;
    const res = await axios.post(url, { action, notes }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Generate IRN (e-Invoice)
   */
  async generateEInvoice(voucherId: string, registrationId?: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/einvoice/generate/`;
    const res = await axios.post(url, { voucher_id: voucherId, registration_id: registrationId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Cancel e-Invoice (within statutory 24 hours)
   */
  async cancelEInvoice(irn: string, reason: string, remarks?: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/einvoice/cancel/`;
    const res = await axios.post(url, { irn, reason, remarks }, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Get e-Invoice details for a voucher
   */
  async getEInvoiceDetail(voucherId: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/einvoice/${voucherId}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Generate E-Way Bill V2
   */
  async generateEWayBillV2(payload: {
    voucher_id: string;
    trans_mode?: string;
    distance_km: number;
    vehicle_number?: string;
    vehicle_type?: string;
    transporter_id?: string;
    transporter_name?: string;
    registration_id?: string;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/ewaybill/generate/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Update E-Way Bill Vehicle Part-B V2
   */
  async updateVehicleV2(payload: {
    ewb_number: string;
    vehicle_number: string;
    reason?: string;
    remarks?: string;
    from_place?: string;
    from_state_code?: number;
    registration_id?: string;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/ewaybill/vehicle-update/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Cancel E-Way Bill V2
   */
  async cancelEWayBillV2(payload: {
    ewb_number: string;
    cancel_reason: string;
    cancel_remarks?: string;
    registration_id?: string;
  }, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/ewaybill/cancel/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Fetch GST compliance audit logs
   */
  async getAuditLogs(params?: { gstin?: string; action?: string }, companyId?: string) {
    const query = new URLSearchParams(params as Record<string, string>);
    const url = `${API_BASE_URL}/api/v1/gst/audit-logs/?${query.toString()}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Legacy lookup compatibility
   */
  async lookupGSTIN(gstin: string, companyId?: string): Promise<GSTTaxpayerDetails> {
    const clean = gstin.trim().toUpperCase();
    const url = `${API_BASE_URL}/api/v1/gst/lookup/${clean}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async getCompanyGSTConfig(companyId: string) {
    const url = `${API_BASE_URL}/api/v1/gst/config/${companyId}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async updateCompanyGSTConfig(companyId: string, data: any) {
    const url = `${API_BASE_URL}/api/v1/gst/config/${companyId}/`;
    const res = await axios.post(url, data, { headers: getHeaders(companyId) });
    return res.data;
  },

  async generateEWayBill(payload: any) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/generate/`;
    const res = await axios.post(url, payload, { headers: getHeaders() });
    return res.data;
  },

  async updateVehicle(payload: any) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/update-vehicle/`;
    const res = await axios.post(url, payload, { headers: getHeaders() });
    return res.data;
  },

  async cancelEWayBill(payload: any) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/cancel/`;
    const res = await axios.post(url, payload, { headers: getHeaders() });
    return res.data;
  },

  async getVoucherEWayBills(voucherId: string): Promise<EWayBillData[]> {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/voucher/${voucherId}/`;
    const res = await axios.get(url, { headers: getHeaders() });
    return (res.data.eway_bills || []).map((e: any) => ({
      ...e,
      eway_bill_number: e.ewb_number || e.eway_bill_number,
      valid_upto: e.valid_until || e.valid_upto,
      vehicle_no: e.vehicle_number || e.vehicle_no,
    }));
  },

  async getEWayBillForVoucher(voucherId: string): Promise<{ success: boolean; data?: EWayBillData | null; eway_bills?: EWayBillData[]; error?: string }> {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/voucher/${voucherId}/`;
    const res = await axios.get(url, { headers: getHeaders() });
    const list = (res.data.eway_bills || []).map((e: any) => ({
      ...e,
      eway_bill_number: e.ewb_number || e.eway_bill_number,
      valid_upto: e.valid_until || e.valid_upto,
      vehicle_no: e.vehicle_number || e.vehicle_no,
    }));
    return {
      success: res.data.success !== false,
      data: list[0] || null,
      eway_bills: list,
    };
  },

  async getGSTR1Report(companyId: string, startDate: string, endDate: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reports/gstr1/${companyId}/?start_date=${startDate}&end_date=${endDate}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async getGSTR3BSummary(companyId: string, startDate: string, endDate: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reports/gstr3b/${companyId}/?start_date=${startDate}&end_date=${endDate}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  // Round 2.0 GST Return Workspace & Reconciliation APIs
  async getWorkspace(companyId: string, period: string, returnType: string = 'GSTR1', regId?: string) {
    let url = `${API_BASE_URL}/api/v1/gst/workspace/${companyId}/?period=${period}&return_type=${returnType}`;
    if (regId) url += `&registration_id=${regId}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async generateWorkspaceDraft(companyId: string, period: string, returnType: string = 'GSTR1', regId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/workspace/${companyId}/generate-draft/`;
    const res = await axios.post(url, { period, return_type: returnType, registration_id: regId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  async validateWorkspace(companyId: string, period: string, returnType: string = 'GSTR1', regId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/workspace/${companyId}/validate/`;
    const res = await axios.post(url, { period, return_type: returnType, registration_id: regId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  async signOffWorkspace(companyId: string, period: string, returnType: string = 'GSTR1', regId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/workspace/${companyId}/sign-off/`;
    const res = await axios.post(url, { period, return_type: returnType, registration_id: regId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  async exportWorkspace(companyId: string, period: string, returnType: string = 'GSTR1', format: string = 'JSON', regId?: string): Promise<GSTExportResult> {
    const url = `${API_BASE_URL}/api/v1/gst/workspace/${companyId}/export/`;
    const res = await axios.post(url, { period, return_type: returnType, format, registration_id: regId }, { headers: getHeaders(companyId) });
    return res.data;
  },

  async uploadGSTR2B(companyId: string, file: File, period?: string, regId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reconciliation/${companyId}/upload-2b/`;
    const formData = new FormData();
    formData.append('file', file);
    if (period) formData.append('period', period);
    if (regId) formData.append('registration_id', regId);
    const headers = getHeaders(companyId);
    const res = await axios.post(url, formData, { headers });
    return res.data;
  },

  async getReconciliationSummary(companyId: string, period?: string, regId?: string) {
    let url = `${API_BASE_URL}/api/v1/gst/reconciliation/${companyId}/summary/`;
    const params = [];
    if (period) params.push(`period=${period}`);
    if (regId) params.push(`registration_id=${regId}`);
    if (params.length > 0) url += `?${params.join('&')}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async getReconciliationRecords(companyId: string, period?: string, matchStatus?: string) {
    let url = `${API_BASE_URL}/api/v1/gst/reconciliation/${companyId}/records/`;
    const params = [];
    if (period) params.push(`period=${period}`);
    if (matchStatus) params.push(`match_status=${matchStatus}`);
    if (params.length > 0) url += `?${params.join('&')}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  async manualMatchRecord(companyId: string, recordId: string, voucherId: string, notes?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reconciliation/${companyId}/manual-match/`;
    const res = await axios.post(url, { record_id: recordId, voucher_id: voucherId, notes }, { headers: getHeaders(companyId) });
    return res.data;
  }
};
