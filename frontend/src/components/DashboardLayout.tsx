"use client";
import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useHotkeys } from "react-hotkeys-hook";
import { ThemeToggle } from "./ThemeToggle";
import { removeTokens } from "@/utils/auth";
import CommandPalette from "./CommandPalette";
import { VouchLogo } from "./VouchLogo";
import { useShortcuts } from "@/context/ShortcutContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { useAccountingPeriod } from "@/context/PeriodContext";
import { useCompany } from "@/context/CompanyContext";
import { useRole } from "@/hooks/useRole";
import {
  Calendar,
  Building2,
  Search,
  HelpCircle,
  ChevronDown,
  User,
  Settings,
  LogOut,
  Sparkles,
  FileText,
  BarChart3,
  CheckCircle2,
  Lock,
  Scissors,
  ArrowRight,
  Scale,
  ShieldCheck,
  ShieldAlert,
  Activity,
  Landmark,

  Check,
  Plus,
} from "lucide-react";
import SyncStatusBadge from "./SyncStatusBadge";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  // Dropdown states
  const [isSalesDropdownOpen, setIsSalesDropdownOpen] = useState(false);
  const [isMoreDropdownOpen, setIsMoreDropdownOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isFYDropdownOpen, setIsFYDropdownOpen] = useState(false);
  const [isCompanyDropdownOpen, setIsCompanyDropdownOpen] = useState(false);
  const [isGstDropdownOpen, setIsGstDropdownOpen] = useState(false);

  const salesRef = useRef<HTMLDivElement>(null);
  const gstRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fyRef = useRef<HTMLDivElement>(null);
  const companyRef = useRef<HTMLDivElement>(null);

  const { setIsHelpOpen, setIsDateOpen, workingDate, startTour } = useShortcuts();
  const { activeFY, availableFYs, setActiveFY, isReadOnly, setIsClosingModalOpen } = useFinancialYear();
  const { displayPeriod, setIsPeriodModalOpen, setIsSplitModalOpen } = useAccountingPeriod();
  const { activeCompany, availableCompanies, setActiveCompany } = useCompany();
  const { user, role, isAdmin, isOwner, isCA, isEmployee, isViewer, canManageSettings } = useRole();

  // Superadmin isolation: platform superadmin only sees the Superadmin Command Center, never company dashboards
  useEffect(() => {
    if (user?.is_superuser || user?.email?.trim().toLowerCase() === "prakharssa@gmail.com") {
      router.replace("/admin");
    }
  }, [user, router]);

  // Close dropdowns on route change
  useEffect(() => {
    setIsMobileNavOpen(false);
    setIsSalesDropdownOpen(false);
    setIsGstDropdownOpen(false);
    setIsMoreDropdownOpen(false);
    setIsUserMenuOpen(false);
    setIsFYDropdownOpen(false);
    setIsCompanyDropdownOpen(false);
  }, [pathname]);

  // Click away listener for dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (salesRef.current && !salesRef.current.contains(e.target as Node)) {
        setIsSalesDropdownOpen(false);
      }
      if (gstRef.current && !gstRef.current.contains(e.target as Node)) {
        setIsGstDropdownOpen(false);
      }
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setIsMoreDropdownOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
      if (fyRef.current && !fyRef.current.contains(e.target as Node)) {
        setIsFYDropdownOpen(false);
      }
      if (companyRef.current && !companyRef.current.contains(e.target as Node)) {
        setIsCompanyDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    removeTokens();
    router.push("/login");
  };

  useHotkeys(
    ["ctrl+k", "meta+k"],
    (e) => {
      e.preventDefault();
      setIsCommandPaletteOpen((prev) => !prev);
    },
    { enableOnFormTags: true }
  );

  const isSalesActive = pathname.startsWith("/sales");
  const isPurchasesActive = pathname.startsWith("/purchases");
  const isMoreActive =
    pathname.startsWith("/vouchers") ||
    pathname.startsWith("/network") ||
    pathname.startsWith("/export") ||
    pathname.startsWith("/reports") ||
    pathname.startsWith("/audit") ||
    pathname.startsWith("/health") ||
    pathname.startsWith("/ledgers") ||
    pathname.startsWith("/gst");

  return (
    <div className="min-h-screen bg-background font-sans text-foreground flex flex-col">
      {/* Global Command Palette (Ctrl+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />

      {/* TOP NAVIGATION BAR */}
      <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-card/90 backdrop-blur-xl shadow-2xs">
        <div className="w-full px-3 sm:px-4 lg:px-6 h-14 flex items-center justify-between gap-2 lg:gap-3">
          
          {/* Left Section: Brand & Primary Nav */}
          <div className="flex items-center gap-2 lg:gap-3 xl:gap-4 min-w-0">
            {/* Mobile / Tablet Hamburger Button */}
            <button
              onClick={() => setIsMobileNavOpen(true)}
              className="lg:hidden p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer shrink-0 min-h-[36px] min-w-[36px] flex items-center justify-center"
              aria-label="Open Navigation Menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            {/* Brand Logo */}
            <div id="tour-header-brand" className="flex items-center gap-1.5 shrink-0">
              <Link
                href="/dashboard"
                className="hover:opacity-90 flex items-center gap-1.5 shrink-0 transition-opacity"
              >
                <VouchLogo size={24} showWordmark={true} />
              </Link>
            </div>

            {/* Desktop Navigation Links */}
            <nav className="hidden lg:flex items-center gap-0.5 xl:gap-1 min-w-0">
              {/* Dashboard */}
              <Link
                id="tour-dashboard-link"
                href="/dashboard"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap ${
                  pathname === "/dashboard"
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                Dashboard
              </Link>

              {/* Sales Dropdown */}
              <div ref={salesRef} className="relative shrink-0">
                <button
                  id="tour-sales-btn"
                  onClick={() => {
                    setIsSalesDropdownOpen(!isSalesDropdownOpen);
                    setIsGstDropdownOpen(false);
                    setIsMoreDropdownOpen(false);
                  }}
                  className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all flex items-center gap-1 cursor-pointer whitespace-nowrap ${
                    isSalesActive
                      ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>Sales</span>
                  <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isSalesDropdownOpen ? "rotate-180" : ""}`} />
                </button>

                {isSalesDropdownOpen && (
                  <div className="absolute left-0 top-full mt-1.5 w-64 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95">
                    <Link
                      href="/sales"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsSalesDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium flex items-center gap-1.5 text-xs sm:text-sm">
                          <span>Sales Invoices (GST)</span>
                          <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.2 rounded font-mono font-semibold">F8</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Official GST tax invoices</div>
                      </div>
                    </Link>
                    <Link
                      href="/sales/proforma"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsSalesDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium text-blue-500 dark:text-blue-400 flex items-center gap-1.5 text-xs sm:text-sm">
                          <span>Proforma & Quotations</span>
                          <span className="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 px-1.5 py-0.2 rounded font-semibold">1-Click GST</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Estimates, quotes & proforma bills</div>
                      </div>
                    </Link>

                    <div className="border-t border-border/40 my-1.5"></div>

                    <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                      <Link
                        href="/sales/new"
                        className="flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                        onClick={() => setIsSalesDropdownOpen(false)}
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>+ Invoice</span>
                      </Link>
                      <Link
                        href="/sales/proforma/new"
                        className="flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 transition-colors"
                        onClick={() => setIsSalesDropdownOpen(false)}
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>+ Quotation</span>
                      </Link>
                    </div>
                  </div>
                )}
              </div>

              {/* Purchases */}
              <Link
                id="tour-purchase-btn"
                href="/purchases"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap ${
                  isPurchasesActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                Purchases
              </Link>

              {/* Parties */}
              <Link
                id="tour-parties-link"
                href="/parties"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap ${
                  pathname.startsWith("/parties")
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                Parties
              </Link>

              {/* Inventory */}
              <Link
                id="tour-inventory-link"
                href="/inventory"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap ${
                  pathname.startsWith("/inventory")
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                Inventory
              </Link>

              {/* Banking */}
              <Link
                id="tour-banking-link"
                href="/banking"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap ${
                  pathname.startsWith("/banking")
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                Banking
              </Link>

              {/* Analytics Hub */}
              <Link
                id="tour-analytics-link"
                href="/analytics"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all whitespace-nowrap flex items-center gap-1.5 ${
                  pathname.startsWith("/analytics")
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                <span>Analytics</span>
                <span className="text-[9px] bg-purple-500/15 text-purple-600 dark:text-purple-400 font-bold px-1.5 py-0.2 rounded-full">
                  AI
                </span>
              </Link>

              {/* GST & Tax Dropdown (visible on wide screens >= 1280px, otherwise gracefully tucked in More) */}
              <div ref={gstRef} className="relative shrink-0 hidden xl:block">
                <button
                  id="tour-gst-btn"
                  onClick={() => {
                    setIsGstDropdownOpen(!isGstDropdownOpen);
                    setIsSalesDropdownOpen(false);
                    setIsMoreDropdownOpen(false);
                  }}
                  className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                    pathname.startsWith("/gst")
                      ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>GST & Tax</span>
                  <span className="text-[9px] bg-rose-500/15 text-rose-600 dark:text-rose-400 font-bold px-1.5 py-0.2 rounded-full">
                    Shield
                  </span>
                  <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isGstDropdownOpen ? "rotate-180" : ""}`} />
                </button>

                {isGstDropdownOpen && (
                  <div className="absolute left-0 top-full mt-1.5 w-72 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95">
                    <Link
                      href="/gst/itc-shield"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsGstDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-semibold text-rose-500 flex items-center gap-1.5 text-xs sm:text-sm">
                          <ShieldAlert className="w-3.5 h-3.5" />
                          <span>Vendor ITC Risk Shield</span>
                          <span className="text-[9px] bg-rose-500/20 text-rose-400 px-1 py-0.2 rounded font-bold">New</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">GSTR-2B match, payment hold & WhatsApp chaser</div>
                      </div>
                    </Link>

                    <Link
                      href="/gst/returns"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsGstDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium flex items-center gap-1.5 text-xs sm:text-sm">
                          <FileText className="w-3.5 h-3.5 text-primary" />
                          <span>GST Returns Center</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">GSTR-1, GSTR-3B tax summary & GSTR-9</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>

              {/* More Dropdown */}
              <div ref={moreRef} className="relative shrink-0">
                <button
                  onClick={() => {
                    setIsMoreDropdownOpen(!isMoreDropdownOpen);
                    setIsSalesDropdownOpen(false);
                    setIsGstDropdownOpen(false);
                  }}
                  className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs xl:text-[13px] font-medium transition-all flex items-center gap-1 cursor-pointer whitespace-nowrap ${
                    isMoreActive
                      ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>More</span>
                  <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isMoreDropdownOpen ? "rotate-180" : ""}`} />
                </button>

                {isMoreDropdownOpen && (
                  <div className="absolute right-0 top-full mt-1.5 w-[580px] max-h-[85vh] overflow-y-auto bg-card/95 backdrop-blur-xl border border-border/40 rounded-2xl shadow-2xl shadow-black/20 p-4 z-50 animate-in fade-in zoom-in-95 grid grid-cols-3 gap-3 divide-x divide-border/30">
                    
                    {/* Col 1: Accounting & Entries */}
                    <div className="space-y-1">
                      <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                        Accounting & Entries
                      </div>
                      <Link
                        href="/vouchers"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Transactions</div>
                          <div className="text-[10px] text-muted-foreground">All posted vouchers</div>
                        </div>
                      </Link>
                      <Link
                        href="/vouchers/credit-note"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs text-amber-500">Credit / Debit Note</div>
                          <div className="text-[10px] text-muted-foreground">Sales & purchase returns</div>
                        </div>
                      </Link>
                      <Link
                        href="/vouchers/new"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Payments & Receipts</div>
                          <div className="text-[10px] text-muted-foreground">Record money in/out</div>
                        </div>
                      </Link>
                      <Link
                        href="/vouchers/grid"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Journal Entry</div>
                          <div className="text-[10px] text-muted-foreground">Manual double-entry</div>
                        </div>
                      </Link>
                      <Link
                        href="/ledgers"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Chart of Accounts</div>
                          <div className="text-[10px] text-muted-foreground">Account heads & ledgers</div>
                        </div>
                      </Link>
                    </div>

                    {/* Col 2: Reports & Statements */}
                    <div className="pl-3 space-y-1">
                      <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                        Reports & Statements
                      </div>
                      <Link
                        href="/reports/trial-balance"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Trial Balance</div>
                          <div className="text-[10px] text-muted-foreground">Debit-Credit parity</div>
                        </div>
                      </Link>
                      <Link
                        href="/reports/profit-and-loss"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Profit & Loss</div>
                          <div className="text-[10px] text-muted-foreground">Trading & net margin</div>
                        </div>
                      </Link>
                      <Link
                        href="/reports/balance-sheet"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Balance Sheet</div>
                          <div className="text-[10px] text-muted-foreground">Assets & liabilities</div>
                        </div>
                      </Link>
                      <Link
                        href="/reports/aging"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs text-purple-500">Aging MSME</div>
                          <div className="text-[10px] text-muted-foreground">45-day overdue tracker</div>
                        </div>
                      </Link>
                      <Link
                        href="/export/tally"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Export to Tally</div>
                          <div className="text-[10px] text-muted-foreground">TallyPrime XML sync</div>
                        </div>
                      </Link>
                    </div>

                    {/* Col 3: GST, Tools & Compliance */}
                    <div className="pl-3 space-y-1">
                      <div className="px-2 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                        GST & Operations
                      </div>
                      <Link
                        href="/gst/itc-shield"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs text-rose-500 flex items-center gap-1">
                            <span>ITC Risk Shield</span>
                            <span className="text-[8px] bg-rose-500/20 text-rose-400 px-1 py-0.2 rounded font-bold">New</span>
                          </div>
                          <div className="text-[10px] text-muted-foreground">2B reconcile & WhatsApp</div>
                        </div>
                      </Link>
                      <Link
                        href="/gst/returns"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">GST Returns</div>
                          <div className="text-[10px] text-muted-foreground">GSTR-1, 3B, 9 filing</div>
                        </div>
                      </Link>
                      <Link
                        href="/health"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Books Health</div>
                          <div className="text-[10px] text-muted-foreground">Automated ledger audit</div>
                        </div>
                      </Link>
                      <Link
                        href="/audit"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">Activity Audit</div>
                          <div className="text-[10px] text-muted-foreground">Tamper-evident logs</div>
                        </div>
                      </Link>
                      <Link
                        href="/network/inbox"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                        onClick={() => setIsMoreDropdownOpen(false)}
                      >
                        <div>
                          <div className="font-semibold text-xs">B2B Network</div>
                          <div className="text-[10px] text-muted-foreground">Supplier e-invoices</div>
                        </div>
                      </Link>
                      {(isAdmin || isOwner || isCA) && (
                        <button
                          onClick={() => {
                            setIsMoreDropdownOpen(false);
                            setIsClosingModalOpen(true);
                          }}
                          className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors flex items-center justify-between cursor-pointer"
                        >
                          <div>
                            <div className="font-semibold text-xs">Close FY</div>
                            <div className="text-[10px] text-muted-foreground">Year-end balance transfer</div>
                          </div>
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </nav>
          </div>

          {/* Right Section: Workspace Context, Quick Search & Utilities */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            
            {/* Company Switcher Pill */}
            <div ref={companyRef} className="relative hidden md:block">
              <button
                onClick={() => {
                  setIsCompanyDropdownOpen(!isCompanyDropdownOpen);
                  setIsFYDropdownOpen(false);
                  setIsUserMenuOpen(false);
                }}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs transition-all cursor-pointer shadow-2xs min-h-[36px]"
                title={`Active Company: ${activeCompany?.name || 'Company'}`}
              >
                <div className="w-5 h-5 rounded-md bg-gradient-to-br from-primary/20 to-primary/10 border border-primary/25 flex items-center justify-center text-[10px] font-bold text-primary shrink-0 uppercase">
                  {(activeCompany?.name || "C")[0]}
                </div>
                <span className="font-semibold text-xs text-foreground truncate max-w-[90px] lg:max-w-[110px] xl:max-w-[150px]">
                  {activeCompany?.name || "Company"}
                </span>
                <ChevronDown className={`w-3 h-3 text-muted-foreground/70 shrink-0 transition-transform duration-150 ${isCompanyDropdownOpen ? "rotate-180" : ""}`} />
              </button>

              {isCompanyDropdownOpen && (
                <div className="absolute right-0 mt-1.5 w-64 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-1.5 z-50 animate-in fade-in zoom-in-95">
                  <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    Switch Company Workspace
                  </div>
                  {availableCompanies.length === 0 ? (
                    <div className="px-2 py-1.5 text-xs text-muted-foreground">No companies found</div>
                  ) : (
                    <div className="space-y-0.5 max-h-56 overflow-y-auto">
                      {availableCompanies.map((comp) => (
                        <button
                          key={comp.id}
                          onClick={() => {
                            setActiveCompany(comp);
                            setIsCompanyDropdownOpen(false);
                            window.location.reload();
                          }}
                          className={`w-full text-left px-2.5 py-2 rounded-lg text-xs transition-colors flex items-center justify-between cursor-pointer ${
                            activeCompany?.id === comp.id
                              ? "bg-primary/10 text-primary font-semibold"
                              : "text-foreground hover:bg-muted"
                          }`}
                        >
                          <div className="flex items-center gap-2 truncate">
                            <div className="w-5 h-5 rounded-md bg-muted flex items-center justify-center text-[10px] font-bold shrink-0 uppercase">
                              {comp.name[0]}
                            </div>
                            <span className="truncate">{comp.name}</span>
                          </div>
                          {activeCompany?.id === comp.id && (
                            <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0 ml-1" />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="border-t border-border/40 my-1"></div>
                  <Link
                    href="/settings"
                    onClick={() => setIsCompanyDropdownOpen(false)}
                    className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    <span>Company Settings</span>
                  </Link>
                </div>
              )}
            </div>

            {/* Financial Year & Period Switcher */}
            <div ref={fyRef} className="relative hidden md:block">
              <button
                onClick={() => setIsFYDropdownOpen(!isFYDropdownOpen)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs transition-all cursor-pointer shadow-2xs min-h-[36px]"
                title="Change Financial Year or Period (Alt + F2)"
              >
                <Calendar className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="font-mono tabular-nums text-xs font-semibold text-foreground whitespace-nowrap">
                  {activeFY ? (activeFY.code || activeFY.name) : "FY 26-27"}
                </span>
                <span className={`w-2 h-2 rounded-full shrink-0 ${activeFY?.is_closed ? "bg-amber-400" : "bg-emerald-500"}`} />
                <ChevronDown className="w-3 h-3 text-muted-foreground/70 shrink-0" />
              </button>

              {isFYDropdownOpen && (
                <div className="absolute right-0 mt-1.5 w-64 rounded-xl border border-border bg-card/95 backdrop-blur-md shadow-xl p-1.5 z-50 text-xs animate-in fade-in zoom-in-95">
                  <div className="px-2.5 py-1.5 text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                    <span>Financial Years</span>
                    <span className="text-[9px] font-mono text-muted-foreground/80">Active FY Only</span>
                  </div>
                  <div className="space-y-0.5 max-h-56 overflow-y-auto">
                    {availableFYs.map((fy) => {
                      const isSelected = activeFY?.id === fy.id;
                      return (
                        <button
                          key={fy.id}
                          onClick={() => {
                            setActiveFY(fy);
                            setIsFYDropdownOpen(false);
                          }}
                          className={`w-full text-left px-2.5 py-2 rounded-lg flex items-center justify-between transition-colors cursor-pointer ${
                            isSelected
                              ? "bg-primary/15 text-primary font-semibold"
                              : "hover:bg-muted text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <div className="flex flex-col">
                            <span className="font-medium text-xs text-foreground flex items-center gap-1.5">
                              {fy.name || `FY ${fy.code}`}
                              {fy.is_closed && (
                                <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-400 font-normal">Closed</span>
                              )}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground">
                              {fy.start_date} → {fy.end_date}
                            </span>
                          </div>
                          {isSelected && <Check className="w-3.5 h-3.5 text-primary shrink-0" />}
                        </button>
                      );
                    })}
                  </div>
                  <div className="border-t border-border mt-1 pt-1 flex flex-col gap-0.5">
                    <button
                      onClick={() => {
                        setIsFYDropdownOpen(false);
                        setIsPeriodModalOpen(true);
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-between cursor-pointer"
                    >
                      <span className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>Custom Period Range</span>
                      </span>
                      <kbd className="font-mono text-[10px] px-1 py-0.2 bg-muted text-muted-foreground rounded border border-border">Alt+F2</kbd>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Quick Command Palette Search (Ctrl+K) */}
            <button
              id="tour-command-palette-btn"
              onClick={() => setIsCommandPaletteOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-border/50 bg-muted/20 hover:bg-muted/60 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs min-h-[36px]"
              title="Quick Search & Navigation (Ctrl+K)"
            >
              <Search className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="hidden xl:inline text-xs font-medium">Search</span>
              <kbd className="hidden sm:inline-block text-[10px] font-mono bg-muted/80 px-1.5 py-0.2 rounded border border-border/60 text-muted-foreground">
                Ctrl+K
              </kbd>
            </button>

            {/* Help Icon Button (F1) */}
            <button
              id="tour-help-btn"
              onClick={() => setIsHelpOpen(true)}
              className="hidden xl:inline-flex p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted/60 transition-colors cursor-pointer min-h-[36px] min-w-[36px] items-center justify-center"
              title="Keyboard Shortcuts & Help (F1)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            {/* Theme Toggle */}
            <ThemeToggle />

            {/* User Avatar Dropdown */}
            <div ref={userMenuRef} className="relative">
              <button
                onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 via-primary/10 to-accent/20 border border-border/60 flex items-center justify-center text-xs font-bold text-foreground hover:ring-2 hover:ring-primary/30 transition-all cursor-pointer"
                title="Account Menu"
              >
                {user?.first_name ? user.first_name[0].toUpperCase() : <User className="w-4 h-4 text-muted-foreground" />}
              </button>

              {isUserMenuOpen && (
                <div className="absolute right-0 mt-1.5 w-60 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95">
                  <div className="px-3 py-2 border-b border-border/40 mb-1.5">
                    <div className="text-xs font-bold text-foreground truncate">
                      {user?.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : (user?.email || activeCompany?.name || "User")}
                    </div>
                    <div className="text-[11px] text-muted-foreground font-mono truncate">{user?.email}</div>
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                      <span className={`px-1.5 py-0.5 text-[9px] font-mono font-bold rounded uppercase border ${
                        role === 'ADMIN'
                          ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                          : role === 'OWNER'
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          : role === 'CA'
                          ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                          : role === 'EMPLOYEE'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-zinc-500/10 text-zinc-400 border-zinc-500/30'
                      }`}>
                        {role}
                      </span>
                    </div>
                  </div>
                  {canManageSettings && (
                    <Link
                      id="tour-settings-link"
                      href="/settings"
                      onClick={() => setIsUserMenuOpen(false)}
                      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                    >
                      <Settings className="w-3.5 h-3.5 text-muted-foreground" />
                      <span>Settings</span>
                    </Link>
                  )}
                  <button
                    onClick={() => {
                      setIsUserMenuOpen(false);
                      startTour();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors cursor-pointer"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                    <span>Guided Tour</span>
                  </button>
                  <div className="border-t border-border/40 my-1"></div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-rose-500 hover:bg-rose-500/10 transition-colors cursor-pointer"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Logout</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Read-Only Mode Banner for Closed Financial Year */}
      {isReadOnly && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 text-xs font-medium text-amber-400 flex items-center justify-between">
          <div className="flex items-center gap-2 max-w-[1600px] mx-auto w-full">
            <Lock className="w-3.5 h-3.5 shrink-0" />
            <span>
              Viewing Closed Financial Year (<strong>{activeFY?.code}</strong>). Transactions in this period are in read-only audit mode.
            </span>
          </div>
        </div>
      )}

      {/* Mobile Navigation Drawer */}
      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <aside className="relative w-72 max-w-[80vw] bg-card/95 backdrop-blur-xl border-r border-border/40 h-full flex flex-col p-5 shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <div className="flex items-center gap-2">
                <VouchLogo size={24} showWordmark={true} />
              </div>
              <button
                onClick={() => setIsMobileNavOpen(false)}
                className="text-muted-foreground hover:text-foreground p-2 rounded-lg min-h-[36px] min-w-[36px] flex items-center justify-center cursor-pointer"
                aria-label="Close Navigation Menu"
              >
                ✕
              </button>
            </div>

            {/* Mobile Company Selector */}
            {availableCompanies.length > 1 && (
              <div className="py-2 border-b border-border/50">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                  Company
                </label>
                <select
                  value={activeCompany?.id || ""}
                  onChange={(e) => {
                    const found = availableCompanies.find(c => c.id === e.target.value);
                    if (found) {
                      setActiveCompany(found);
                      window.location.reload();
                    }
                  }}
                  className="w-full bg-muted border border-border/60 rounded-lg px-2.5 py-1.5 text-xs text-foreground font-medium"
                >
                  {availableCompanies.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Mobile Financial Year Selector */}
            {availableFYs.length > 0 && (
              <div className="py-2 border-b border-border/50">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                  Financial Year
                </label>
                <select
                  value={activeFY?.id || ""}
                  onChange={(e) => {
                    const found = availableFYs.find(f => f.id === e.target.value);
                    if (found) {
                      setActiveFY(found);
                    }
                  }}
                  className="w-full bg-muted border border-border/60 rounded-lg px-2.5 py-1.5 text-xs text-foreground font-medium"
                >
                  {availableFYs.map(f => (
                    <option key={f.id} value={f.id}>
                      {f.name || `FY ${f.code}`}{f.is_closed ? " (Closed)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Mobile Context Pill */}
            <div className="py-3 flex items-center justify-between text-xs border-b border-border/50 gap-2">
              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  setIsPeriodModalOpen(true);
                }}
                className="flex items-center gap-2 px-3 py-2 bg-muted text-foreground rounded-lg border border-border/60 font-mono tabular-nums text-xs min-h-[36px]"
              >
                <Calendar className="w-4 h-4 text-muted-foreground" />
                <span>{activeFY?.code || "FY 26-27"} · {workingDate}</span>
              </button>

              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  setIsHelpOpen(true);
                }}
                className="px-3 py-2 bg-muted/60 text-muted-foreground rounded-lg border border-border/50 text-xs font-semibold min-h-[36px]"
              >
                Help (F1)
              </button>
            </div>

            {/* Mobile Nav Links */}
            <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
              <Link
                href="/dashboard"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname === "/dashboard" ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Dashboard
              </Link>
              <div className="space-y-0.5">
                <div className="px-3 pt-2 pb-1 text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                  Sales
                </div>
                <Link
                  href="/sales"
                  onClick={() => setIsMobileNavOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                    pathname === "/sales" || (pathname.startsWith("/sales") && !pathname.startsWith("/sales/proforma"))
                      ? "bg-muted font-semibold text-foreground"
                      : "text-muted-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>Sales Invoices (GST)</span>
                  <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-mono font-semibold">F8</span>
                </Link>
                <Link
                  href="/sales/proforma"
                  onClick={() => setIsMobileNavOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                    pathname.startsWith("/sales/proforma") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                  }`}
                >
                  <span className="text-blue-500 dark:text-blue-400 font-medium">Proforma & Quotations</span>
                  <span className="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded font-semibold">1-Click GST</span>
                </Link>
              </div>
              <Link
                href="/purchases"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/purchases") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Purchases</span>
              </Link>
              <Link
                href="/parties"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/parties") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Parties
              </Link>
              <Link
                href="/inventory"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/inventory") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Inventory
              </Link>
              <Link
                href="/banking"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/banking") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Banking
              </Link>
              <Link
                href="/analytics"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/analytics") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Analytics & Forecasting</span>
                <span className="text-[9px] bg-purple-500/10 text-purple-400 font-bold px-1.5 py-0.5 rounded">AI</span>
              </Link>
              
              <div className="space-y-0.5 pt-1">
                <div className="px-3 pt-2 pb-1 text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                  GST & Compliance
                </div>
                <Link
                  href="/gst/itc-shield"
                  onClick={() => setIsMobileNavOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                    pathname.startsWith("/gst/itc-shield")
                      ? "bg-muted font-semibold text-rose-500"
                      : "text-muted-foreground hover:bg-muted/60"
                  }`}
                >
                  <span className="font-semibold text-rose-500 flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    <span>Vendor ITC Risk Shield</span>
                  </span>
                  <span className="text-[9px] bg-rose-500/20 text-rose-400 px-1 py-0.2 rounded font-bold">New</span>
                </Link>
                <Link
                  href="/gst/returns"
                  onClick={() => setIsMobileNavOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                    pathname.startsWith("/gst/returns")
                      ? "bg-muted font-semibold text-foreground"
                      : "text-muted-foreground hover:bg-muted/60"
                  }`}
                >
                  <span>GST Returns Center</span>
                </Link>
              </div>

              <div className="border-t border-border/40 my-2"></div>

              
              <Link
                href="/vouchers"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/vouchers") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Transactions
              </Link>
              <Link
                href="/ledgers"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/ledgers") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Accounts
              </Link>
              <Link
                href="/health"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/health") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Books Health</span>
              </Link>
              <Link
                href="/export/tally"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/export") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Export to Tally</span>
              </Link>
              <Link
                href="/reports/trial-balance"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/reports/trial-balance") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Trial Balance</span>
              </Link>
              <Link
                href="/reports/profit-and-loss"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/reports/profit-and-loss") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Profit & Loss</span>
              </Link>
              <Link
                href="/reports/balance-sheet"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/reports/balance-sheet") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Balance Sheet</span>
              </Link>
              <Link
                href="/audit"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/audit") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Activity Log</span>
              </Link>
              <Link
                href="/settings"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname === "/settings" ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                Settings
              </Link>
            </nav>

            <div className="pt-4 border-t border-border flex items-center justify-between">
              <button
                onClick={handleLogout}
                className="text-sm font-semibold text-rose-500 hover:text-rose-400"
              >
                Logout
              </button>
              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  startTour();
                }}
                className="text-xs text-blue-500 hover:underline"
              >
                Guided Tour
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 overflow-auto">
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
