import axios from 'axios';
import { API_BASE_URL } from '@/utils/api';
import { getAccessToken } from '@/utils/auth';

function getHeaders(companyId?: string) {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
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

export const gstApi = {
  /**
   * Looks up taxpayer details by GSTIN from the GST portal (or local cache).
   */
  async lookupGSTIN(gstin: string, companyId?: string): Promise<GSTTaxpayerDetails> {
    const clean = gstin.trim().toUpperCase();
    const url = `${API_BASE_URL}/api/v1/gst/lookup/${clean}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Retrieves company GST configuration.
   */
  async getCompanyGSTConfig(companyId: string) {
    const url = `${API_BASE_URL}/api/v1/gst/config/${companyId}/`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Updates company GST configuration.
   */
  async updateCompanyGSTConfig(companyId: string, data: any) {
    const url = `${API_BASE_URL}/api/v1/gst/config/${companyId}/`;
    const res = await axios.post(url, data, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Generates a new E-Way Bill for a voucher.
   */
  async generateEWayBill(payload: {
    voucher_id: string;
    transport_mode?: string;
    trans_mode?: string;
    distance_km: number;
    vehicle_number?: string;
    vehicle_no?: string;
    vehicle_type?: string;
    transporter_id?: string;
    transporter_name?: string;
    transporter_doc_no?: string;
    trans_doc_no?: string;
    transporter_doc_date?: string;
    sub_supply_type?: string;
  }) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/generate/`;
    const formatted = {
      voucher_id: payload.voucher_id,
      transport_mode: payload.transport_mode || payload.trans_mode || '1',
      distance_km: payload.distance_km,
      vehicle_number: payload.vehicle_number || payload.vehicle_no || '',
      vehicle_type: payload.vehicle_type || 'R',
      transporter_id: payload.transporter_id,
      transporter_name: payload.transporter_name,
      transporter_doc_no: payload.transporter_doc_no || payload.trans_doc_no,
      transporter_doc_date: payload.transporter_doc_date,
    };
    const res = await axios.post(url, formatted, { headers: getHeaders() });
    if (res.data?.data) {
      res.data.data.eway_bill_number = res.data.data.ewb_number || res.data.data.eway_bill_number;
      res.data.data.valid_upto = res.data.data.valid_until || res.data.data.valid_upto;
      res.data.data.vehicle_no = res.data.data.vehicle_number || res.data.data.vehicle_no;
    }
    return res.data;
  },

  /**
   * Updates Part-B vehicle number for an active E-Way bill.
   */
  async updateVehicle(payload: {
    ewb_number?: string;
    eway_bill_number?: string;
    vehicle_number?: string;
    vehicle_no?: string;
    from_place?: string;
    from_state?: string;
    reason?: string;
    reason_code?: string;
    remarks?: string;
    reason_remarks?: string;
    trans_doc_no?: string;
  }) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/update-vehicle/`;
    const formatted = {
      ewb_number: payload.ewb_number || payload.eway_bill_number || '',
      vehicle_number: payload.vehicle_number || payload.vehicle_no || '',
      reason: payload.reason || payload.reason_remarks || payload.reason_code || 'Breakdown',
      remarks: payload.remarks || payload.reason_remarks || '',
    };
    const res = await axios.post(url, formatted, { headers: getHeaders() });
    if (res.data?.data) {
      res.data.data.eway_bill_number = res.data.data.ewb_number || res.data.data.eway_bill_number;
      res.data.data.valid_upto = res.data.data.valid_until || res.data.data.valid_upto;
      res.data.data.vehicle_no = res.data.data.vehicle_number || res.data.data.vehicle_no;
    }
    return res.data;
  },

  /**
   * Cancels an active E-Way bill.
   */
  async cancelEWayBill(payload: {
    ewb_number?: string;
    eway_bill_number?: string;
    reason?: string;
    cancel_reason_code?: string;
    remarks?: string;
    cancel_remarks?: string;
  }) {
    const url = `${API_BASE_URL}/api/v1/gst/eway-bill/cancel/`;
    const formatted = {
      ewb_number: payload.ewb_number || payload.eway_bill_number || '',
      reason: payload.reason || payload.cancel_reason_code || '1',
      remarks: payload.remarks || payload.cancel_remarks || 'Cancelled by user',
    };
    const res = await axios.post(url, formatted, { headers: getHeaders() });
    if (res.data?.data) {
      res.data.data.eway_bill_number = res.data.data.ewb_number || res.data.data.eway_bill_number;
      res.data.data.valid_upto = res.data.data.valid_until || res.data.data.valid_upto;
      res.data.data.vehicle_no = res.data.data.vehicle_number || res.data.data.vehicle_no;
    }
    return res.data;
  },

  /**
   * Fetches E-Way bills generated for a voucher.
   */
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

  /**
   * Fetches primary E-Way bill for a voucher.
   */
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

  /**
   * Fetches GSTR-1 payload JSON or downloads it.
   */
  async getGSTR1Report(companyId: string, startDate: string, endDate: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reports/gstr1/${companyId}/?start_date=${startDate}&end_date=${endDate}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  },

  /**
   * Fetches GSTR-3B tax liability vs eligible ITC summary.
   */
  async getGSTR3BSummary(companyId: string, startDate: string, endDate: string) {
    const url = `${API_BASE_URL}/api/v1/gst/reports/gstr3b/${companyId}/?start_date=${startDate}&end_date=${endDate}`;
    const res = await axios.get(url, { headers: getHeaders(companyId) });
    return res.data;
  }
};
