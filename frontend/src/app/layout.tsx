import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ShortcutProvider } from "@/context/ShortcutContext";
import DateModal from "@/components/modals/DateModal";
import HelpModal from "@/components/modals/HelpModal";
import QuickCreateModal from "@/components/modals/QuickCreateModal";
import OnboardingTour from "@/components/tour/OnboardingTour";
import PWAInstallPrompt from "@/components/PWAInstallPrompt";
import OfflineSyncHandler from "@/components/OfflineSyncHandler";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export const metadata: Metadata = {
  title: "Vouch - Double-Entry Accounting & AI ERP",
  description: "Keyboard-first cloud ERP and accounting platform with automated GST compliance and AI bill extraction.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Vouch",
  },
};

import { FinancialYearProvider } from "@/context/FinancialYearContext";
import { PeriodProvider } from "@/context/PeriodContext";
import YearEndClosingModal from "@/components/modals/YearEndClosingModal";
import PeriodModal from "@/components/modals/PeriodModal";
import SplitCompanyModal from "@/components/modals/SplitCompanyModal";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen bg-background text-foreground`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <FinancialYearProvider>
            <PeriodProvider>
              <ShortcutProvider>
                {children}
                <DateModal />
                <PeriodModal />
                <SplitCompanyModal />
                <HelpModal />
                <QuickCreateModal />
                <YearEndClosingModal />
                <OnboardingTour />
                <PWAInstallPrompt />
                <OfflineSyncHandler />
              </ShortcutProvider>
            </PeriodProvider>
          </FinancialYearProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
