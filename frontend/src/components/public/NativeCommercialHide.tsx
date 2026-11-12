"use client";

import React from "react";
import { useIsNativeApp } from "@/hooks/useIsNativeApp";

/**
 * Hides web-only pricing, refund/payment, or checkout references inside the
 * native Android container while rendering normally on public web browsers.
 */
export function NativeCommercialHide({ children }: { children: React.ReactNode }) {
  const isNative = useIsNativeApp();
  if (isNative) return null;
  return <>{children}</>;
}
