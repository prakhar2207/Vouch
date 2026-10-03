"use client";
import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useHotkeys } from "react-hotkeys-hook";
import { ThemeToggle } from "./ThemeToggle";
import { NotificationBell } from "./NotificationBell";
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
  FilePlus,
  BarChart3,
  CheckCircle2,
  Lock,
  Scissors,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  Activity,
  Landmark,
  Check,
  Plus,
  Calculator,
  Receipt,
  ShoppingCart,
  TrendingUp,
  Boxes,
  Users,
  AlertTriangle,
  FolderKanban,
  Sliders,
  X,
} from "lucide-react";
import SyncStatusBadge from "./SyncStatusBadge";
import UniversalNewModal from "./UniversalNewModal";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isUniversalNewOpen, setIsUniversalNewOpen] = useState(false);

  // Simplified Navigation Dropdown States: Reports and More
  const [isReportsOpen, setIsReportsOpen] = useState(false);
  const [isMoreOpen, setIsMoreOpen] = useState(false);

  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isFYDropdownOpen, setIsFYDropdownOpen] = useState(false);
  const [isCompanyDropdownOpen, setIsCompanyDropdownOpen] = useState(false);

  const reportsRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fyRef = useRef<HTMLDivElement>(null);
  const companyRef = useRef<HTMLDivElement>(null);

  const { setIsHelpOpen, setIsDateOpen, workingDate, startTour, isCalculatorOpen, setIsCalculatorOpen } = useShortcuts();
  const { activeFY, availableFYs, setActiveFY, isReadOnly, setIsClosingModalOpen } = useFinancialYear();
  const { displayPeriod, setIsPeriodModalOpen, setIsSplitModalOpen } = useAccountingPeriod();
  const { activeCompany, availableCompanies, setActiveCompany } = useCompany();
  const { user, role, isAdmin, isOwner, isCA, isEmployee, isViewer, canManageSettings } = useRole();

  // Superadmin isolation: platform superadmin only sees the Superadmin Command Center, never company dashboards
  useEffect(() => {
    if (user?.is_superuser) {
      router.replace("/admin");
    }
  }, [user, router]);

  // Close dropdowns on route change
  useEffect(() => {
    setIsMobileNavOpen(false);
    setIsReportsOpen(false);
    setIsMoreOpen(false);
    setIsUserMenuOpen(false);
    setIsFYDropdownOpen(false);
    setIsCompanyDropdownOpen(false);
  }, [pathname]);

  // Click away and Escape key listeners for dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (reportsRef.current && !reportsRef.current.contains(target)) setIsReportsOpen(false);
      if (moreRef.current && !moreRef.current.contains(target)) setIsMoreOpen(false);
      if (userMenuRef.current && !userMenuRef.current.contains(target)) setIsUserMenuOpen(false);
      if (fyRef.current && !fyRef.current.contains(target)) setIsFYDropdownOpen(false);
      if (companyRef.current && !companyRef.current.contains(target)) setIsCompanyDropdownOpen(false);
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsReportsOpen(false);
        setIsMoreOpen(false);
        setIsUserMenuOpen(false);
        setIsFYDropdownOpen(false);
        setIsCompanyDropdownOpen(false);
        setIsMobileNavOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
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

  useHotkeys(
    ["c", "n"],
    (e) => {
      e.preventDefault();
      setIsUniversalNewOpen(true);
    },
    { enableOnFormTags: false }
  );


  const isSalesActive = pathname.startsWith("/sales") && !pathname.startsWith("/sales/proforma");
  const isPurchasesActive = pathname.startsWith("/purchases");
  const isCashBankActive =
    (pathname.startsWith("/vouchers") && !pathname.startsWith("/vouchers/grid") && !pathname.startsWith("/vouchers/credit-note")) ||
    pathname === "/voucher";
  const isInventoryActive = pathname.startsWith("/inventory");
  const isPartiesActive = pathname.startsWith("/parties");
  const isReportsActive =
    pathname.startsWith("/reports") ||
    pathname.startsWith("/analytics");
  const isMoreActive =
    pathname.startsWith("/gst") ||
    pathname.startsWith("/banking") ||
    pathname.startsWith("/ledgers") ||
    pathname.startsWith("/health") ||
    pathname.startsWith("/audit") ||
    pathname.startsWith("/export") ||
    pathname.startsWith("/network") ||
    pathname.startsWith("/vouchers/grid") ||
    pathname.startsWith("/vouchers/credit-note") ||
    pathname.startsWith("/sales/proforma");

  return (
    <div className="min-h-screen bg-background font-sans text-foreground flex flex-col overflow-x-hidden max-w-full">
      {/* Global Command Palette (Ctrl+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />

      {/* Skip to Main Content Link for Keyboard Accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-white focus:rounded-md focus:shadow-lg focus:outline-none"
      >
        Skip to main content
      </a>

      {/* TOP NAVIGATION BAR */}
      <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-card/90 backdrop-blur-xl shadow-2xs print:hidden overflow-x-clip">
        <div className="w-full max-w-[100vw] px-2.5 sm:px-3.5 xl:px-4 2xl:px-5 h-14 flex items-center justify-between gap-1 sm:gap-1.5 min-w-0">
          
          {/* Left Section: Brand & Primary Nav */}
          <div className="flex items-center gap-1 xl:gap-1.5 2xl:gap-2 min-w-0">
            {/* Brand Logo */}
            <div id="tour-header-brand" className="flex items-center gap-1.5 shrink-0">
              <Link
                href="/dashboard"
                className="hover:opacity-90 flex items-center gap-1.5 shrink-0 transition-opacity"
              >
                <VouchLogo size={24} showWordmark={true} />
              </Link>
            </div>

            {/* Desktop Navigation Links — Important Direct Links + Dropdowns for Reports & More */}
            <nav className="hidden lg:flex items-center gap-0.5 xl:gap-1">
              {/* 1. SALES */}
              <Link
                id="tour-sales-nav"
                href="/sales"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                  isSalesActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium"
                }`}
                title="Sales Invoices & Billing (F8)"
              >
                <Receipt className="w-3.5 h-3.5" />
                <span>Sales</span>
              </Link>

              {/* 2. PURCHASES */}
              <Link
                id="tour-purchases-nav"
                href="/purchases"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                  isPurchasesActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium"
                }`}
                title="Purchases & Vendor Bills (F9)"
              >
                <ShoppingCart className="w-3.5 h-3.5" />
                <span>Purchases</span>
              </Link>

              {/* 3. CASH & BANK */}
              <Link
                id="tour-banking-nav"
                href="/vouchers"
                className={`px-2 xl:px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                  isCashBankActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium"
                }`}
                title="Cash & Bank Payments / Receipts (F5/F6)"
              >
                <Landmark className="w-3.5 h-3.5" />
                <span>Cash & Bank</span>
              </Link>

              {/* 4. INVENTORY (Visible on XL+, accessible in More dropdown on smaller screens) */}
              <Link
                id="tour-inventory-nav"
                href="/inventory"
                className={`hidden xl:flex px-2 xl:px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] transition-all items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                  isInventoryActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium"
                }`}
                title="Stock, Products & Warehouse"
              >
                <Boxes className="w-3.5 h-3.5" />
                <span>Inventory</span>
              </Link>

              {/* 5. PARTIES (Visible on 2XL+, accessible in More dropdown on smaller screens) */}
              <Link
                id="tour-parties-nav"
                href="/parties"
                className={`hidden 2xl:flex px-2 xl:px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] transition-all items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                  isPartiesActive
                    ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60 font-medium"
                }`}
                title="Customer & Supplier Contacts"
              >
                <Users className="w-3.5 h-3.5" />
                <span>Parties</span>
              </Link>

              {/* 6. REPORTS DROPDOWN */}
              <div ref={reportsRef} className="relative shrink-0">
                <button
                  id="tour-reports-btn"
                  onClick={() => {
                    setIsReportsOpen(!isReportsOpen);
                    setIsMoreOpen(false);
                  }}
                  aria-haspopup="menu"
                  aria-expanded={isReportsOpen}
                  aria-controls="reports-dropdown-menu"
                  className={`px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] font-medium transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                    isReportsActive
                      ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>Reports</span>
                  <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isReportsOpen ? "rotate-180" : ""}`} />
                </button>

                {isReportsOpen && (
                  <div
                    id="reports-dropdown-menu"
                    role="menu"
                    aria-label="Financial Statements & Reports"
                    className="absolute left-0 top-full mt-1.5 w-72 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95 space-y-1"
                  >
                    <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                      Financial Statements & Reports
                    </div>
                    <Link
                      href="/reports/profit-and-loss"
                      role="menuitem"
                      onClick={() => setIsReportsOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-emerald-600 dark:text-emerald-400">Profit & Loss</div>
                        <div className="text-[11px] text-muted-foreground">Revenue, direct costs & net margin</div>
                      </div>
                    </Link>
                    <Link
                      href="/reports/balance-sheet"
                      role="menuitem"
                      onClick={() => setIsReportsOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Balance Sheet</div>
                        <div className="text-[11px] text-muted-foreground">Assets, liabilities & capital</div>
                      </div>
                    </Link>
                    <Link
                      href="/reports/trial-balance"
                      role="menuitem"
                      onClick={() => setIsReportsOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Trial Balance</div>
                        <div className="text-[11px] text-muted-foreground">Debit-Credit equilibrium check</div>
                      </div>
                    </Link>
                    <Link
                      href="/reports/aging"
                      role="menuitem"
                      onClick={() => setIsReportsOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-purple-600 dark:text-purple-400">Aging & Overdues</div>
                        <div className="text-[11px] text-muted-foreground">45-day MSME collection tracker</div>
                      </div>
                    </Link>
                    <div className="border-t border-border/40 my-1"></div>
                    <Link
                      href="/analytics"
                      role="menuitem"
                      onClick={() => setIsReportsOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-purple-600 dark:text-purple-400 flex items-center gap-1.5">
                          <span>AI Analytics Hub</span>
                          <span className="text-[9px] bg-purple-500/15 px-1 rounded font-bold">AI</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">Sales forecast & customer clusters</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>

              {/* 7. MORE DROPDOWN */}
              <div ref={moreRef} className="relative shrink-0">
                <button
                  id="tour-more-btn"
                  onClick={() => {
                    setIsMoreOpen(!isMoreOpen);
                    setIsReportsOpen(false);
                  }}
                  aria-haspopup="menu"
                  aria-expanded={isMoreOpen}
                  aria-controls="more-dropdown-menu"
                  className={`px-2.5 py-1.5 rounded-lg text-xs 2xl:text-[13px] font-medium transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap ${
                    isMoreActive
                      ? "bg-primary/10 text-primary font-semibold border border-primary/20 shadow-2xs"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>More</span>
                  <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform duration-150 ${isMoreOpen ? "rotate-180" : ""}`} />
                </button>

                {isMoreOpen && (
                  <div
                    id="more-dropdown-menu"
                    role="menu"
                    aria-label="More Features"
                    className="absolute left-0 top-full mt-1.5 w-80 max-h-[82vh] overflow-y-auto bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95 space-y-1"
                  >
                    {/* Section 1: GST & Compliance */}
                    <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                      GST & Statutory
                    </div>
                    <Link
                      href="/gst/returns"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">GST Filing Center</div>
                        <div className="text-[11px] text-muted-foreground">GSTR-1 & 3B summary tables</div>
                      </div>
                    </Link>
                    <Link
                      href="/gst/itc-shield"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-rose-500 flex items-center gap-1.5">
                          <span>Vendor ITC Risk Shield</span>
                          <span className="text-[9px] bg-rose-500/15 px-1 rounded font-bold">2B</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">Catch missing 2B supplier invoices</div>
                      </div>
                    </Link>

                    {/* Section 2: Accounting & Ledgers */}
                    <div className="border-t border-border/40 my-1"></div>
                    <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                      Accounting & Ledgers
                    </div>
                    <Link
                      href="/ledgers"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Chart of Accounts</div>
                        <div className="text-[11px] text-muted-foreground">Account heads & ledger balances</div>
                      </div>
                    </Link>
                    <Link
                      href="/vouchers/grid"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground flex items-center gap-1.5">
                          <span>Journal & Voucher Grid</span>
                          <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.2 rounded font-mono font-semibold">F7</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">High-speed double-entry matrix</div>
                      </div>
                    </Link>
                    <Link
                      href="/banking"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-emerald-600 dark:text-emerald-400">Bank Reconciliation</div>
                        <div className="text-[11px] text-muted-foreground">Match statement feeds with vouchers</div>
                      </div>
                    </Link>
                    <Link
                      href="/vouchers/credit-note"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Credit & Debit Notes</div>
                        <div className="text-[11px] text-muted-foreground">Sales & purchase returns</div>
                      </div>
                    </Link>

                    {/* Section 3: Tools & Operations */}
                    <div className="border-t border-border/40 my-1"></div>
                    <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
                      Tools & Operations
                    </div>
                    <Link
                      href="/inventory"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Inventory & Stock</div>
                        <div className="text-[11px] text-muted-foreground">Products, categories & batch tracking</div>
                      </div>
                    </Link>
                    <Link
                      href="/parties"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Parties & Contacts</div>
                        <div className="text-[11px] text-muted-foreground">Customer & supplier directories</div>
                      </div>
                    </Link>
                    <Link
                      href="/sales/proforma"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-blue-500 dark:text-blue-400">Proformas & Estimates</div>
                        <div className="text-[11px] text-muted-foreground">Quotations & 1-click GST convert</div>
                      </div>
                    </Link>
                    <Link
                      href="/purchases/new?scan=1"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-purple-600 dark:text-purple-400 flex items-center gap-1.5">
                          <span>Smart Bill Scanner</span>
                          <span className="text-[9px] bg-purple-500/15 px-1 rounded font-bold">OCR</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">Scan photo/PDF into purchase bill</div>
                      </div>
                    </Link>
                    <Link
                      href="/health"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                          <span>Books Health Audit</span>
                          <span className="text-[9px] bg-amber-500/15 px-1 rounded font-bold">Audit</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">1-Click preview and fix imbalances</div>
                      </div>
                    </Link>
                    <Link
                      href="/export/tally"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Tally Migration & Export</div>
                        <div className="text-[11px] text-muted-foreground">TallyPrime XML bridge</div>
                      </div>
                    </Link>
                    <Link
                      href="/audit"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Activity Audit Trail</div>
                        <div className="text-[11px] text-muted-foreground">Tamper-evident system logs</div>
                      </div>
                    </Link>
                    <Link
                      href="/network/inbox"
                      onClick={() => setIsMoreOpen(false)}
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors"
                    >
                      <div>
                        <div className="font-semibold text-foreground">Direct Supplier Network</div>
                        <div className="text-[11px] text-muted-foreground">Paperless B2B e-invoices</div>
                      </div>
                    </Link>
                    {(isAdmin || isOwner || isCA) && (
                      <button
                        type="button"
                        onClick={() => {
                          setIsMoreOpen(false);
                          setIsClosingModalOpen(true);
                        }}
                        className="w-full text-left px-3 py-2 rounded-lg text-xs hover:bg-muted/70 transition-colors cursor-pointer"
                      >
                        <div className="font-semibold text-amber-600 dark:text-amber-400">Close Financial Year</div>
                        <div className="text-[11px] text-muted-foreground">Carry forward closing balances</div>
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* 8. Universal + NEW Button */}
              <button
                id="tour-universal-new-btn"
                type="button"
                onClick={() => setIsUniversalNewOpen(true)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl font-bold text-xs bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm shadow-emerald-600/25 transition-all cursor-pointer shrink-0 ml-1 active:scale-95"
                title="Create Invoice, Bill, Payment or Item (Shortcut: N or C)"
              >
                <Plus className="w-4 h-4 stroke-[2.5]" />
                <span>New</span>
              </button>
            </nav>
          </div>


          {/* Right Section: Workspace Context, Quick Search & Utilities */}
          <div className="flex items-center gap-1 sm:gap-1.5 shrink-0 ml-auto pr-0.5">
            {/* Company Switcher Pill */}
            <div ref={companyRef} className="relative hidden md:block shrink-0">
              <button
                onClick={() => {
                  setIsCompanyDropdownOpen(!isCompanyDropdownOpen);
                  setIsFYDropdownOpen(false);
                  setIsUserMenuOpen(false);
                }}
                aria-label={`Switch Company Workspace (Active: ${activeCompany?.name || 'Company'})`}
                aria-haspopup="true"
                aria-expanded={isCompanyDropdownOpen}
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-xl border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs transition-all cursor-pointer shadow-2xs min-h-[44px]"
                title={`Active Company: ${activeCompany?.name || 'Company'}`}
              >
                <div className="w-5 h-5 rounded-md bg-gradient-to-br from-primary/20 to-primary/10 border border-primary/25 flex items-center justify-center text-[10px] font-bold text-primary shrink-0 uppercase">
                  {(activeCompany?.name || "C")[0]}
                </div>
                <span className="font-semibold text-xs text-foreground truncate max-w-[70px] lg:max-w-[75px] xl:max-w-[90px] 2xl:max-w-[110px]">
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
            <div ref={fyRef} className="relative hidden md:block shrink-0">
              <button
                onClick={() => setIsFYDropdownOpen(!isFYDropdownOpen)}
                aria-label={`Financial Year (${activeFY ? (activeFY.code || activeFY.name) : "FY 26-27"})`}
                aria-haspopup="true"
                aria-expanded={isFYDropdownOpen}
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-xl border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs transition-all cursor-pointer shadow-2xs min-h-[44px]"
                title="Change Financial Year or Period (Alt + F2)"
              >
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
                                <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-800 dark:text-amber-300 font-normal">Closed</span>
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
              className="flex items-center justify-center p-2 rounded-xl border border-border/50 bg-muted/20 hover:bg-muted/60 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs min-h-[44px] min-w-[44px] shrink-0"
              title="Quick Search & Navigation (Ctrl+K)"
              aria-label="Quick Search"
            >
              <Search className="w-4 h-4 text-muted-foreground shrink-0" />
            </button>

            {/* Tally Calculator Quick Access (Alt+N or Ctrl+N) */}
            <button
              id="tour-calculator-btn"
              onClick={() => setIsCalculatorOpen(!isCalculatorOpen)}
              aria-label="Tally Calculator & GST Tools"
              aria-expanded={isCalculatorOpen}
              className={`p-2 rounded-xl transition-all cursor-pointer min-h-[44px] min-w-[44px] hidden sm:flex items-center justify-center shrink-0 ${
                isCalculatorOpen
                  ? "bg-primary/20 text-primary border border-primary/40 shadow-xs"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              }`}
              title="Tally Calculator (Alt+N or Ctrl+N) - Quick calculations & GST tools"
            >
              <Calculator className="w-4 h-4 shrink-0" />
            </button>

            {/* Notifications */}
            <div className="shrink-0 flex items-center">
              <NotificationBell />
            </div>

            {/* Theme Toggle (Hidden on mobile header to preserve brand logo spacing) */}
            <div className="shrink-0 hidden sm:flex items-center">
              <ThemeToggle />
            </div>

            {/* User Avatar Dropdown */}
            <div ref={userMenuRef} className="relative shrink-0">
              <button
                onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                aria-label="Account and user preferences menu"
                aria-haspopup="true"
                aria-expanded={isUserMenuOpen}
                className="w-8 h-8 rounded-full bg-gradient-to-br from-primary/20 via-primary/10 to-accent/20 border border-border/60 flex items-center justify-center text-xs font-bold text-foreground hover:ring-2 hover:ring-primary/30 transition-all cursor-pointer shrink-0"
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
                          ? 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/30'
                          : role === 'OWNER'
                          ? 'bg-amber-500/10 text-amber-800 dark:text-amber-300 border-amber-500/30'
                          : role === 'CA'
                          ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30'
                          : role === 'EMPLOYEE'
                          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                          : 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/30'
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
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 text-xs font-medium text-amber-800 dark:text-amber-300 flex items-center justify-between print:hidden">
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
        <div className="fixed inset-0 z-50 lg:hidden print:hidden">
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-xs transition-opacity"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <aside
            ref={(node) => {
              // Focus trap: lock Tab/Shift-Tab inside the drawer
              if (!node) return;
              const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
              const focusableEls = node.querySelectorAll<HTMLElement>(focusableSelector);
              if (focusableEls.length === 0) return;
              const firstEl = focusableEls[0];
              const lastEl = focusableEls[focusableEls.length - 1];
              firstEl.focus();
              const trapHandler = (e: KeyboardEvent) => {
                if (e.key !== 'Tab') return;
                if (e.shiftKey) {
                  if (document.activeElement === firstEl) {
                    e.preventDefault();
                    lastEl.focus();
                  }
                } else {
                  if (document.activeElement === lastEl) {
                    e.preventDefault();
                    firstEl.focus();
                  }
                }
              };
              node.addEventListener('keydown', trapHandler);
              // Cleanup via MutationObserver is not needed since React unmounts when isMobileNavOpen=false
            }}
            className="relative w-72 max-w-[80vw] bg-card/95 backdrop-blur-xl border-r border-border/40 h-full flex flex-col p-5 shadow-2xl z-10 animate-in slide-in-from-left duration-200"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation Menu"
          >
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <div className="flex items-center gap-2">
                <VouchLogo size={24} showWordmark={true} />
              </div>
              <div className="flex items-center gap-1.5">
                <ThemeToggle />
                <button
                  onClick={() => setIsMobileNavOpen(false)}
                  className="text-muted-foreground hover:text-foreground p-2 rounded-lg min-h-[44px] min-w-[44px] flex items-center justify-center cursor-pointer transition-colors"
                  aria-label="Close Navigation Menu"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
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
                className="flex items-center gap-2 px-3 py-2 bg-muted text-foreground rounded-lg border border-border/60 font-mono tabular-nums text-xs min-h-[44px]"
              >
                <Calendar className="w-4 h-4 text-muted-foreground" />
                <span>{activeFY?.code || "FY 26-27"} · {workingDate}</span>
              </button>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => {
                    setIsMobileNavOpen(false);
                    setIsCalculatorOpen(true);
                  }}
                  className="p-2 bg-muted/60 text-muted-foreground hover:text-foreground rounded-lg border border-border/50 text-xs min-h-[44px] min-w-[44px] flex items-center justify-center cursor-pointer"
                  aria-label="Calculator"
                  title="Calculator (Alt+N)"
                >
                  <Calculator className="w-4 h-4" />
                </button>
                <button
                  onClick={() => {
                    setIsMobileNavOpen(false);
                    setIsHelpOpen(true);
                  }}
                  className="px-3 py-2 bg-muted/60 text-muted-foreground rounded-lg border border-border/50 text-xs font-semibold min-h-[44px] cursor-pointer"
                >
                  Help (F1)
                </button>
              </div>
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
      <main id="main-content" className="flex-1 overflow-y-auto overflow-x-hidden pb-20 lg:pb-0 print:overflow-visible print:p-0 print:m-0 print:w-full print:block">
        <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto print:p-0 print:m-0 print:max-w-none print:w-full">
          {children}
        </div>
      </main>

      {/* Mobile Bottom Navigation Bar (First-Class Touch Experience) */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 bg-card/95 backdrop-blur-xl border-t border-border/60 lg:hidden px-3 py-1.5 flex items-center justify-around shadow-2xl print:hidden">
        <Link
          href="/dashboard"
          className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-lg text-[10px] font-medium transition-colors ${
            pathname === "/dashboard" ? "text-primary font-bold" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <BarChart3 className="w-4.5 h-4.5" />
          <span>Home</span>
        </Link>

        <Link
          href="/sales"
          className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-lg text-[10px] font-medium transition-colors ${
            pathname.startsWith("/sales") ? "text-primary font-bold" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Receipt className="w-4.5 h-4.5" />
          <span>Sales</span>
        </Link>

        {/* Central Hero Universal + New Button */}
        <button
          type="button"
          onClick={() => setIsUniversalNewOpen(true)}
          className="-mt-5 w-12 h-12 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/35 flex items-center justify-center cursor-pointer transition-transform active:scale-95 shrink-0"
          aria-label="Universal New Transaction"
        >
          <Plus className="w-6 h-6 stroke-[2.5]" />
        </button>

        <Link
          href="/health"
          className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-lg text-[10px] font-medium transition-colors ${
            pathname.startsWith("/health") || pathname.startsWith("/banking") ? "text-amber-600 dark:text-amber-400 font-bold" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <ShieldAlert className="w-4.5 h-4.5 text-amber-500" />
          <span>Fix</span>
        </Link>

        <button
          type="button"
          onClick={() => setIsMobileNavOpen(true)}
          className="flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-lg text-[10px] font-medium text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
          aria-label="Open Navigation Menu"
          title="Menu"
        >
          <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          <span>Menu</span>
        </button>
      </nav>

      {/* Universal + New Modal */}
      <UniversalNewModal
        isOpen={isUniversalNewOpen}
        onClose={() => setIsUniversalNewOpen(false)}
      />
    </div>
  );
}

