"use client";

import React from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { BillingSettingsView } from "@/components/billing/BillingSettingsView";

export default function BillingSettingsPage() {
  return (
    <DashboardLayout>
      <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-black tracking-tight text-foreground">
            Subscription &amp; Billing Management
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage your workspace subscription plan, view daily OCR usage meters, and download official tax invoices.
          </p>
        </div>

        <BillingSettingsView />
      </div>
    </DashboardLayout>
  );
}
