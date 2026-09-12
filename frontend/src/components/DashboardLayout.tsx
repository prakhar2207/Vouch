"use client";
import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useHotkeys } from "react-hotkeys-hook";
import { ThemeToggle } from "./ThemeToggle";
import { removeTokens } from "@/utils/auth";
import CommandPalette from "./CommandPalette";
import { useShortcuts } from "@/context/ShortcutContext";
import { useFinancialYear } from "@/context/FinancialYearContext";
import { useAccountingPeriod } from "@/context/PeriodContext";
import { useCompany } from "@/context/CompanyContext";
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
  Activity,
  Landmark,
} from "lucide-react";
import SyncStatusBadge from "./SyncStatusBadge";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  // Dropdown states
  const [isMoreDropdownOpen, setIsMoreDropdownOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isFYDropdownOpen, setIsFYDropdownOpen] = useState(false);
  const [isCompanyDropdownOpen, setIsCompanyDropdownOpen] = useState(false);

  const moreRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const fyRef = useRef<HTMLDivElement>(null);
  const companyRef = useRef<HTMLDivElement>(null);

  const { setIsHelpOpen, setIsDateOpen, workingDate, startTour } = useShortcuts();
  const { activeFY, availableFYs, setActiveFY, isReadOnly, setIsClosingModalOpen } = useFinancialYear();
  const { displayPeriod, setIsPeriodModalOpen, setIsSplitModalOpen } = useAccountingPeriod();
  const { activeCompany, availableCompanies, setActiveCompany } = useCompany();

  // Close dropdowns on route change
  useEffect(() => {
    setIsMobileNavOpen(false);
    setIsMoreDropdownOpen(false);
    setIsUserMenuOpen(false);
    setIsFYDropdownOpen(false);
    setIsCompanyDropdownOpen(false);
  }, [pathname]);

  // Click away listener for dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
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
    pathname.startsWith("/analytics") ||
    pathname.startsWith("/reports") ||
    pathname.startsWith("/audit") ||
    pathname.startsWith("/health") ||
    pathname.startsWith("/ledgers");

  return (
    <div className="min-h-screen bg-background font-sans text-foreground flex flex-col">
      {/* Global Command Palette (Ctrl+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />

      {/* TOP NAVIGATION BAR */}
      <header className="sticky top-0 z-40 w-full border-b border-border/20 bg-card/80 backdrop-blur-xl shadow-sm">
        <div className="w-full px-3 sm:px-6 h-14 flex items-center justify-between gap-2 sm:gap-4">
          
          {/* Left Section: Brand & Core Nav */}
          <div className="flex items-center gap-2 lg:gap-4 min-w-0">
            {/* Mobile / Tablet Hamburger Button */}
            <button
              onClick={() => setIsMobileNavOpen(true)}
              className="lg:hidden p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer shrink-0 min-h-[36px] min-w-[36px] flex items-center justify-center"
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
                className="text-xl font-black tracking-tight text-foreground hover:opacity-90 flex items-center gap-1.5 shrink-0"
              >
                <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-violet-600 bg-clip-text text-transparent">
                  Vouch
                </span>
              </Link>
            </div>

            {/* Desktop Navigation Links */}
            <nav className="hidden lg:flex items-center gap-0.5 xl:gap-1 min-w-0">
              {/* Dashboard */}
              <Link
                id="tour-dashboard-link"
                href="/dashboard"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  pathname === "/dashboard"
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Dashboard
              </Link>

              {/* Sales */}
              <Link
                id="tour-sales-btn"
                href="/sales"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  isSalesActive
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Sales
              </Link>

              {/* Purchases */}
              <Link
                id="tour-purchase-btn"
                href="/purchases"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  isPurchasesActive
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Purchases
              </Link>

              {/* Parties */}
              <Link
                id="tour-parties-link"
                href="/parties"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  pathname.startsWith("/parties")
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Parties
              </Link>

              {/* Inventory */}
              <Link
                id="tour-inventory-link"
                href="/inventory"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  pathname.startsWith("/inventory")
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Inventory
              </Link>

              {/* Banking */}
              <Link
                id="tour-banking-link"
                href="/banking"
                className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors whitespace-nowrap ${
                  pathname.startsWith("/banking")
                    ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                Banking
              </Link>

              {/* More Dropdown */}
              <div ref={moreRef} className="relative">
                <button
                  onClick={() => setIsMoreDropdownOpen(!isMoreDropdownOpen)}
                  className={`px-2.5 xl:px-3 py-1.5 rounded-lg text-xs xl:text-sm font-medium transition-colors flex items-center gap-1 cursor-pointer whitespace-nowrap ${
                    isMoreActive
                      ? "text-foreground bg-primary/10 font-semibold border-b-2 border-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  }`}
                >
                  <span>More</span>
                  <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform duration-150 ${isMoreDropdownOpen ? "rotate-180" : ""}`} />
                </button>

                {isMoreDropdownOpen && (
                  <div className="absolute left-0 mt-1.5 w-60 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95">
                    <Link
                      href="/vouchers"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Transactions</div>
                        <div className="text-xs text-muted-foreground">View all transactions</div>
                      </div>
                    </Link>
                    <Link
                      href="/vouchers/new"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Payments & Receipts</div>
                        <div className="text-xs text-muted-foreground">Record money in/out</div>
                      </div>
                    </Link>
                    <Link
                      href="/vouchers/grid"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Journal Entry</div>
                        <div className="text-xs text-muted-foreground">Manual accounting entries</div>
                      </div>
                    </Link>
                    
                    <div className="border-t border-border/40 my-1"></div>
                    
                    <Link
                      href="/ledgers"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Accounts</div>
                        <div className="text-xs text-muted-foreground">Account heads & ledgers</div>
                      </div>
                    </Link>
                    <Link
                      href="/reports/trial-balance"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Trial Balance</div>
                        <div className="text-xs text-muted-foreground">Account balances summary</div>
                      </div>
                    </Link>
                    <Link
                      href="/export/tally"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Export to Tally</div>
                        <div className="text-xs text-muted-foreground">Export data to TallyPrime</div>
                      </div>
                    </Link>

                    <div className="border-t border-border/40 my-1"></div>

                    <Link
                      href="/health"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Books Health</div>
                        <div className="text-xs text-muted-foreground">Check your books</div>
                      </div>
                    </Link>
                    <Link
                      href="/audit"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">Activity Log</div>
                        <div className="text-xs text-muted-foreground">View change history</div>
                      </div>
                    </Link>
                    <button
                      onClick={() => {
                        setIsMoreDropdownOpen(false);
                        setIsClosingModalOpen(true);
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors flex items-center justify-between cursor-pointer"
                    >
                      <div>
                        <div className="font-medium">Close Financial Year</div>
                        <div className="text-xs text-muted-foreground">Year-end closing</div>
                      </div>
                    </button>
                    <button
                      onClick={() => {
                        setIsMoreDropdownOpen(false);
                        setIsSplitModalOpen(true);
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors flex items-center justify-between cursor-pointer"
                    >
                      <div>
                        <div className="font-medium">Archive Company Data</div>
                        <div className="text-xs text-muted-foreground">Split or archive data</div>
                      </div>
                    </button>
                    <Link
                      href="/network/inbox"
                      className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-foreground hover:bg-muted/70 transition-colors"
                      onClick={() => setIsMoreDropdownOpen(false)}
                    >
                      <div>
                        <div className="font-medium">B2B Network</div>
                        <div className="text-xs text-muted-foreground">Supplier e-invoices</div>
                      </div>
                    </Link>
                  </div>
                )}
              </div>
            </nav>
          </div>

          {/* Right Section: Unified Context Pill, Search, Utilities & Profile */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {/* Sync Status Badge Removed */}

            {/* Company Switcher Pill */}
            <div ref={companyRef} className="relative hidden md:block">
              <button
                onClick={() => {
                  setIsCompanyDropdownOpen(!isCompanyDropdownOpen);
                  setIsFYDropdownOpen(false);
                  setIsUserMenuOpen(false);
                }}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs min-h-[36px] max-w-[120px] xl:max-w-[170px]"
                title="Active Company"
              >
                <Building2 className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="font-medium text-foreground truncate">
                  {activeCompany?.name || "Company"}
                </span>
                <ChevronDown className={`w-3 h-3 text-muted-foreground shrink-0 transition-transform duration-150 ${isCompanyDropdownOpen ? "rotate-180" : ""}`} />
              </button>

              {isCompanyDropdownOpen && (
                <div className="absolute left-0 mt-1.5 w-60 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-1.5 z-50 animate-in fade-in zoom-in-95">
                  <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Active Company
                  </div>
                  {availableCompanies.length === 0 ? (
                    <div className="px-2 py-1.5 text-xs text-muted-foreground">No companies found</div>
                  ) : (
                    availableCompanies.map((comp) => (
                      <button
                        key={comp.id}
                        onClick={() => {
                          setActiveCompany(comp);
                          setIsCompanyDropdownOpen(false);
                          window.location.reload();
                        }}
                        className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-colors flex items-center justify-between ${
                          activeCompany?.id === comp.id
                            ? "bg-primary/10 text-primary font-semibold"
                            : "text-foreground hover:bg-muted"
                        }`}
                      >
                        <span className="truncate">{comp.name}</span>
                        {activeCompany?.id === comp.id && (
                          <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0 ml-1" />
                        )}
                      </button>
                    ))
                  )}
                  <div className="border-t border-border/40 my-1"></div>
                  <Link
                    href="/settings"
                    onClick={() => setIsCompanyDropdownOpen(false)}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    <span>Company Settings</span>
                  </Link>
                </div>
              )}
            </div>

            {/* Unified Compact Context Pill: FY · Date · Alt+F2 */}
            <div ref={fyRef} className="relative hidden md:block">
              <button
                onClick={() => setIsPeriodModalOpen(true)}
                className="flex items-center gap-1.5 xl:gap-2 px-2.5 xl:px-3 py-1.5 rounded-lg border border-border/50 bg-muted/30 hover:bg-muted/70 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs min-h-[36px]"
                title="Change Accounting Period (Alt + F2)"
              >
                <Calendar className="w-3.5 xl:w-4 h-3.5 xl:h-4 text-muted-foreground shrink-0" />
                <span className="font-mono tabular-nums text-xs font-medium text-foreground whitespace-nowrap">
                  {activeFY ? (activeFY.code || activeFY.name) : "FY 26-27"}<span className="hidden xl:inline"> · {workingDate ? workingDate.slice(5) : "Today"}</span>
                </span>
                <span className={`w-2 h-2 rounded-full shrink-0 ${activeFY?.is_closed ? "bg-amber-400" : "bg-emerald-400"}`}></span>
              </button>
            </div>

            {/* Search Trigger: Compact Ctrl+K */}
            <button
              id="tour-command-palette-btn"
              onClick={() => setIsCommandPaletteOpen(true)}
              className="flex items-center gap-1.5 sm:gap-2 px-2.5 py-1.5 rounded-lg border border-border/50 bg-muted/20 hover:bg-muted/60 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer shadow-2xs min-h-[36px]"
              title="Command Search (Ctrl+K)"
            >
              <Search className="w-4 h-4 text-muted-foreground" />
              <span className="hidden 2xl:inline text-xs font-normal">Search...</span>
            </button>

            {/* Help Icon Button (F1) */}
            <button
              id="tour-help-btn"
              onClick={() => setIsHelpOpen(true)}
              className="hidden xl:inline-flex p-2 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted/60 transition-colors cursor-pointer min-h-[36px] min-w-[36px] items-center justify-center"
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
                className="w-9 h-9 rounded-full bg-gradient-to-br from-primary/20 to-accent/20 border border-border/40 flex items-center justify-center text-xs font-bold text-foreground hover:ring-2 hover:ring-ring transition-all cursor-pointer"
                title="Account Menu"
              >
                <User className="w-4 h-4 text-muted-foreground" />
              </button>

              {isUserMenuOpen && (
                <div className="absolute right-0 mt-1.5 w-52 bg-card/95 backdrop-blur-xl border border-border/40 rounded-xl shadow-xl shadow-black/10 p-2 z-50 animate-in fade-in zoom-in-95">
                  <div className="px-3 py-2 border-b border-border/40 mb-1">
                    <div className="text-sm font-semibold text-foreground truncate">{activeCompany?.name || "My Business"}</div>
                  </div>
                  <Link
                    id="tour-settings-link"
                    href="/settings"
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-foreground hover:bg-muted/70 transition-colors"
                  >
                    <Settings className="w-3.5 h-3.5 text-muted-foreground" />
                    <span>Settings</span>
                  </Link>
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
                <span className="text-xl font-black bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                  Vouch
                </span>
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
              <Link
                href="/sales"
                onClick={() => setIsMobileNavOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  pathname.startsWith("/sales") ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60"
                }`}
              >
                <span>Sales</span>
              </Link>
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
