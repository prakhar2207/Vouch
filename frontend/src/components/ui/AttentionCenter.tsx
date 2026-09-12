import React from "react";
import Link from "next/link";

export interface AttentionItem {
  message: string;
  type?: "money" | "stock" | "banking" | "general";
  href?: string;
}

export interface AttentionCenterProps {
  items: AttentionItem[];
  title?: string;
  viewAllHref?: string;
  maxDisplay?: number;
}

export default function AttentionCenter({
  items,
  title = "Needs your attention",
  viewAllHref = "/health",
  maxDisplay = 5,
}: AttentionCenterProps) {
  if (!items || items.length === 0) return null;

  return (
    <div className="bg-card border border-border/40 rounded-xl p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {viewAllHref && (
          <Link
            href={viewAllHref}
            className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors"
          >
            View all →
          </Link>
        )}
      </div>
      <div className="space-y-2">
        {items.slice(0, maxDisplay).map((item, idx) => {
          const isOverdue = item.message?.toLowerCase().includes("overdue");
          const isLowStock = item.message?.toLowerCase().includes("stock");
          const dotColor = isOverdue
            ? "bg-rose-400"
            : isLowStock
            ? "bg-amber-400"
            : "bg-blue-400";

          const rowContent = (
            <div className="flex items-center gap-2.5 py-1.5 text-xs text-foreground hover:text-primary transition-colors">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
              <span>{item.message}</span>
            </div>
          );

          if (item.href) {
            return (
              <Link key={idx} href={item.href} className="block">
                {rowContent}
              </Link>
            );
          }

          return <div key={idx}>{rowContent}</div>;
        })}
      </div>
    </div>
  );
}
