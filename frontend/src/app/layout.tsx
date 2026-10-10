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
import ExtensionErrorSuppressor from "@/components/ExtensionErrorSuppressor";
import { ToastProvider } from "@/context/ToastContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  metadataBase: new URL("https://srilekh.com"),
  title: {
    default: "SriLekh - Double-Entry Accounting & AI ERP",
    template: "%s | SriLekh",
  },
  description: "Keyboard-first cloud ERP and accounting platform with automated GST compliance and AI bill extraction.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.ico?v=srilekh-v3",
    shortcut: "/favicon.ico?v=srilekh-v3",
    apple: "/icons/srilekh-apple-touch.png?v=srilekh-v3",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "SriLekh",
  },
  openGraph: {
    type: "website",
    locale: "en_IN",
    url: "https://srilekh.com",
    siteName: "SriLekh Accounting",
    title: "SriLekh - Double-Entry Accounting & AI ERP",
    description: "Keyboard-first cloud ERP and accounting platform with automated GST compliance and AI bill extraction.",
  },
  twitter: {
    card: "summary_large_image",
    title: "SriLekh - Double-Entry Accounting & AI ERP",
    description: "Keyboard-first cloud ERP and accounting platform with automated GST compliance and AI bill extraction.",
  },
};

import { CompanyProvider } from "@/context/CompanyContext";
import { FinancialYearProvider } from "@/context/FinancialYearContext";
import { PeriodProvider } from "@/context/PeriodContext";
import YearEndClosingModal from "@/components/modals/YearEndClosingModal";
import PeriodModal from "@/components/modals/PeriodModal";
import SplitCompanyModal from "@/components/modals/SplitCompanyModal";
import TallyCalculator from "@/components/accounting/TallyCalculator";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen bg-background text-foreground`} suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <CompanyProvider>
            <FinancialYearProvider>
              <PeriodProvider>
                <ShortcutProvider>
                  <ToastProvider>
                  {children}
                  <DateModal />
                  <PeriodModal />
                  <SplitCompanyModal />
                  <HelpModal />
                  <QuickCreateModal />
                  <YearEndClosingModal />
                  <TallyCalculator />
                  <OnboardingTour />
                  <PWAInstallPrompt />
                  <OfflineSyncHandler />
                  <ExtensionErrorSuppressor />
                </ToastProvider>
              </ShortcutProvider>
            </PeriodProvider>
          </FinancialYearProvider>
        </CompanyProvider>
      </ThemeProvider>
      </body>
    </html>
  );
}
