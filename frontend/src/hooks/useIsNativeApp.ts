"use client";

import { useEffect, useState } from "react";
import { isCapacitorNative } from "@/utils/auth";

/**
 * Hydration-safe hook that returns true strictly when rendered inside
 * a Capacitor native container (Android / iOS). Always returns false on SSR
 * and standard desktop/mobile web browsers.
 */
export function useIsNativeApp(): boolean {
  const [native, setNative] = useState(false);

  useEffect(() => {
    if (isCapacitorNative()) {
      setNative(true);
    }
  }, []);

  return native;
}
