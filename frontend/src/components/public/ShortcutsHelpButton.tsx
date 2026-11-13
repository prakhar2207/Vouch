"use client";

import React from "react";
import { ChevronRight } from "lucide-react";
import { useShortcuts } from "@/context/ShortcutContext";

export function ShortcutsHelpButton() {
  const { setIsHelpOpen } = useShortcuts();

  return (
    <button
      type="button"
      onClick={() => setIsHelpOpen(true)}
      className="hover:text-foreground transition-colors cursor-pointer inline-flex items-center gap-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ChevronRight className="w-3 h-3 shrink-0" />
      <span>Keyboard Shortcuts (F1)</span>
    </button>
  );
}
