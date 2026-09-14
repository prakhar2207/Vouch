"use client";
import React, { useState, useEffect } from 'react';
import { 
  X, 
  Truck, 
  ShieldCheck, 
  AlertTriangle, 
  Loader2, 
  CheckCircle2, 
  Copy, 
  RotateCcw,
  Ban
} from 'lucide-react';
import { gstApi, EWayBillData } from '@/lib/api/gst';
import { useToast } from '@/context/ToastContext';

interface EWayBillModalProps {
  isOpen: boolean;
  onClose: () => void;
  voucher: any;
  companyId?: string;
  onSuccess?: () => void;
}

export default function EWayBillModal({
  isOpen,
  onClose,
  voucher,
  companyId,
  onSuccess,
}: EWayBillModalProps) {
  const { toast } = useToast();
  
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [ewayRecord, setEwayRecord] = useState<EWayBillData | null>(null);
  const [activeTab, setActiveTab] = useState<'VIEW' | 'GENERATE' | 'UPDATE_VEHICLE' | 'CANCEL'>('VIEW');

  // Generation form state
  const [distanceKm, setDistanceKm] = useState('100');
  const [transMode, setTransMode] = useState<'1' | '2' | '3' | '4'>('1');
  const [vehicleNo, setVehicleNo] = useState('');
  const [vehicleType, setVehicleType] = useState<'R' | 'O'>('R');
  const [transporterId, setTransporterId] = useState('');
  const [transporterName, setTransporterName] = useState('');
  const [transDocNo, setTransDocNo] = useState('');
  const [subType, setSubType] = useState('1');

  // Update vehicle form state
  const [updVehicleNo, setUpdVehicleNo] = useState('');
  const [fromPlace, setFromPlace] = useState('');
  const [fromState, setFromState] = useState('');
  const [updReasonCode, setUpdReasonCode] = useState('1');
  const [updRemarks, setUpdRemarks] = useState('');

  // Cancel form state
  const [cancelReasonCode, setCancelReasonCode] = useState('1');
  const [cancelRemarks, setCancelRemarks] = useState('');

  useEffect(() => {
    if (isOpen && voucher?.id) {
      loadEWayBill();
    } else {
      setEwayRecord(null);
      setActiveTab('VIEW');
    }
  }, [isOpen, voucher?.id]);

  const loadEWayBill = async () => {
    if (!voucher?.id) return;
    setLoading(true);
    try {
      const res = await gstApi.getEWayBillForVoucher(voucher.id);
      if (res.success && res.data) {
        setEwayRecord(res.data);
        setActiveTab('VIEW');
      } else {
        setEwayRecord(null);
        setActiveTab('GENERATE');
      }
    } catch (err) {
      console.error(err);
      setEwayRecord(null);
      setActiveTab('GENERATE');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !voucher) return null;

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard', `${label}: ${text}`);
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    const dist = parseInt(distanceKm, 10);
    if (!dist || dist <= 0) {
      toast.warning('Invalid distance', 'Distance must be at least 1 km');
      return;
    }

    if (transMode === '1' && !vehicleNo.trim() && !transporterId.trim()) {
      toast.warning('Vehicle or Transporter ID required', 'Enter vehicle number or Transporter ID for Road transport');
      return;
    }

    setActionLoading(true);
    try {
      const payload = {
        voucher_id: voucher.id,
        distance_km: dist,
        trans_mode: transMode,
        vehicle_no: vehicleNo.trim().toUpperCase(),
        vehicle_type: vehicleType,
        transporter_id: transporterId.trim().toUpperCase(),
        transporter_name: transporterName.trim(),
        trans_doc_no: transDocNo.trim(),
        sub_supply_type: subType,
      };

      const res = await gstApi.generateEWayBill(payload);
      if (res.success && res.data) {
        setEwayRecord(res.data);
        setActiveTab('VIEW');
        toast.success(
          'E-Way Bill Generated!',
          `EWB No: ${res.data.eway_bill_number}${res.data.valid_upto ? ` • Valid till ${new Date(res.data.valid_upto).toLocaleDateString()}` : ''}`
        );
        if (onSuccess) onSuccess();
      } else {
        toast.error('Generation Failed', res.error || 'Failed to generate E-Way Bill');
      }
    } catch (err: any) {
      toast.error('Generation Error', err.response?.data?.error || err.message || 'Error occurred');
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ewayRecord) return;
    if (!updVehicleNo.trim()) {
      toast.warning('Vehicle Number Required', 'Enter a valid new vehicle registration number');
      return;
    }

    setActionLoading(true);
    try {
      const res = await gstApi.updateVehicle({
        eway_bill_number: ewayRecord.eway_bill_number,
        vehicle_no: updVehicleNo.trim().toUpperCase(),
        from_place: fromPlace.trim() || 'Warehouse',
        from_state: fromState || voucher.company?.state_code || '09',
        reason_code: updReasonCode,
        reason_remarks: updRemarks.trim() || 'Vehicle changed in transit',
        trans_doc_no: transDocNo.trim(),
      });

      if (res.success && res.data) {
        setEwayRecord(res.data);
        setActiveTab('VIEW');
        setUpdVehicleNo('');
        setUpdRemarks('');
        toast.success('Vehicle Updated Successfully', `New vehicle ${res.data.vehicle_no} assigned to Part-B.`);
        if (onSuccess) onSuccess();
      } else {
        toast.error('Vehicle Update Failed', res.error || 'Could not update vehicle on portal');
      }
    } catch (err: any) {
      toast.error('Vehicle Update Error', err.response?.data?.error || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelEwayBill = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ewayRecord) return;

    if (!confirm(`Are you sure you want to cancel E-Way Bill #${ewayRecord.eway_bill_number}? This cannot be undone.`)) {
      return;
    }

    setActionLoading(true);
    try {
      const res = await gstApi.cancelEWayBill({
        eway_bill_number: ewayRecord.eway_bill_number,
        cancel_reason_code: cancelReasonCode,
        cancel_remarks: cancelRemarks.trim() || 'Cancelled as per customer request',
      });

      if (res.success && res.data) {
        setEwayRecord(res.data);
        setActiveTab('VIEW');
        toast.success('E-Way Bill Cancelled', `EWB #${res.data.eway_bill_number} has been cancelled.`);
        if (onSuccess) onSuccess();
      } else {
        toast.error('Cancellation Failed', res.error || 'Could not cancel E-Way bill');
      }
    } catch (err: any) {
      toast.error('Cancellation Error', err.response?.data?.error || err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const isCancelled = ewayRecord?.status === 'CAN';
  const isValid = ewayRecord && !isCancelled;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="w-full max-w-2xl bg-card border border-border/40 rounded-2xl shadow-2xl overflow-hidden flex flex-col my-8 animate-in fade-in zoom-in-95">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/40 bg-muted/20">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 text-primary rounded-xl">
              <Truck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-foreground">
                GST E-Way Bill Management
              </h3>
              <p className="text-xs text-muted-foreground">
                Invoice <span className="font-mono font-semibold text-foreground">{voucher.voucher_number}</span> • ₹{Number(voucher.total_amount || 0).toLocaleString('en-IN')}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6 max-h-[78vh] overflow-y-auto">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground font-mono">Querying GST Portal / E-Way Bill System...</p>
            </div>
          ) : (
            <>
              {/* If E-Way Bill exists and we are in VIEW mode */}
              {activeTab === 'VIEW' && ewayRecord && (
                <div className="space-y-6">
                  {/* Status Banner */}
                  <div className={`p-4 rounded-xl border flex items-center justify-between gap-4 ${
                    isCancelled 
                      ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' 
                      : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  }`}>
                    <div className="flex items-center gap-3">
                      {isCancelled ? (
                        <Ban className="w-6 h-6 text-rose-500 shrink-0" />
                      ) : (
                        <ShieldCheck className="w-6 h-6 text-emerald-500 shrink-0" />
                      )}
                      <div>
                        <div className="text-xs uppercase tracking-wider font-bold">
                          {isCancelled ? 'E-Way Bill Cancelled' : 'Official NIC E-Way Bill Active'}
                        </div>
                        <div className="text-base font-bold font-mono text-foreground flex items-center gap-2 mt-0.5">
                          <span>{ewayRecord.eway_bill_number}</span>
                          <button
                            type="button"
                            onClick={() => handleCopy(ewayRecord.eway_bill_number, 'E-Way Bill Number')}
                            className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
                            title="Copy E-Way Bill No."
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold font-mono border ${
                        isCancelled
                          ? 'bg-rose-500/20 text-rose-400 border-rose-500/30'
                          : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                      }`}>
                        {ewayRecord.status_display || ewayRecord.status}
                      </span>
                      <div className="text-[11px] text-muted-foreground mt-1">
                        Gen: {ewayRecord.eway_bill_date || ewayRecord.ewb_date ? new Date(ewayRecord.eway_bill_date || ewayRecord.ewb_date || '').toLocaleDateString('en-IN') : 'N/A'}
                      </div>
                    </div>
                  </div>

                  {/* Details Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3.5 p-4 rounded-xl bg-muted/30 border border-border/40 text-xs">
                    <div>
                      <div className="text-muted-foreground">Valid Upto</div>
                      <div className="font-semibold text-foreground font-mono mt-0.5">
                        {ewayRecord.valid_upto || ewayRecord.valid_until ? new Date(ewayRecord.valid_upto || ewayRecord.valid_until || '').toLocaleDateString('en-IN') : 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Distance</div>
                      <div className="font-semibold text-foreground font-mono mt-0.5">
                        {ewayRecord.distance_km} KM
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Transport Mode</div>
                      <div className="font-semibold text-foreground mt-0.5">
                        {ewayRecord.trans_mode_display || 'Road'}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Vehicle Number (Part-B)</div>
                      <div className="font-bold text-foreground font-mono mt-0.5 text-sm">
                        {ewayRecord.vehicle_no || 'Pending Part-B'}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Vehicle Type</div>
                      <div className="font-semibold text-foreground mt-0.5">
                        {ewayRecord.vehicle_type === 'O' ? 'Over Dimensional' : 'Regular'}
                      </div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Transporter ID</div>
                      <div className="font-mono text-foreground mt-0.5">
                        {ewayRecord.transporter_id || 'Self / Unassigned'}
                      </div>
                    </div>
                  </div>

                  {/* Consignor / Consignee Summary */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="p-3 bg-card border border-border/40 rounded-xl space-y-1">
                      <div className="font-bold text-muted-foreground uppercase text-[10px]">Dispatch From (Supplier)</div>
                      <div className="font-semibold text-foreground">{voucher.company?.name || 'Your Company'}</div>
                      <div className="text-muted-foreground font-mono">GSTIN: {voucher.company?.gstin || 'N/A'}</div>
                      <div className="text-muted-foreground">{voucher.company?.address || 'Registered Location'}</div>
                    </div>
                    <div className="p-3 bg-card border border-border/40 rounded-xl space-y-1">
                      <div className="font-bold text-muted-foreground uppercase text-[10px]">Ship To (Recipient)</div>
                      <div className="font-semibold text-foreground">{voucher.party?.name || 'Customer'}</div>
                      <div className="text-muted-foreground font-mono">GSTIN: {voucher.party?.gstin || 'Unregistered'}</div>
                      <div className="text-muted-foreground">{voucher.party?.address || 'Customer Address'}</div>
                    </div>
                  </div>

                  {/* Action Buttons for Active E-Way Bill */}
                  {isValid && (
                    <div className="flex items-center justify-end gap-3 pt-2 border-t border-border/40">
                      <button
                        type="button"
                        onClick={() => setActiveTab('CANCEL')}
                        className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer"
                      >
                        <Ban className="w-3.5 h-3.5" />
                        Cancel E-Way Bill
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setUpdVehicleNo(ewayRecord.vehicle_no || '');
                          setActiveTab('UPDATE_VEHICLE');
                        }}
                        className="px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        Update Vehicle (Part-B)
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* GENERATE FORM */}
              {activeTab === 'GENERATE' && (
                <form onSubmit={handleGenerate} className="space-y-4">
                  <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 rounded-xl text-xs text-blue-400 flex items-start gap-2.5">
                    <Truck className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold">E-Way Bill Required for Goods Movement:</span> Enter transportation details to electronically register dispatch with GST Portal / NIC.
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Approx Distance (KM) <span className="text-primary">*</span>
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="4000"
                        required
                        value={distanceKm}
                        onChange={(e) => setDistanceKm(e.target.value)}
                        placeholder="e.g. 120"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm font-mono outline-none focus:ring-2 focus:ring-primary"
                      />
                      <p className="text-[10px] text-muted-foreground mt-1">Determines validity period (100 km/day)</p>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Transportation Mode <span className="text-primary">*</span>
                      </label>
                      <select
                        value={transMode}
                        onChange={(e: any) => setTransMode(e.target.value)}
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      >
                        <option value="1">1 - Road</option>
                        <option value="2">2 - Rail</option>
                        <option value="3">3 - Air</option>
                        <option value="4">4 - Ship</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Vehicle Number (Part-B)
                      </label>
                      <input
                        type="text"
                        value={vehicleNo}
                        onChange={(e) => setVehicleNo(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                        placeholder="e.g. DL01AB1234"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm font-mono uppercase outline-none focus:ring-2 focus:ring-primary"
                      />
                      <p className="text-[10px] text-muted-foreground mt-1">Format: State (2) + District (2) + Letters + Digits</p>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Vehicle Type
                      </label>
                      <select
                        value={vehicleType}
                        onChange={(e: any) => setVehicleType(e.target.value)}
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      >
                        <option value="R">Regular Goods Vehicle</option>
                        <option value="O">Over Dimensional Cargo (ODC)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Transporter ID / TRANSIN (Optional)
                      </label>
                      <input
                        type="text"
                        maxLength={15}
                        value={transporterId}
                        onChange={(e) => setTransporterId(e.target.value.toUpperCase())}
                        placeholder="15-digit GSTIN/TRANSIN"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm font-mono uppercase outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Transporter Doc No / LR No (Optional)
                      </label>
                      <input
                        type="text"
                        value={transDocNo}
                        onChange={(e) => setTransDocNo(e.target.value)}
                        placeholder="e.g. LR-98214"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-border/40">
                    {ewayRecord && (
                      <button
                        type="button"
                        onClick={() => setActiveTab('VIEW')}
                        className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="px-5 py-2.5 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground shadow-md transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      {actionLoading ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Generating on Portal...</span>
                        </>
                      ) : (
                        <>
                          <Truck className="w-4 h-4" />
                          <span>Generate 12-Digit E-Way Bill</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* UPDATE VEHICLE FORM */}
              {activeTab === 'UPDATE_VEHICLE' && ewayRecord && (
                <form onSubmit={handleUpdateVehicle} className="space-y-4">
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-400">
                    <span className="font-bold">Part-B Updation:</span> Update vehicle details when cargo is transshipped or vehicle changes during movement.
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        New Vehicle Number <span className="text-primary">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={updVehicleNo}
                        onChange={(e) => setUpdVehicleNo(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                        placeholder="e.g. MH04CD5678"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm font-mono uppercase outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Place of Change
                      </label>
                      <input
                        type="text"
                        value={fromPlace}
                        onChange={(e) => setFromPlace(e.target.value)}
                        placeholder="e.g. Pune Hub"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Reason for Update
                      </label>
                      <select
                        value={updReasonCode}
                        onChange={(e) => setUpdReasonCode(e.target.value)}
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      >
                        <option value="1">1 - Due to Transshipment</option>
                        <option value="2">2 - Vehicle Breakdown</option>
                        <option value="3">3 - Not updated earlier</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Remarks
                      </label>
                      <input
                        type="text"
                        value={updRemarks}
                        onChange={(e) => setUpdRemarks(e.target.value)}
                        placeholder="e.g. Transshipped at logistics hub"
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-border/40">
                    <button
                      type="button"
                      onClick={() => setActiveTab('VIEW')}
                      className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors"
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="px-5 py-2.5 rounded-xl text-xs font-bold bg-primary hover:bg-primary/90 text-primary-foreground shadow-md transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      {actionLoading ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Updating Part-B...</span>
                        </>
                      ) : (
                        <>
                          <RotateCcw className="w-4 h-4" />
                          <span>Save &amp; Update Vehicle</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* CANCEL FORM */}
              {activeTab === 'CANCEL' && ewayRecord && (
                <form onSubmit={handleCancelEwayBill} className="space-y-4">
                  <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-400 space-y-1">
                    <div className="font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-rose-500" />
                      Notice: E-Way Bill Cancellation Rules
                    </div>
                    <p>
                      According to GST rules, an E-Way Bill can only be cancelled within 24 hours of generation if the goods are not in transit.
                    </p>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Reason for Cancellation <span className="text-primary">*</span>
                      </label>
                      <select
                        value={cancelReasonCode}
                        onChange={(e) => setCancelReasonCode(e.target.value)}
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary"
                      >
                        <option value="1">1 - Duplicate E-Way Bill</option>
                        <option value="2">2 - Order Cancelled by Buyer</option>
                        <option value="3">3 - Data Entry Mistake</option>
                        <option value="4">4 - Other</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">
                        Cancellation Remarks <span className="text-primary">*</span>
                      </label>
                      <textarea
                        rows={2}
                        required
                        value={cancelRemarks}
                        onChange={(e) => setCancelRemarks(e.target.value)}
                        placeholder="Provide reason for cancelling this E-Way bill..."
                        className="w-full bg-muted/40 border border-input text-foreground p-2.5 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary resize-none"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-border/40">
                    <button
                      type="button"
                      onClick={() => setActiveTab('VIEW')}
                      className="px-4 py-2 rounded-xl text-xs font-semibold bg-muted hover:bg-muted/80 text-foreground transition-colors"
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="px-5 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white shadow-md transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                    >
                      {actionLoading ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Cancelling...</span>
                        </>
                      ) : (
                        <>
                          <Ban className="w-4 h-4" />
                          <span>Confirm Cancellation</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
