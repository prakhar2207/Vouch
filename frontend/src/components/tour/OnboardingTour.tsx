"use client";
import React, { useEffect } from "react";
import { driver, DriveStep } from "driver.js";
import "driver.js/dist/driver.css";
import { useShortcuts } from "@/context/ShortcutContext";
import { isAuthenticated } from "@/utils/auth";

export default function OnboardingTour() {
  const { setTourStarter } = useShortcuts();

  const startGuidedTour = () => {
    const allSteps: DriveStep[] = [
      {
        element: "#tour-header-brand",
        popover: {
          title: "⚡ Welcome to Vouch",
          description: "A fast, keyboard-driven double-entry accounting and ERP platform designed to make billing, inventory, and GST compliance effortless.",
          side: "bottom",
          align: "start",
        },
      },
      {
        element: "#tour-command-palette-btn",
        popover: {
          title: "🔍 Instant Search (Ctrl + K)",
          description: "Press Ctrl+K or Cmd+K anytime to quickly look up customers, check product stock quantities, or jump to any screen without touching your mouse.",
          side: "bottom",
          align: "start",
        },
      },
      {
        element: "#tour-business-health",
        popover: {
          title: "📈 Sales Pace & Business Health",
          description: "Shows at a glance whether your sales are Booming 🚀, Steady ⚖️, or Slowing down 📉, alongside customer loyalty groups to help you grow revenue.",
          side: "top",
          align: "center",
        },
      },
      {
        element: "#tour-sales-btn",
        popover: {
          title: "🧾 Create Sales Invoices (F8)",
          description: "Press F8 to bill customers. Taxes (CGST/SGST for local vs IGST for out-of-state) and stock deductions are handled automatically.",
          side: "left",
          align: "center",
        },
      },
      {
        element: "#tour-purchase-btn",
        popover: {
          title: "🤖 AI Bill Scanner (F9)",
          description: "Press F9 to snap or upload vendor invoices. Our AI reads all items and taxes into a side-by-side review screen so you don't have to type.",
          side: "left",
          align: "center",
        },
      },
      {
        element: "#tour-b2b-btn",
        popover: {
          title: "⚡ B2B Network (EDI)",
          description: "Receive e-invoices directly from your registered suppliers and auto-post stock in 1 click.",
          side: "bottom",
          align: "center",
        },
      },
      {
        element: "#tour-help-btn",
        popover: {
          title: "❓ Shortcuts & How-To Guides (F1)",
          description: "Press F1 anytime to view the complete keyboard shortcuts list, read step-by-step feature tutorials, or re-launch this tour.",
          side: "top",
          align: "center",
        },
      },
    ];

    // Filter to only steps whose target elements actually exist in current DOM to prevent driver.js crashes
    const validSteps = allSteps.filter((s) => {
      if (typeof s.element === "string") {
        return !!document.querySelector(s.element);
      }
      return true;
    });

    if (validSteps.length === 0) return;

    const driverObj = driver({
      showProgress: true,
      animate: true,
      allowClose: true,
      overlayColor: "rgba(0, 0, 0, 0.75)",
      nextBtnText: "Next →",
      prevBtnText: "← Back",
      doneBtnText: "Finish Tour 🚀",
      steps: validSteps,
      onDestroyed: () => {
        if (typeof window !== "undefined") {
          localStorage.setItem("vouch_tour_completed", "true");
        }
      },
    });

    driverObj.drive();
  };

  useEffect(() => {
    setTourStarter(startGuidedTour);

    if (isAuthenticated() && typeof window !== "undefined") {
      const tourDone = localStorage.getItem("vouch_tour_completed");
      const isDashboard = window.location.pathname === "/" || window.location.pathname === "/dashboard";
      if (!tourDone && isDashboard) {
        const timer = setTimeout(() => {
          startGuidedTour();
        }, 1500);
        return () => clearTimeout(timer);
      }
    }
  }, [setTourStarter]);

  return null;
}
