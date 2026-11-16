"use client";
import React, { useState, useEffect, useCallback } from "react";
import { 
  Building2, 
  ShieldCheck, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Plus, 
  X, 
  Check, 
  ExternalLink,
  Edit2,
  Trash2,
  Power,
  Info
} from "lucide-react";
import { gstApi, GSTRegistration } from "@/lib/api/gst";
import { useToast } from "@/context/ToastContext";
import StateSelect from "@/components/StateSelect";

interface Props {
  companyId: string;
  companyName: string;
}

export default function GSTRegistrationsView({ companyId, companyName }: Props) {
  const { toast } = useToast();
  const [registrations, setRegistrations] = useState<GSTRegistration[]>([]);
  const [loading, setLoading] = useState(false);

  // Add / Edit Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingReg, setEditingReg] = useState<GSTRegistration | null>(null);

  // Form Fields
  const [inputGstin, setInputGstin] = useState("");
  const [inputStateCode, setInputStateCode] = useState("");
  const [inputLegalName, setInputLegalName] = useState("");
  const [inputTradeName, setInputTradeName] = useState("");
  const [inputAddress, setInputAddress] = useState("");
  const [inputPincode, setInputPincode] = useState("");
  const [inputTaxpayerType, setInputTaxpayerType] = useState("REGULAR");
  const [inputIsPrimary, setInputIsPrimary] = useState(false);

  // Verification Step in Modal
  const [verifying, setVerifying] = useState(false);
  const [verifiedDetails, setVerifiedDetails] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  // Single record verifying action
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const fetchRegistrations = useCallback(async () => {
    if (!companyId) return;
    setLoading(true);
    try {
      const data = await gstApi.getRegistrations(companyId);
      setRegistrations(data);
    } catch (err: any) {
      toast.error("Error", err.response?.data?.error || err.message || "Failed to load GST registrations.");
    } finally {
      setLoading(false);
    }
  }, [companyId, toast]);

  useEffect(() => {
    fetchRegistrations();
  }, [fetchRegistrations]);

  const handleOpenAddModal = () => {
    setEditingReg(null);
    setInputGstin("");
    setInputStateCode("");
    setInputLegalName("");
    setInputTradeName("");
    setInputAddress("");
    setInputPincode("");
    setInputTaxpayerType("REGULAR");
    setInputIsPrimary(registrations.length === 0);
    setVerifiedDetails(null);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (reg: GSTRegistration) => {
    setEditingReg(reg);
    setInputGstin(reg.gstin);
    setInputStateCode(reg.state_code);
    setInputLegalName(reg.legal_name);
    setInputTradeName(reg.trade_name);
    setInputAddress(reg.address);
    setInputPincode(reg.pincode);
    setInputTaxpayerType(reg.taxpayer_type);
    setInputIsPrimary(reg.is_primary);
    setVerifiedDetails(null);
    setIsModalOpen(true);
  };

  const handleVerifyInModal = async () => {
    const clean = inputGstin.trim().toUpperCase();
    if (clean.length !== 15) {
      toast.warning("GSTIN must be 15 alphanumeric characters.");
      return;
    }

    setVerifying(true);
    try {
      const res = await gstApi.verifyRegistrationPreview(companyId, clean);
      if (res.success) {
        setVerifiedDetails(res);
        setInputLegalName(res.legal_name || inputLegalName);
        setInputTradeName(res.trade_name || inputTradeName || res.legal_name);
        setInputStateCode(res.state_code || inputStateCode);
        setInputAddress(res.address || inputAddress);
        setInputPincode(res.pincode || inputPincode);
        setInputTaxpayerType(res.taxpayer_type || inputTaxpayerType);

        if (res.source === 'provider_live') {
          toast.success("GSTIN Verified (Live)", `${res.legal_name || clean} (${res.status || 'Active'})`);
        } else if (res.is_cached) {
          toast.success("GSTIN Verified (Cache)", `${res.legal_name || clean} (${res.status || 'Active'})`);
        } else {
          toast.warning("GSTIN Format Valid", `${res.legal_name || clean} (Gateway Offline - Validated Locally)`);
        }
      } else {
        toast.error("Verification Failed", res.error || "Could not verify GSTIN with portal.");
      }
    } catch (err: any) {
      toast.error("Verification Error", err.response?.data?.error || err.message || "Gateway unreachable.");
    } finally {
      setVerifying(false);
    }
  };

  const handleSaveRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputGstin.trim().toUpperCase();
    if (clean.length !== 15) {
      toast.warning("GSTIN must be 15 alphanumeric characters.");
      return;
    }

    if (!editingReg && !verifiedDetails) {
      const confirmed = window.confirm(
        "This GSTIN has not been verified against the GST portal. Are you sure you want to save it as unverified?"
      );
      if (!confirmed) {
        return;
      }
    }

    setSaving(true);
    try {
      if (editingReg) {
        await gstApi.updateRegistration(companyId, editingReg.id, {
          trade_name: inputTradeName,
          legal_name: inputLegalName,
          address: inputAddress,
          pincode: inputPincode,
          taxpayer_type: inputTaxpayerType,
          is_primary: inputIsPrimary,
        });
        toast.success("Saved", `Registration '${clean}' updated successfully.`);
      } else {
        await gstApi.createRegistration(companyId, {
          gstin: clean,
          state_code: inputStateCode || clean.slice(0, 2),
          legal_name: inputLegalName || clean,
          trade_name: inputTradeName || inputLegalName || clean,
          address: inputAddress,
          pincode: inputPincode,
          taxpayer_type: inputTaxpayerType,
          is_primary: inputIsPrimary,
          auto_verify: false // Already verified via preview
        });
        toast.success("Created", `Registration '${clean}' added successfully.`);
      }
      setIsModalOpen(false);
      fetchRegistrations();
    } catch (err: any) {
      toast.error("Save Failed", err.response?.data?.error || err.message || "Failed to save registration.");
    } finally {
      setSaving(false);
    }
  };

  const handleVerifySingle = async (regId: string) => {
    setVerifyingId(regId);
    try {
      const res = await gstApi.verifyRegistration(companyId, regId, true);
      if (res.success) {
        toast.success("Verified", "Registration status refreshed from Sandbox.");
        fetchRegistrations();
      } else {
        toast.error("Verification Failed", res.error || "Could not refresh status.");
      }
    } catch (err: any) {
      toast.error("Error", err.response?.data?.error || err.message);
    } finally {
      setVerifyingId(null);
    }
  };

  const handleToggleActive = async (reg: GSTRegistration) => {
    if (reg.status === 'ACTIVE') {
      const confirmed = window.confirm(
        `Are you sure you want to deactivate registration '${reg.gstin}'? Invoices cannot be filed under an inactive registration.`
      );
      if (!confirmed) return;
    }

    try {
      if (reg.status === 'ACTIVE') {
        await gstApi.deactivateRegistration(companyId, reg.id);
        toast.success("Deactivated", `Registration '${reg.gstin}' is now INACTIVE.`);
      } else {
        await gstApi.reactivateRegistration(companyId, reg.id);
        toast.success("Reactivated", `Registration '${reg.gstin}' is now ACTIVE.`);
      }
      fetchRegistrations();
    } catch (err: any) {
      toast.error("Action Failed", err.response?.data?.error || err.message);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">ACTIVE</span>;
      case 'INACTIVE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-muted text-muted-foreground border border-border">INACTIVE</span>;
      case 'CANCELLED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/10 text-red-500 border border-red-500/20">CANCELLED</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20">{status}</span>;
    }
  };

  const getVerificationBadge = (vStatus: string) => {
    switch (vStatus) {
      case 'VERIFIED':
        return <span className="inline-flex items-center gap-1 text-[11px] text-emerald-500 font-semibold"><CheckCircle2 className="w-3.5 h-3.5" /> Verified</span>;
      case 'PENDING':
        return <span className="inline-flex items-center gap-1 text-[11px] text-blue-500 font-semibold"><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Pending</span>;
      case 'INVALID':
        return <span className="inline-flex items-center gap-1 text-[11px] text-red-500 font-semibold"><AlertTriangle className="w-3.5 h-3.5" /> Invalid</span>;
      case 'PROVIDER_UNAVAILABLE':
        return <span className="inline-flex items-center gap-1 text-[11px] text-amber-500 font-semibold"><Info className="w-3.5 h-3.5" /> Gateway Offline</span>;
      default:
        return <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground font-semibold"><Info className="w-3.5 h-3.5" /> Not Verified</span>;
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header Card */}
      <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-2xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-border/40 gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-foreground">GST Registrations (Multi-GSTIN)</h2>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-muted text-muted-foreground border border-border/40">
                  {registrations.length} Configured
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Manage state-level GSTINs for {companyName}. Verified via Sandbox by Quicko.
              </p>
            </div>
          </div>

          <button
            onClick={handleOpenAddModal}
            className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm cursor-pointer shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>Add GST Registration</span>
          </button>
        </div>

        {/* Registrations List */}
        {loading ? (
          <div className="py-12 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Loading registrations...</span>
          </div>
        ) : registrations.length === 0 ? (
          <div className="py-12 text-center text-xs text-muted-foreground space-y-2">
            <p>No GST registrations added yet for this company.</p>
            <p className="text-[11px]">Click "Add GST Registration" to enter and verify your 15-digit GSTIN.</p>
          </div>
        ) : (
          <div className="divide-y divide-border/40 border border-border/60 rounded-xl overflow-hidden bg-muted/10">
            {registrations.map((reg) => (
              <div key={reg.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-foreground text-sm">{reg.gstin}</span>
                    {reg.is_primary && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
                        ★ PRIMARY
                      </span>
                    )}
                    {getStatusBadge(reg.status)}
                    <span className="text-muted-foreground font-semibold">State: {reg.state_code} ({reg.state_name || 'State'})</span>
                  </div>

                  <div className="text-foreground font-medium">
                    {reg.legal_name} {reg.trade_name && reg.trade_name !== reg.legal_name ? `• ${reg.trade_name}` : ''}
                  </div>

                  {reg.address && (
                    <div className="text-[11px] text-muted-foreground line-clamp-1">
                      {reg.address} {reg.pincode ? `(${reg.pincode})` : ''}
                    </div>
                  )}

                  <div className="flex items-center gap-3 pt-1">
                    {getVerificationBadge(reg.verification_status)}
                    {reg.last_verified_at && (
                      <span className="text-[10px] text-muted-foreground">
                        Last verified: {new Date(reg.last_verified_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleVerifySingle(reg.id)}
                    disabled={verifyingId === reg.id}
                    title="Verify now with Sandbox"
                    className="px-2.5 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-[11px] font-semibold flex items-center gap-1 cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${verifyingId === reg.id ? 'animate-spin' : ''}`} />
                    <span>Verify</span>
                  </button>

                  <button
                    onClick={() => handleOpenEditModal(reg)}
                    title="Edit registration"
                    className="p-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-[11px] cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>

                  <button
                    onClick={() => handleToggleActive(reg)}
                    title={reg.status === 'ACTIVE' ? 'Deactivate' : 'Reactivate'}
                    className={`p-1.5 rounded-lg border border-border bg-card hover:bg-muted text-[11px] cursor-pointer ${
                      reg.status === 'ACTIVE' ? 'text-amber-500 hover:text-amber-600' : 'text-emerald-500 hover:text-emerald-600'
                    }`}
                  >
                    <Power className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl relative space-y-4 max-h-[90vh] overflow-y-auto">
            <button
              onClick={() => setIsModalOpen(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted/50"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-primary/10 text-primary">
                <Building2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">
                  {editingReg ? "Edit GST Registration" : "Add GST Registration"}
                </h3>
                <p className="text-xs text-muted-foreground">
                  Enter GSTIN and verify with Sandbox by Quicko
                </p>
              </div>
            </div>

            <form onSubmit={handleSaveRegistration} className="space-y-4 text-xs">
              {/* GSTIN Input with Verify Button */}
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                  GSTIN Number *
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    maxLength={15}
                    placeholder="e.g. 27AADCB2230M1ZT"
                    value={inputGstin}
                    onChange={(e) => {
                      const val = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
                      setInputGstin(val);
                      if (val.length >= 2 && !inputStateCode) {
                        setInputStateCode(val.slice(0, 2));
                      }
                    }}
                    disabled={!!editingReg}
                    required
                    className="flex-1 bg-muted/30 border border-input rounded-xl px-3 py-2 font-mono uppercase text-foreground outline-none focus:ring-2 focus:ring-primary disabled:opacity-60"
                  />
                  {!editingReg && (
                    <button
                      type="button"
                      onClick={handleVerifyInModal}
                      disabled={verifying || inputGstin.length !== 15}
                      className="px-3.5 py-2 rounded-xl bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/30 font-bold flex items-center gap-1.5 transition-all disabled:opacity-50 cursor-pointer shrink-0"
                    >
                      {verifying ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                      <span>Verify</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Verified Details Card (if returned) */}
              {verifiedDetails && (
                <div className="p-3.5 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    {verifiedDetails.source === 'provider_live' ? (
                      <span className="font-bold text-emerald-500 flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Portal Verified (Live)
                      </span>
                    ) : (verifiedDetails.is_cached || verifiedDetails.source === 'local_cache') ? (
                      <span className="font-bold text-blue-500 flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Verified via Cache
                      </span>
                    ) : (
                      <span className="font-bold text-amber-500 flex items-center gap-1">
                        <AlertTriangle className="w-3.5 h-3.5" /> Format Validated (Gateway Offline)
                      </span>
                    )}
                    <span className="font-bold uppercase text-foreground">{verifiedDetails.status || 'Active'}</span>
                  </div>
                  <div className="font-semibold text-foreground text-xs">{verifiedDetails.legal_name}</div>
                  {verifiedDetails.address && (
                    <div className="text-[10px] text-muted-foreground">{verifiedDetails.address}</div>
                  )}
                </div>
              )}

              {/* Legal Name */}
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                  Legal Business Name *
                </label>
                <input
                  type="text"
                  required
                  value={inputLegalName}
                  onChange={(e) => setInputLegalName(e.target.value)}
                  placeholder="Legal name on GST Portal"
                  className="w-full bg-muted/30 border border-input rounded-xl px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              {/* Trade Name */}
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                  Trade Name / DBA
                </label>
                <input
                  type="text"
                  value={inputTradeName}
                  onChange={(e) => setInputTradeName(e.target.value)}
                  placeholder="Trade name (optional)"
                  className="w-full bg-muted/30 border border-input rounded-xl px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              {/* State & Pincode Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <StateSelect
                    value={inputStateCode}
                    onChange={(code) => setInputStateCode(code)}
                    label="State / UT"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                    Pincode
                  </label>
                  <input
                    type="text"
                    maxLength={6}
                    value={inputPincode}
                    onChange={(e) => setInputPincode(e.target.value)}
                    placeholder="e.g. 400001"
                    className="w-full bg-muted/30 border border-input rounded-xl px-3 py-2 text-foreground outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Address */}
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                  Principal Place of Business Address
                </label>
                <textarea
                  rows={2}
                  value={inputAddress}
                  onChange={(e) => setInputAddress(e.target.value)}
                  placeholder="Registered address"
                  className="w-full bg-muted/30 border border-input rounded-xl p-2.5 text-foreground outline-none focus:ring-2 focus:ring-primary resize-none"
                />
              </div>

              {/* Primary Toggle */}
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={inputIsPrimary}
                  onChange={(e) => setInputIsPrimary(e.target.checked)}
                  className="rounded border-input text-primary focus:ring-primary"
                />
                <span className="font-medium text-foreground">Set as Primary GST Registration for this company</span>
              </label>

              {/* Modal Buttons */}
              <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border/40">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !inputGstin || inputGstin.length !== 15}
                  className="px-5 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5 shadow-sm"
                >
                  {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  <span>{editingReg ? "Save Changes" : "Confirm & Save Registration"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
