"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Keyboard,
  Scan,
  FileCheck,
  TrendingUp,
  Sparkles,
  ArrowRight,
  Zap,
  Shield,
  Globe,
  BarChart3,
  Clock,
  Users,
  ChevronRight,
  Layers,
  Terminal,
} from "lucide-react";
import { isAuthenticated } from "@/utils/auth";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useShortcuts } from "@/context/ShortcutContext";
import { VouchLogo } from "@/components/VouchLogo";

/* ────────────────────── Feature Data ────────────────────── */
const features = [
  {
    icon: Keyboard,
    title: "Lightning-Fast Data Entry",
    description: "Works just like Tally — press F8 for sales, F9 for purchases. Create new parties on the fly and save entries instantly. Your hands never leave the keyboard.",
    color: "blue",
    gradient: "from-blue-500/10 to-blue-600/5",
    iconBg: "bg-blue-500/10 dark:bg-blue-500/15",
    iconColor: "text-blue-600 dark:text-blue-400",
    borderHover: "hover:border-blue-500/40",
  },
  {
    icon: Scan,
    title: "Scan Bills with AI",
    description: "Just take a photo of any purchase bill or upload a PDF. Our AI reads everything — items, quantities, GST, supplier details — and fills the entry for you.",
    color: "purple",
    gradient: "from-purple-500/10 to-purple-600/5",
    iconBg: "bg-purple-500/10 dark:bg-purple-500/15",
    iconColor: "text-purple-600 dark:text-purple-400",
    borderHover: "hover:border-purple-500/40",
  },
  {
    icon: FileCheck,
    title: "GST Done Automatically",
    description: "CGST, SGST, IGST — calculated automatically based on your state. Stock updates, tax reports, and proper books — all handled without extra effort.",
    color: "emerald",
    gradient: "from-emerald-500/10 to-emerald-600/5",
    iconBg: "bg-emerald-500/10 dark:bg-emerald-500/15",
    iconColor: "text-emerald-600 dark:text-emerald-400",
    borderHover: "hover:border-emerald-500/40",
  },
  {
    icon: TrendingUp,
    title: "Know Your Business Better",
    description: "See your best customers, daily sales, pending payments, and profit — all in one dashboard. No spreadsheets, no guesswork.",
    color: "amber",
    gradient: "from-amber-500/10 to-amber-600/5",
    iconBg: "bg-amber-500/10 dark:bg-amber-500/15",
    iconColor: "text-amber-600 dark:text-amber-400",
    borderHover: "hover:border-amber-500/40",
  },
  {
    icon: Globe,
    title: "Connected with Your Buyers",
    description: "Send invoices directly to your buyer's account. They see it instantly and can accept it into their books — no WhatsApp, no emails, no confusion.",
    color: "cyan",
    gradient: "from-cyan-500/10 to-cyan-600/5",
    iconBg: "bg-cyan-500/10 dark:bg-cyan-500/15",
    iconColor: "text-cyan-600 dark:text-cyan-400",
    borderHover: "hover:border-cyan-500/40",
  },
  {
    icon: Shield,
    title: "Your Data is Safe",
    description: "Every transaction is securely saved and cannot be tampered with. Your books are always accurate, always backed up, and only you can access them.",
    color: "rose",
    gradient: "from-rose-500/10 to-rose-600/5",
    iconBg: "bg-rose-500/10 dark:bg-rose-500/15",
    iconColor: "text-rose-600 dark:text-rose-400",
    borderHover: "hover:border-rose-500/40",
  },
];

/* ────────────────────── Keyboard Shortcut Data ────────────────────── */
const shortcuts = [
  { label: "Sales", key: "F8", desc: "GST Invoice", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20" },
  { label: "Purchase", key: "F9", desc: "AI Bill Scan", color: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20" },
  { label: "Search", key: "⌘K", desc: "Command Box", color: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20" },
  { label: "Save", key: "^A", desc: "Instant Post", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20" },
  { label: "Masters", key: "Alt+C", desc: "On the Fly", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20" },
  { label: "Date", key: "F2", desc: "Change Period", color: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20" },
];

/* ────────────────────── Main Page ────────────────────── */
export default function LandingPage() {
  const [isAuth, setIsAuth] = useState(false);
  const { setIsHelpOpen } = useShortcuts();

  useEffect(() => {
    setIsAuth(isAuthenticated());
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-blue-600/20 selection:text-foreground">
      {/* ─────────── Navigation ─────────── */}
      <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/70 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2.5">
              <VouchLogo size={28} showWordmark={true} />
              <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-600/10 text-blue-600 dark:text-blue-400 rounded border border-blue-500/20 font-bold">
                Cloud Core
              </span>
            </Link>
            <nav className="hidden md:flex items-center gap-1 text-[13px] font-medium text-muted-foreground">
              <a href="#features" className="px-3 py-1.5 rounded-lg hover:text-foreground hover:bg-muted transition-all">Features</a>
              <a href="#mockup" className="px-3 py-1.5 rounded-lg hover:text-foreground hover:bg-muted transition-all">AI Bill Scanner</a>
              <a href="#shortcuts" className="px-3 py-1.5 rounded-lg hover:text-foreground hover:bg-muted transition-all">Keyboard Shortcuts</a>
              <a href="#get-started" className="px-3 py-1.5 rounded-lg hover:text-foreground hover:bg-muted transition-all">Get Started</a>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button
              onClick={() => setIsHelpOpen(true)}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded-lg text-xs font-semibold border border-border transition-colors cursor-pointer"
            >
              <span>Shortcuts</span>
              <kbd className="px-1 py-0.5 bg-background rounded text-[10px] text-muted-foreground font-mono border border-border/50">F1</kbd>
            </button>

            {isAuth ? (
              <Link
                href="/dashboard"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md shadow-blue-600/20 transition-all flex items-center gap-1.5"
              >
                <span>Go to Dashboard →</span>
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="px-3.5 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md shadow-blue-600/20 transition-all"
                >
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ─────────── Hero Section ─────────── */}
      <section className="relative overflow-hidden pt-20 pb-24 md:pt-28 md:pb-32">
        {/* Background Pattern — subtle dot grid */}
        <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.04]" style={{
          backgroundImage: "radial-gradient(circle, currentColor 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }} />

        {/* Ambient Glow — Light */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[500px] bg-gradient-to-b from-blue-500/8 via-purple-500/5 to-transparent blur-3xl pointer-events-none rounded-full dark:from-blue-600/15 dark:via-purple-600/10" />

        {/* Secondary glow accents */}
        <div className="absolute -top-20 -left-40 w-[400px] h-[400px] bg-blue-400/5 dark:bg-blue-500/10 blur-3xl rounded-full pointer-events-none" />
        <div className="absolute -top-20 -right-40 w-[400px] h-[400px] bg-purple-400/5 dark:bg-purple-500/10 blur-3xl rounded-full pointer-events-none" />

        <div className="max-w-5xl mx-auto px-6 text-center space-y-8 relative z-10">
          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/8 dark:bg-blue-500/10 border border-blue-500/15 dark:border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-semibold"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>Next-Gen Cloud Accounting & ERP for Modern Businesses</span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-black tracking-tight leading-[1.08] text-balance"
          >
            Desktop Speed.{" "}
            <br className="hidden sm:block" />
            Cloud Power.{" "}
            <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-blue-600 via-indigo-500 to-purple-600 dark:from-blue-400 dark:via-indigo-400 dark:to-purple-400 bg-clip-text text-transparent">
              AI Intelligence.
            </span>
          </motion.h1>

          {/* Subtitle */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="max-w-2xl mx-auto text-base sm:text-lg text-muted-foreground text-balance leading-relaxed"
          >
            The modern double-entry ERP built for fast-moving businesses.
            Zero data entry with AI bill scanning, instant GST compliance,
            and keyboard-first navigation.
          </motion.p>

          {/* CTAs */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="flex items-center justify-center gap-4 flex-wrap pt-2"
          >
            <Link
              href={isAuth ? "/dashboard" : "/register"}
              className="group px-7 py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold shadow-lg shadow-blue-600/25 dark:shadow-blue-600/15 transition-all flex items-center gap-2.5 cursor-pointer"
            >
              <span>{isAuth ? "Launch Dashboard" : "Get Started Free"}</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <a
              href="#mockup"
              className="px-7 py-3.5 bg-white dark:bg-secondary hover:bg-slate-50 dark:hover:bg-secondary/80 text-foreground border border-border/80 dark:border-border rounded-xl text-sm font-bold transition-all flex items-center gap-2 cursor-pointer shadow-sm"
            >
              <span>Interactive Demo</span>
              <span className="inline-flex items-center px-1.5 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded text-[10px] font-bold border border-emerald-500/20">Live</span>
            </a>
          </motion.div>

          {/* Keyboard Shortcut Matrix */}
          <div id="shortcuts" className="pt-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.55 }}
              className="p-3 bg-white dark:bg-card border border-border/80 dark:border-border rounded-2xl shadow-xl shadow-black/5 dark:shadow-black/20 max-w-3xl mx-auto grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-left"
            >
              {shortcuts.map((s) => (
                <div key={s.key} className="p-2.5 bg-slate-50 dark:bg-zinc-900/80 rounded-xl border border-border/60 dark:border-border space-y-1 hover:border-blue-500/30 transition-colors">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] text-muted-foreground uppercase font-semibold">{s.label}</span>
                    <kbd className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${s.color}`}>{s.key}</kbd>
                  </div>
                  <div className="text-xs font-bold text-foreground">{s.desc}</div>
                </div>
              ))}
            </motion.div>
          </div>
        </div>
      </section>

      {/* ─────────── Features Grid ─────────── */}
      <section id="features" className="py-24 border-t border-border/60 bg-slate-50/50 dark:bg-zinc-950/40">
        <div className="max-w-7xl mx-auto px-6 space-y-16">
          <div className="text-center max-w-2xl mx-auto space-y-4">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/8 dark:bg-blue-500/10 border border-blue-500/15 dark:border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-semibold"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Built for Your Business</span>
            </motion.div>
            <motion.h2
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="text-3xl sm:text-4xl font-extrabold tracking-tight text-balance"
            >
              Everything You Need to{" "}
              <span className="bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400 bg-clip-text text-transparent">Run Your Accounts</span>
            </motion.h2>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="text-muted-foreground text-sm sm:text-base"
            >
              Whether you run a shop, a factory, or a trading business — ShriLekh makes billing and bookkeeping simple.
            </motion.p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className={`group p-6 bg-white dark:bg-card border border-border/60 dark:border-border rounded-2xl space-y-4 shadow-sm hover:shadow-md ${f.borderHover} transition-all duration-300`}
              >
                <div className={`w-11 h-11 ${f.iconBg} ${f.iconColor} rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform duration-300`}>
                  <f.icon className="w-5 h-5" />
                </div>
                <h3 className="text-base font-bold text-foreground">{f.title}</h3>
                <p className="text-[13px] text-muted-foreground leading-relaxed">
                  {f.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─────────── AI OCR Mockup Section ─────────── */}
      <section id="mockup" className="py-24 border-t border-border/60 relative overflow-hidden">
        {/* Subtle background gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-background via-slate-50/30 dark:via-zinc-950/50 to-background pointer-events-none" />

        <div className="max-w-6xl mx-auto px-6 space-y-10 relative z-10">
          <div className="text-center space-y-3 max-w-2xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-600 dark:text-purple-400 uppercase tracking-wider"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Live Scanning Simulation</span>
            </motion.div>
            <motion.h2
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-3xl sm:text-4xl font-extrabold tracking-tight"
            >
              See AI OCR & Split-Screen{" "}
              <span className="bg-gradient-to-r from-purple-600 to-pink-600 dark:from-purple-400 dark:to-pink-400 bg-clip-text text-transparent">in Action</span>
            </motion.h2>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="text-muted-foreground text-sm"
            >
              Drag-and-drop supplier bills to extract line items, quantities, and GST rates in seconds.
            </motion.p>
          </div>

          {/* Browser Window Mockup */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="rounded-2xl border border-border/80 dark:border-border bg-white dark:bg-zinc-900 shadow-2xl shadow-black/8 dark:shadow-black/30 overflow-hidden"
          >
            {/* Window Titlebar */}
            <div className="px-4 py-3 bg-slate-50 dark:bg-zinc-950 border-b border-border/80 dark:border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-400 dark:bg-red-500/80 inline-block" />
                <span className="w-3 h-3 rounded-full bg-yellow-400 dark:bg-yellow-500/80 inline-block" />
                <span className="w-3 h-3 rounded-full bg-green-400 dark:bg-green-500/80 inline-block" />
              </div>
              <div className="px-6 py-1 bg-white dark:bg-zinc-900 rounded-lg text-[11px] font-mono text-muted-foreground border border-border/80 dark:border-border flex items-center gap-2">
                <span className="text-green-600 dark:text-green-500">🔒</span>
                <span>https://srilekh.com/purchases/new</span>
              </div>
              <div className="text-xs text-muted-foreground font-mono flex items-center gap-1.5">
                <Terminal className="w-3 h-3" />
                <span>F9 Purchase Scan</span>
              </div>
            </div>

            {/* Split Screen Content */}
            <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-6 bg-slate-50/80 dark:bg-zinc-950/80">
              {/* Left: Simulated Invoice */}
              <div className="relative bg-white dark:bg-zinc-900 border border-border/60 dark:border-border rounded-xl p-5 overflow-hidden flex flex-col justify-between h-[360px]">
                {/* Scanning beam */}
                <motion.div
                  animate={{ top: ["0%", "100%", "0%"] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-blue-500 to-transparent shadow-[0_0_12px_rgba(59,130,246,0.5)] pointer-events-none z-10"
                />

                <div className="space-y-4">
                  <div className="flex justify-between items-start border-b border-border/60 dark:border-border pb-3">
                    <div>
                      <div className="text-xs font-bold text-foreground font-mono flex items-center gap-1.5">
                        <span>TAX INVOICE</span>
                        <span className="text-[10px] font-sans font-semibold px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                          Demo Invoice
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">Apex Industrial Supplies Pvt Ltd</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-mono text-blue-600 dark:text-blue-400 font-bold"># INV-2026-0891</div>
                      <div className="text-[10px] text-muted-foreground font-mono">Date: 15/01/2026</div>
                    </div>
                  </div>

                  <div className="space-y-2 text-[11px] font-mono">
                    <div className="flex justify-between text-muted-foreground text-[10px] border-b border-border/40 dark:border-border/60 pb-1">
                      <span>ITEM DESCRIPTION</span>
                      <span>HSN</span>
                      <span>QTY</span>
                      <span>AMOUNT</span>
                    </div>
                    <div className="flex justify-between text-foreground">
                      <span className="font-semibold">BEARING 6205-2RS INDUSTRIAL</span>
                      <span className="text-muted-foreground">84821011</span>
                      <span>10.00 PCS</span>
                      <span>₹2,500.00</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>CGST (9.00%)</span>
                      <span></span>
                      <span></span>
                      <span>₹225.00</span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>SGST (9.00%)</span>
                      <span></span>
                      <span></span>
                      <span>₹225.00</span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-border/60 dark:border-border flex justify-between items-center text-xs font-bold font-mono">
                  <span className="text-muted-foreground">GRAND TOTAL:</span>
                  <span className="text-emerald-600 dark:text-emerald-400 text-sm">₹ 2,950.00</span>
                </div>
              </div>

              {/* Right: Extracted Data */}
              <div className="bg-white dark:bg-zinc-900 border border-blue-500/20 dark:border-blue-500/30 rounded-xl p-5 space-y-4 flex flex-col justify-between h-[360px]">
                <div className="space-y-3">
                  <div className="flex items-center justify-between border-b border-border/60 dark:border-border pb-2">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                      <span className="text-xs font-bold text-foreground">AI OCR Extracted Data</span>
                    </div>
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded text-[10px] font-bold border border-emerald-500/20">
                      High-confidence matching
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 bg-slate-50 dark:bg-zinc-950 rounded-lg border border-border/60 dark:border-border">
                      <div className="text-[10px] text-muted-foreground uppercase font-medium">Supplier</div>
                      <div className="font-semibold text-foreground truncate mt-0.5">Apex Industrial Supplies Pvt Ltd</div>
                    </div>
                    <div className="p-2.5 bg-slate-50 dark:bg-zinc-950 rounded-lg border border-border/60 dark:border-border">
                      <div className="text-[10px] text-muted-foreground uppercase font-medium">GSTIN</div>
                      <div className="font-mono text-blue-600 dark:text-blue-400 font-bold mt-0.5">27AAACA1234A1Z5</div>
                    </div>
                    <div className="p-2.5 bg-slate-50 dark:bg-zinc-950 rounded-lg border border-border/60 dark:border-border">
                      <div className="text-[10px] text-muted-foreground uppercase font-medium">State Code</div>
                      <div className="font-mono text-foreground mt-0.5">27 (Maharashtra)</div>
                    </div>
                    <div className="p-2.5 bg-slate-50 dark:bg-zinc-950 rounded-lg border border-border/60 dark:border-border">
                      <div className="text-[10px] text-muted-foreground uppercase font-medium">Invoice No</div>
                      <div className="font-mono text-purple-600 dark:text-purple-400 font-bold mt-0.5">INV-2026-0891</div>
                    </div>
                  </div>

                  <div className="p-2.5 bg-slate-50 dark:bg-zinc-950 rounded-lg border border-border/60 dark:border-border space-y-1 text-xs">
                    <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                      <span>TAXABLE: ₹2,500.00</span>
                      <span>CGST: ₹225.00 | SGST: ₹225.00</span>
                    </div>
                    <div className="flex justify-between text-xs font-bold text-foreground font-mono">
                      <span>Total Amount:</span>
                      <span className="text-emerald-600 dark:text-emerald-400">₹2,950.00</span>
                    </div>
                  </div>
                </div>

                <Link
                  href="/purchases/new"
                  className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold text-center transition-colors shadow-lg shadow-emerald-600/20 flex items-center justify-center gap-2"
                >
                  <FileCheck className="w-3.5 h-3.5" />
                  <span>Save to Your Books ✓</span>
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─────────── Trust Indicators ─────────── */}
      <section className="py-16 border-t border-border/60 bg-slate-50/50 dark:bg-zinc-950/40">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="grid grid-cols-2 md:grid-cols-4 gap-6"
          >
            {[
              { icon: Shield, label: "100% Accurate Books", desc: "Every entry is double-checked" },
              { icon: Clock, label: "Works Offline Too", desc: "No internet? No problem" },
              { icon: BarChart3, label: "Instant Reports", desc: "Profit & Loss, Balance Sheet" },
              { icon: Users, label: "Multi-User Access", desc: "Your whole team can use it" },
            ].map((item, i) => (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 15 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="flex flex-col items-center text-center gap-2.5 p-5 rounded-xl bg-white dark:bg-card border border-border/50 dark:border-border shadow-sm"
              >
                <div className="w-10 h-10 rounded-lg bg-blue-500/8 dark:bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400">
                  <item.icon className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-sm font-bold text-foreground">{item.label}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{item.desc}</div>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─────────── CTA Section ─────────── */}
      <section id="get-started" className="py-24 border-t border-border/60 relative overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-background via-blue-50/30 dark:via-blue-950/10 to-background pointer-events-none" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-blue-500/5 dark:bg-blue-500/8 blur-3xl rounded-full pointer-events-none" />

        <div className="max-w-3xl mx-auto px-6 text-center space-y-8 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="space-y-4"
          >
            <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-balance">
              Ready to streamline your{" "}
              <span className="bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400 bg-clip-text text-transparent">
                business accounting
              </span>?
            </h2>
            <p className="text-muted-foreground text-sm sm:text-base max-w-xl mx-auto">
              Start billing, manage GST, and keep your books clean —
              all from one simple app. Free to get started.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.15 }}
            className="flex items-center justify-center gap-4 flex-wrap"
          >
            <Link
              href={isAuth ? "/dashboard" : "/register"}
              className="group px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold shadow-xl shadow-blue-600/25 dark:shadow-blue-600/15 transition-all inline-flex items-center gap-2.5 cursor-pointer"
            >
              <span>{isAuth ? "Enter Dashboard" : "Get Started Free"}</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
            className="text-[11px] text-muted-foreground"
          >
            No credit card required · Free tier available · Setup in under 2 minutes
          </motion.p>
        </div>
      </section>

      {/* ─────────── Footer ─────────── */}
      <footer className="border-t border-border/60 bg-slate-50 dark:bg-zinc-950 py-12 text-xs text-muted-foreground">
        <div className="max-w-7xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
          <div className="space-y-3 col-span-2 md:col-span-1">
            <VouchLogo size={24} showWordmark={true} />
            <p className="text-xs text-muted-foreground leading-relaxed max-w-[220px]">
              Simple billing, GST invoicing, and accounting software — built for Indian businesses who want to save time.
            </p>
          </div>
          <div className="space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-foreground">Product</div>
            <ul className="space-y-2 text-muted-foreground">
              <li><Link href="/dashboard" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Dashboard</Link></li>
              <li><Link href="/sales" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Sales Invoicing (F8)</Link></li>
              <li><Link href="/purchases" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />AI Bill Scanner (F9)</Link></li>
              <li><Link href="/vouchers" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Payments & Receipts</Link></li>
            </ul>
          </div>
          <div className="space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-foreground">Resources</div>
            <ul className="space-y-2 text-muted-foreground">
              <li><button onClick={() => setIsHelpOpen(true)} className="hover:text-foreground transition-colors cursor-pointer inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Keyboard Shortcuts (F1)</button></li>
              <li><Link href="/dashboard" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Documentation</Link></li>
              <li><Link href="/dashboard" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />GST Compliance Guide</Link></li>
              <li><Link href="/~offline" className="hover:text-foreground transition-colors inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Offline Support (PWA)</Link></li>
            </ul>
          </div>
          <div className="space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-foreground">Legal & Trust</div>
            <ul className="space-y-2 text-muted-foreground">
              <li className="inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Privacy Policy</li>
              <li className="inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Terms of Service</li>
              <li className="inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Secure & Reliable</li>
              <li className="inline-flex items-center gap-1"><ChevronRight className="w-3 h-3" />Your Data, Your Control</li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 pt-6 border-t border-border/60 dark:border-border flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] text-muted-foreground">
          <div>
            © {new Date().getFullYear()} ShriLekh Platform. Built for Modern Indian Businesses.
          </div>
          <div className="flex items-center gap-3 font-mono text-[10px]">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded border border-emerald-500/15">PWA Enabled</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded border border-blue-500/15">Desktop & Mobile</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
