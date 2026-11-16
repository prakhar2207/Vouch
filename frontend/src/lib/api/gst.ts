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
  legal_name: string;
  trade_name: string;
  address: string;
  pincode: string;
  taxpayer_type: string;
  is_primary: boolean;
  is_active: boolean;
  has_auth_token: boolean;
  has_einvoice_credentials: boolean;
  has_eway_credentials: boolean;
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

export const gstApi = {
  /**
   * Unified GSTIN Verification against Sandbox / Cache with Luhn check and enrichment preview
   */
  async verifyGSTIN(gstin: string, partyId?: string, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/gstin/verify/`;
    const res = await axios.post(url, { gstin, party_id: partyId }, { headers: getHeaders(companyId) });
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
    const url = `${API_BASE_URL}/api/v1/gst/parties/enrich/`;
    const res = await axios.post(url, payload, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * List GST Registrations (multi-state/multi-GSTIN)
   */
  async getRegistrations(companyId?: string): Promise<GSTRegistration[]> {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data?.data || res.data || [];
  },

  /**
   * Create a new GST Registration
   */
  async createRegistration(data: Partial<GSTRegistration>, companyId?: string) {
    const url = `${API_BASE_URL}/api/v1/gst/registrations/`;
    const res = await axios.post(url, data, { headers: getHeaders(companyId) });
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
  }
};
