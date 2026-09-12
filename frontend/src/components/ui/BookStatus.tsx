import React from "react";
import Link from "next/link";
import { CheckCircle2, Info, Activity, ArrowUpRight } from "lucide-react";

export interface BookStatusProps {
  healthReport?: any;
  detailsHref?: string;
}

export default function BookStatus({
  healthReport,
  detailsHref = "/health",
}: BookStatusProps) {
  const score = healthReport?.health_score ?? 100;
  const isHealthy = score >= 90;
  const isCritical = healthReport?.health_status === "CRITICAL" || score < 70;

  return (
    <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
            isHealthy
              ? "bg-emerald-500/10 text-emerald-400"
              : isCritical
              ? "bg-rose-500/10 text-rose-400"
              : "bg-amber-500/10 text-amber-400"
          }`}
        >
          {isHealthy ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : isCritical ? (
            <Info className="w-4 h-4" />
          ) : (
            <Activity className="w-4 h-4" />
          )}
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {healthReport ? (
              isHealthy
                ? "Your books look good"
                : isCritical
                ? `${healthReport.metrics?.critical_findings_count || 1} things need review`
                : "Some things need attention"
            ) : (
              "Books status"
            )}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {healthReport ? (
              isHealthy
                ? `Last checked ${
                    healthReport._cachedAt
                      ? new Date(healthReport._cachedAt).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "recently"
                  }`
                : "Review recommended"
            ) : (
              "Run a check to see how your books are doing"
            )}
          </p>
        </div>
      </div>
      <Link
        href={detailsHref}
        className="px-3.5 py-2 rounded-xl border border-border/60 bg-muted/40 hover:bg-muted text-foreground text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
      >
        <span>{!isHealthy ? "Review now" : "View details"}</span>
        <ArrowUpRight className="w-3 h-3" />
      </Link>
    </div>
  );
}
