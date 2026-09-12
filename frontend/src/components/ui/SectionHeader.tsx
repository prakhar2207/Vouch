import React from "react";
import Link from "next/link";
import { LucideIcon } from "lucide-react";

export interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  badge?: string;
  badgeVariant?: "default" | "success" | "warning" | "error" | "info";
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  icon?: LucideIcon;
  children?: React.ReactNode;
}

export default function SectionHeader({
  title,
  subtitle,
  badge,
  badgeVariant = "default",
  actionLabel,
  actionHref,
  onAction,
  icon: Icon,
  children,
}: SectionHeaderProps) {
  const badgeStyles = {
    default: "bg-muted text-muted-foreground border-border/50",
    success: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    error: "bg-rose-500/10 text-rose-500 border-rose-500/20",
    info: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-1">
      <div>
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-primary" />}
          <h2 className="text-sm font-semibold text-foreground tracking-tight">
            {title}
          </h2>
          {badge && (
            <span
              className={`text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border ${badgeStyles[badgeVariant]}`}
            >
              {badge}
            </span>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        {children}
        {actionLabel && actionHref && (
          <Link
            href={actionHref}
            className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors"
          >
            {actionLabel}
          </Link>
        )}
        {actionLabel && onAction && !actionHref && (
          <button
            type="button"
            onClick={onAction}
            className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors cursor-pointer"
          >
            {actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}
