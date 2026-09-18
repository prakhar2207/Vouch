"use client";
import React, { useState, useEffect } from "react";
import axios from "axios";
import { getAccessToken } from "@/utils/auth";
import { History, User, Clock, CheckCircle2, ShieldCheck, X } from "lucide-react";

interface AuditHistoryModalProps {
  voucherId: string;
  voucherNumber: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function AuditHistoryModal({
  voucherId,
  voucherNumber,
  isOpen,
  onClose,
}: AuditHistoryModalProps) {
  const [loading, setLoading] = useState(false);
  const [revisions, setRevisions] = useState<any[]>([]);

  useEffect(() => {
    if (isOpen && voucherId) {
      fetchHistory();
    }
  }, [isOpen, voucherId]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const token = getAccessToken();
      const res = await axios.get(
        `http://localhost:8000/api/v1/accounting/vouchers/${voucherId}/history/`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setRevisions(res.data.revisions || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-card border border-border rounded-2xl max-w-2xl w-full p-6 space-y-5 shadow-2xl text-foreground max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-blue-600/10 text-blue-500 font-bold">
              <History className="w-5 h-5" />
            </span>
            <div>
              <h3 className="text-lg font-bold">Voucher Audit Trail & Version History</h3>
              <p className="text-xs text-muted-foreground">
                Invoice #{voucherNumber} • MCA Statutory Edit Log
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

        {/* MCA Compliance Callout */}
        <div className="p-3.5 bg-muted/40 border border-border rounded-xl flex items-start gap-2.5 text-xs text-muted-foreground">
          <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
          <span>
            <strong>MCA Compliant (Non-Freezing):</strong> You retain 100% freedom to rectify clerical errors anytime. Every version snapshot is recorded with user identity and timestamp to ensure complete statutory audit readiness.
          </span>
        </div>

        {/* Timeline */}
        {loading ? (
          <div className="py-12 text-center text-xs text-muted-foreground">Loading audit log...</div>
        ) : revisions.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No revision history found.</div>
        ) : (
          <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
            {revisions.map((rev, idx) => {
              const isCurrent = idx === revisions.length - 1;
              return (
                <div key={rev.id} className="relative space-y-2 text-xs">
                  {/* Timeline Dot */}
                  <span
                    className={`absolute -left-6 top-1 w-3 h-3 rounded-full border-2 ${
                      isCurrent
                        ? "bg-blue-600 border-blue-400 ring-4 ring-blue-500/20"
                        : "bg-muted border-muted-foreground"
                    }`}
                  />

                  {/* Version Header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-foreground font-mono">
                        Version {rev.version}
                      </span>
                      {isCurrent ? (
                        <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800 rounded text-[10px] font-bold">
                          ACTIVE CURRENT
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-muted text-muted-foreground rounded text-[10px]">
                          SUPERSEDED
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {rev.timestamp || rev.date}
                    </span>
                  </div>

                  {/* Version Detail Card */}
                  <div className="p-3.5 bg-muted/20 border border-border rounded-xl space-y-1.5">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5" />
                        <span>Action by:</span>
                      </span>
                      <span className="font-semibold text-foreground">
                        {rev.user_name || "Accountant"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Voucher Total:</span>
                      <span className="font-mono font-bold text-foreground">
                        ₹{rev.total_amount.toFixed(2)}
                      </span>
                    </div>

                    {rev.correction_reason && (
                      <div className="pt-1 border-t border-border/50 text-muted-foreground">
                        <span className="font-medium text-foreground">Reason for edit: </span>
                        <span>{rev.correction_reason}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="pt-2 border-t border-border flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-xl text-xs font-semibold cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
