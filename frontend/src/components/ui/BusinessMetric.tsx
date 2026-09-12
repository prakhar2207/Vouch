import React from "react";
import Link from "next/link";
import { LucideIcon } from "lucide-react";

export interface BusinessMetricProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon?: LucideIcon;
  href?: string;
  accentColor?: "emerald" | "blue" | "amber" | "rose" | "indigo" | "purple";
}

const colorMap = {
  emerald: {
    stripe: "from-emerald-500 to-teal-500",
    text: "text-emerald-500",
    icon: "text-emerald-500/70",
    borderHover: "hover:border-emerald-500/40",
  },
  blue: {
    stripe: "from-blue-500 to-indigo-500",
    text: "text-blue-500",
    icon: "text-blue-500/70",
    borderHover: "hover:border-blue-500/40",
  },
  amber: {
    stripe: "from-amber-500 to-orange-500",
    text: "text-amber-500",
    icon: "text-amber-500/70",
    borderHover: "hover:border-amber-500/40",
  },
  rose: {
    stripe: "from-rose-500 to-red-500",
    text: "text-rose-500",
    icon: "text-rose-500/70",
    borderHover: "hover:border-rose-500/40",
  },
  indigo: {
    stripe: "from-indigo-500 to-purple-500",
    text: "text-indigo-500",
    icon: "text-indigo-500/70",
    borderHover: "hover:border-indigo-500/40",
  },
  purple: {
    stripe: "from-purple-500 to-violet-500",
    text: "text-purple-500",
    icon: "text-purple-500/70",
    borderHover: "hover:border-purple-500/40",
  },
};

export default function BusinessMetric({
  label,
  value,
  subtitle,
  icon: Icon,
  href,
  accentColor = "blue",
}: BusinessMetricProps) {
  const colors = colorMap[accentColor] || colorMap.blue;

  const content = (
    <div
      className={`bg-card border border-border/40 rounded-xl p-4 shadow-sm space-y-1 relative overflow-hidden transition-all ${
        href ? `cursor-pointer ${colors.borderHover}` : ""
      }`}
    >
      <div
        className={`absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b ${colors.stripe}`}
      />
      <div className="flex items-center justify-between text-muted-foreground pl-2">
        <span className="text-xs font-medium">{label}</span>
        {Icon && <Icon className={`w-4 h-4 ${colors.icon}`} />}
      </div>
      <div className={`text-xl font-bold font-mono tabular-nums tracking-tight ${colors.text} pl-2`}>
        {value}
      </div>
      {subtitle && (
        <div className="text-[11px] text-muted-foreground pl-2">{subtitle}</div>
      )}
    </div>
  );

  if (href) {
    return <Link href={href}>{content}</Link>;
  }

  return content;
}
