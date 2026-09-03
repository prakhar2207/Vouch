"use client";
import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useHotkeys } from 'react-hotkeys-hook';
import { ThemeToggle } from './ThemeToggle';
import { removeTokens } from '@/utils/auth';
import CommandPalette from './CommandPalette';
import { useShortcuts } from '@/context/ShortcutContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useAccountingPeriod } from '@/context/PeriodContext';
import { Calendar } from 'lucide-react';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isFYDropdownOpen, setIsFYDropdownOpen] = useState(false);
  const { setIsHelpOpen, setIsDateOpen, workingDate, startTour } = useShortcuts();
  const { activeFY, availableFYs, setActiveFY, isReadOnly, setIsClosingModalOpen } = useFinancialYear();
  const { displayPeriod, setIsPeriodModalOpen } = useAccountingPeriod();

  // Close mobile nav on route change
  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [pathname]);

  const handleLogout = () => {
    removeTokens();
    router.push('/login');
  };

  useHotkeys(['ctrl+k', 'meta+k'], (e) => {
    e.preventDefault();
    setIsCommandPaletteOpen((prev) => !prev);
  }, { enableOnFormTags: true });

  const navItems = [
    { id: 'tour-dashboard-link', path: '/dashboard', label: 'Dashboard' },
    { id: 'tour-sales-btn', path: '/sales', label: 'Sales', badge: 'F8' },
    { id: 'tour-purchase-btn', path: '/purchases', label: 'Purchases', badge: 'AI' },
    { id: 'tour-b2b-btn', path: '/network/inbox', label: 'B2B', badge: 'EDI' },
    { id: 'tour-grid-btn', path: '/vouchers/grid', label: 'Quick Journal' },
    { id: 'tour-vouchers-link', path: '/vouchers', label: 'Vouchers' },
    { id: 'tour-inventory-link', path: '/inventory', label: 'Inventory' },
    { id: 'tour-parties-link', path: '/parties', label: 'Parties' },
    { id: 'tour-tally-link', path: '/export/tally', label: 'Tally XML', badge: 'Alt+O' },
    { id: 'tour-settings-link', path: '/settings', label: 'Settings' },
  ];

  return (
    <div className="min-h-screen bg-background font-sans text-foreground flex flex-col">
      {/* Global Command Palette (Ctrl+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />

      {/* TOP NAVIGATION BAR (PC & Large Screens) */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-card/95 backdrop-blur-md shadow-sm">
        <div className="w-full px-3 sm:px-5 h-16 flex items-center justify-between gap-2 sm:gap-4">
          {/* Left: Brand & Desktop Horizontal Nav */}
          <div className="flex items-center gap-3 sm:gap-5 min-w-0 flex-1">
            {/* Mobile Hamburger Button */}
            <button
              onClick={() => setIsMobileNavOpen(true)}
              className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer shrink-0"
              aria-label="Open Navigation Menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            {/* Brand Logo - shrink-0 ensures it NEVER gets cut off */}
            <div id="tour-header-brand" className="flex items-center gap-1.5 shrink-0">
              <Link
                href="/dashboard"
                className="text-xl sm:text-2xl font-black text-blue-600 dark:text-blue-500 tracking-tight hover:opacity-90 flex items-center gap-1.5 shrink-0"
              >
                <span>Vouch</span>
              </Link>
              <span className="hidden sm:inline-block px-1.5 py-0.5 text-[9px] font-mono bg-blue-600/10 text-blue-500 rounded border border-blue-500/20 font-bold shrink-0">
                CORE
              </span>
            </div>

            {/* Desktop Navigation Links - scrollable without clipping logo */}
            <nav className="hidden md:flex items-center gap-1 overflow-x-auto no-scrollbar py-1 min-w-0 flex-1">
              {navItems.map((item) => {
                const isActive = item.path === pathname || (
                  item.path !== '/dashboard' &&
                  item.path !== '/vouchers' &&
                  pathname.startsWith(item.path + '/')
                );
                return (
                  <Link
                    key={item.path}
                    id={item.id}
                    href={item.path}
                    className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap shrink-0 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-sm font-bold'
                        : 'text-gray-400 hover:text-foreground hover:bg-zinc-800/60'
                    }`}
                  >
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className={`text-[9px] font-mono px-1 py-0.2 rounded ${
                        isActive ? 'bg-blue-700 text-white' : 'bg-zinc-800 text-gray-400 border border-zinc-700'
                      }`}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Right: Quick Action Controls */}
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {/* Tally-Style Continuous Period Selector (Alt+F2) */}
            <button
              onClick={() => setIsPeriodModalOpen(true)}
              className="hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/80 hover:bg-zinc-800 text-xs font-semibold text-zinc-300 transition-all cursor-pointer shadow-sm"
              title="Change Continuous Accounting Period (Alt + F2)"
            >
              <Calendar className="w-3.5 h-3.5 text-blue-400" />
              <span className="font-mono text-[11px] text-zinc-300">{displayPeriod}</span>
              <kbd className="px-1.5 py-0.2 bg-zinc-800 text-zinc-400 rounded border border-zinc-700 font-mono text-[9px]">
                Alt+F2
              </kbd>
            </button>

            {/* Financial Year Selector Dropdown */}
            {activeFY && (
              <div className="relative">
                <button
                  onClick={() => setIsFYDropdownOpen(!isFYDropdownOpen)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-all cursor-pointer ${
                    activeFY.is_closed
                      ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30'
                      : 'bg-zinc-900 hover:bg-zinc-800 text-foreground border-zinc-800'
                  }`}
                  title="Switch Financial Year"
                >
                  <span className={`w-2 h-2 rounded-full ${activeFY.is_closed ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`}></span>
                  <span className="font-mono text-xs">{activeFY.code || activeFY.name}</span>
                  <span className={`text-[9px] font-mono px-1 py-0.2 rounded uppercase ${
                    activeFY.is_closed ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-400 font-bold'
                  }`}>
                    {activeFY.is_closed ? 'Closed' : 'Open'}
                  </span>
                  <span className="text-[10px] text-zinc-400">▼</span>
                </button>

                {isFYDropdownOpen && (
                  <div className="absolute right-0 mt-1.5 w-64 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in">
                    <div className="px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 border-b border-zinc-800 mb-1">
                      Financial Years
                    </div>
                    <div className="max-h-56 overflow-y-auto space-y-1">
                      {availableFYs.map((fy) => (
                        <button
                          key={fy.id}
                          onClick={() => {
                            setActiveFY(fy);
                            setIsFYDropdownOpen(false);
                          }}
                          className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between transition-colors cursor-pointer ${
                            fy.id === activeFY.id
                              ? 'bg-blue-600/20 text-blue-400 font-bold border border-blue-500/30'
                              : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'
                          }`}
                        >
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span>{fy.name}</span>
                              {fy.is_current && (
                                <span className="text-[9px] bg-blue-500/20 text-blue-400 px-1 rounded">Current</span>
                              )}
                            </div>
                            <div className="text-[10px] text-zinc-500 font-mono">
                              {fy.start_date} ~ {fy.end_date}
                            </div>
                          </div>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                            fy.is_closed ? 'bg-zinc-800 text-amber-400 border border-amber-500/20' : 'bg-emerald-500/20 text-emerald-400'
                          }`}>
                            {fy.is_closed ? 'Closed' : 'Open'}
                          </span>
                        </button>
                      ))}
                    </div>

                    <div className="border-t border-zinc-800 mt-1 pt-1">
                      <button
                        onClick={() => {
                          setIsFYDropdownOpen(false);
                          setIsClosingModalOpen(true);
                        }}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-semibold text-amber-400 hover:bg-amber-500/10 flex items-center gap-1.5 transition-colors cursor-pointer"
                      >
                        <span>🔒</span>
                        <span>Year-End Close & Roll-Forward</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Working Date (F2) */}
            <button
              id="tour-date-btn"
              onClick={() => setIsDateOpen(true)}
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-gray-300 rounded-lg border border-zinc-800 font-mono text-xs transition-colors cursor-pointer"
              title="Change Date (F2)"
            >
              <span>📅 {workingDate}</span>
              <kbd className="text-[9px] bg-zinc-800 px-1 py-0.2 rounded text-gray-400 border border-zinc-700">F2</kbd>
            </button>

            {/* Help & Guide (F1) */}
            <button
              id="tour-help-btn"
              onClick={() => setIsHelpOpen(true)}
              className="hidden sm:flex items-center gap-1 px-2.5 py-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-400 rounded-lg border border-blue-500/30 text-xs font-bold transition-colors cursor-pointer"
              title="Help & Shortcuts (F1)"
            >
              <span>Help</span>
              <kbd className="text-[9px] bg-blue-900/40 px-1 py-0.2 rounded text-blue-300">F1</kbd>
            </button>

            {/* Command Search (Ctrl+K) */}
            <button
              id="tour-command-palette-btn"
              onClick={() => setIsCommandPaletteOpen(true)}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-xs font-mono text-gray-300 rounded-lg border border-zinc-700 flex items-center gap-1 shadow-sm transition-colors cursor-pointer"
              title="Search (Ctrl+K)"
            >
              <span>🔍</span>
              <span className="hidden sm:inline">⌘K</span>
            </button>

            <ThemeToggle />

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              className="hidden sm:block text-xs font-semibold text-red-500 hover:text-red-400 px-2 py-1.5 rounded-lg hover:bg-red-500/10 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Read-Only Mode Banner for Closed Financial Year */}
      {isReadOnly && activeFY && (
        <div className="bg-amber-500/15 border-b border-amber-500/30 text-amber-400 px-4 py-2 text-xs font-semibold flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>⚠️</span>
            <span>
              Viewing <strong className="text-white">{activeFY.name}</strong> (Closed Period: {activeFY.start_date} to {activeFY.end_date}). Transactions in this period are read-only.
            </span>
          </div>
          <button
            onClick={() => {
              const openFY = availableFYs.find((f) => !f.is_closed);
              if (openFY) setActiveFY(openFY);
            }}
            className="text-[11px] underline hover:text-white font-bold cursor-pointer"
          >
            Switch to Active Open FY →
          </button>
        </div>
      )}

      {/* MOBILE HIDDEN SLIDE-OUT SIDEBAR DRAWER */}
      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
            onClick={() => setIsMobileNavOpen(false)}
          />

          {/* Sidebar Drawer */}
          <aside className="relative w-72 max-w-[80vw] bg-card border-r border-border h-full flex flex-col p-5 shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            <div className="flex items-center justify-between pb-4 border-b border-border">
              <Link href="/dashboard" className="text-xl font-bold text-blue-600 dark:text-blue-500">
                Vouch
              </Link>
              <button
                onClick={() => setIsMobileNavOpen(false)}
                className="text-gray-400 hover:text-white p-1"
              >
                ✕
              </button>
            </div>

            {/* Working Date & Shortcuts info on Mobile */}
            <div className="py-3 flex items-center justify-between text-xs border-b border-border/50">
              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  setIsDateOpen(true);
                }}
                className="flex items-center gap-1 px-2 py-1 bg-zinc-900 text-gray-300 rounded border border-zinc-800 font-mono text-xs"
              >
                <span>📅 {workingDate}</span>
                <kbd className="text-[9px] text-gray-400">F2</kbd>
              </button>

              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  setIsHelpOpen(true);
                }}
                className="px-2 py-1 bg-blue-600/10 text-blue-400 rounded border border-blue-500/30 text-xs font-bold"
              >
                Help (F1)
              </button>
            </div>

            {/* Mobile Nav Links */}
            <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
              {navItems.map((item) => {
                const isActive = pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    href={item.path}
                    onClick={() => setIsMobileNavOpen(false)}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                      isActive
                        ? 'bg-blue-600 text-white font-semibold shadow-sm'
                        : 'text-gray-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                        isActive ? 'bg-blue-700 text-white' : 'bg-zinc-800 text-gray-400 border border-zinc-700'
                      }`}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            <div className="pt-4 border-t border-border flex items-center justify-between">
              <button
                onClick={handleLogout}
                className="text-sm font-semibold text-red-500 hover:text-red-400"
              >
                Logout
              </button>
              <button
                onClick={() => {
                  setIsMobileNavOpen(false);
                  startTour();
                }}
                className="text-xs text-blue-400 hover:underline"
              >
                Tour
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* Main Content Area - Full width on desktop */}
      <main className="flex-1 overflow-auto">
        <div className="p-4 sm:p-8 max-w-[1600px] mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
