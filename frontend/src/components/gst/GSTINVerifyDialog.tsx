"use client";
import React, { useState } from "react";
import { CheckCircle2, AlertTriangle, ShieldCheck, RefreshCw, X, ArrowRight, ExternalLink } from "lucide-react";
import { gstApi } from "@/lib/api/gst";
import { useToast } from "@/context/ToastContext";

interface Props {
  gstin: string;
  partyId?: string;
  currentPartyName?: string;
  currentStateCode?: string;
  currentAddress?: string;
  onApply: (data: {
    name?: string;
    trade_name?: string;
    state_code?: string;
    address?: string;
    pincode?: string;
  }) => void;
  disabled?: boolean;
}

export default function GSTINVerifyDialog({
  gstin,
  partyId,
  currentPartyName,
  currentStateCode,
  currentAddress,
  onApply,
  disabled
}: Props) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [verifyData, setVerifyData] = useState<any>(null);
  const [applyLegalName, setApplyLegalName] = useState(true);
  const [applyState, setApplyState] = useState(true);
  const [applyAddress, setApplyAddress] = useState(true);

  const handleVerify = async () => {
    const clean = (gstin || "").trim().toUpperCase();
    if (!clean) {
      toast.warning("Please enter a 15-character GSTIN first.");
      return;
    }
    if (clean.length !== 15) {
      toast.warning("GSTIN must be exactly 15 characters.");
      return;
    }

    setLoading(true);
    try {
      const res = await gstApi.verifyGSTIN(clean, partyId);
      if (res.success && res.data) {
        setVerifyData(res.data);
        setIsOpen(true);
        if (res.data.status === "ACTIVE") {
          toast.success("GSTIN Verified", `${res.data.legal_name || clean} is ACTIVE`);
        } else {
          toast.warning("GSTIN Status Warning", `Taxpayer status is ${res.data.status}`);
        }
      } else {
        toast.error("Verification Failed", res.error || "Unable to verify GSTIN with portal.");
      }
    } catch (err: any) {
      const msg = err.response?.data?.error || err.response?.data?.message || err.message || "Failed to contact GST verification service";
      toast.error("Verification Failed", msg);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyChanges = () => {
    if (!verifyData) return;
    const updates: Record<string, string> = {};
    if (applyLegalName) {
      updates.name = verifyData.legal_name || verifyData.trade_name || currentPartyName;
      updates.trade_name = verifyData.trade_name || "";
    }
    if (applyState && verifyData.state_code) {
      updates.state_code = verifyData.state_code;
    }
    if (applyAddress && verifyData.address) {
      updates.address = verifyData.address;
    }
    if (verifyData.pincode) {
      updates.pincode = verifyData.pincode;
    }

    onApply(updates);
    setIsOpen(false);
    toast.success("Party Updated", "Verified GST details applied to form.");
  };

  return (
    <>
      <button
        type="button"
        onClick={handleVerify}
        disabled={disabled || loading || !gstin || gstin.trim().length < 15}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 border border-emerald-500/30 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <>
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            <span>Verifying...</span>
          </>
        ) : (
          <>
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Verify with GST</span>
          </>
        )}
      </button>

      {isOpen && verifyData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in">
          <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl relative space-y-5">
            <button
              onClick={() => setIsOpen(false)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-muted/50"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-xl ${verifyData.status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500'}`}>
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">Verified GSTIN Record</h3>
                <p className="text-xs font-mono text-muted-foreground">{verifyData.gstin}</p>
              </div>
              <span className={`ml-auto px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                verifyData.status === 'ACTIVE' 
                  ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30'
                  : 'bg-red-500/10 text-red-500 border border-red-500/30'
              }`}>
                {verifyData.status || 'UNKNOWN'}
              </span>
            </div>

            <div className="divide-y divide-border/60 text-xs rounded-xl border border-border/60 overflow-hidden bg-muted/20">
              {/* Legal Name */}
              <div className="p-3.5 flex items-start justify-between gap-3">
                <div className="space-y-1 flex-1">
                  <div className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Legal / Trade Name</div>
                  <div className="text-foreground font-bold">{verifyData.legal_name || '—'}</div>
                  {verifyData.trade_name && (
                    <div className="text-muted-foreground text-[11px]">Trade: {verifyData.trade_name}</div>
                  )}
                  {currentPartyName && currentPartyName !== verifyData.legal_name && (
                    <div className="text-amber-500/90 text-[11px] pt-1">
                      Current in Books: <span className="font-semibold">{currentPartyName}</span>
                    </div>
                  )}
                </div>
                <label className="flex items-center gap-2 cursor-pointer mt-1">
                  <input
                    type="checkbox"
                    checked={applyLegalName}
                    onChange={(e) => setApplyLegalName(e.target.checked)}
                    className="rounded border-input text-primary focus:ring-primary"
                  />
                  <span className="text-[11px] font-medium text-foreground">Apply</span>
                </label>
              </div>

              {/* State */}
              <div className="p-3.5 flex items-start justify-between gap-3">
                <div className="space-y-1 flex-1">
                  <div className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">State Code</div>
                  <div className="text-foreground font-bold">
                    {verifyData.state_code ? `${verifyData.state_code} (${verifyData.state_name || 'State'})` : '—'}
                  </div>
                  {currentStateCode && currentStateCode !== verifyData.state_code && (
                    <div className="text-amber-500/90 text-[11px]">
                      Current in Books: <span className="font-semibold">{currentStateCode}</span>
                    </div>
                  )}
                </div>
                <label className="flex items-center gap-2 cursor-pointer mt-1">
                  <input
                    type="checkbox"
                    checked={applyState}
                    onChange={(e) => setApplyState(e.target.checked)}
                    className="rounded border-input text-primary focus:ring-primary"
                  />
                  <span className="text-[11px] font-medium text-foreground">Apply</span>
                </label>
              </div>

              {/* Address */}
              <div className="p-3.5 flex items-start justify-between gap-3">
                <div className="space-y-1 flex-1">
                  <div className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Registered Principal Address</div>
                  <div className="text-foreground leading-relaxed font-medium">
                    {verifyData.address || '—'} {verifyData.pincode ? `(${verifyData.pincode})` : ''}
                  </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer mt-1">
                  <input
                    type="checkbox"
                    checked={applyAddress}
                    onChange={(e) => setApplyAddress(e.target.checked)}
                    className="rounded border-input text-primary focus:ring-primary"
                  />
                  <span className="text-[11px] font-medium text-foreground">Apply</span>
                </label>
              </div>

              {/* Taxpayer Type */}
              <div className="p-3.5 flex items-center justify-between">
                <span className="font-semibold text-muted-foreground uppercase text-[10px] tracking-wider">Taxpayer Type</span>
                <span className="font-bold text-foreground">{verifyData.taxpayer_type || 'Regular'}</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleApplyChanges}
                className="px-5 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all flex items-center gap-1.5 shadow-sm cursor-pointer"
              >
                <span>Apply to Party Record</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
