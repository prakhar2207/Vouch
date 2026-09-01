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
  CheckCircle2, 
  ShieldCheck, 
  ArrowRight, 
  Zap, 
  Cpu, 
  Laptop, 
  Layers, 
  FileText 
} from "lucide-react";
import { isAuthenticated } from "@/utils/auth";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useShortcuts } from "@/context/ShortcutContext";

export default function LandingPage() {
  const [isAuth, setIsAuth] = useState(false);
  const { setIsHelpOpen } = useShortcuts();

  useEffect(() => {
    setIsAuth(isAuthenticated());
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col selection:bg-blue-500 selection:text-white">
      {/* Navigation Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border/40 bg-background/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl font-black tracking-tight text-blue-600 dark:text-blue-500">
                Vouch
              </span>
              <span className="px-2 py-0.5 text-[10px] font-mono bg-blue-600/10 text-blue-500 rounded border border-blue-500/20 font-bold">
                Cloud Core
              </span>
            </Link>
            <nav className="hidden md:flex items-center gap-6 text-xs font-semibold text-gray-400">
              <a href="#features" className="hover:text-foreground transition-colors">Features</a>
              <a href="#mockup" className="hover:text-foreground transition-colors">AI Bill Scanner</a>
              <a href="#shortcuts" className="hover:text-foreground transition-colors">Keyboard Shortcuts</a>
              <a href="#get-started" className="hover:text-foreground transition-colors">Get Started</a>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button
              onClick={() => setIsHelpOpen(true)}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-semibold border border-zinc-700 transition-colors cursor-pointer"
            >
              <span>Shortcuts</span>
              <kbd className="px-1 py-0.2 bg-zinc-900 rounded text-[10px] text-gray-400 font-mono">F1</kbd>
            </button>

            {isAuth ? (
              <Link
                href="/dashboard"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md transition-all flex items-center gap-1.5"
              >
                <span>Go to Dashboard →</span>
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link
                  href="/login"
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-300 hover:text-white transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-md transition-all"
                >
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-16 pb-20 md:pt-24 md:pb-28">
        {/* Ambient Glows */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-gradient-to-tr from-blue-600/15 via-purple-600/10 to-transparent blur-3xl pointer-events-none rounded-full" />

        <div className="max-w-5xl mx-auto px-6 text-center space-y-6 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>Next-Gen Cloud Accounting & ERP for Modern Businesses</span>
          </motion.div>

          <motion.h1 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-4xl sm:text-6xl font-black tracking-tight leading-[1.1] text-balance"
          >
            Desktop Speed. The Cloud's Power. <br />
            <span className="bg-gradient-to-r from-blue-500 via-indigo-400 to-purple-500 bg-clip-text text-transparent">
              AI's Intelligence.
            </span>
          </motion.h1>

          <motion.p 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="max-w-2xl mx-auto text-base sm:text-lg text-gray-400 text-balance leading-relaxed"
          >
            The modern double-entry ERP built for fast-moving businesses. Zero data entry with AI bill scanning, instant GST compliance, and 100% keyboard-first navigation.
          </motion.p>

          {/* CTAs */}
          <motion.div 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3 }}
            className="flex items-center justify-center gap-4 flex-wrap pt-4"
          >
            <Link
              href={isAuth ? "/dashboard" : "/register"}
              className="px-6 py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold shadow-xl shadow-blue-600/20 transition-all flex items-center gap-2 cursor-pointer"
            >
              <span>{isAuth ? "Launch Dashboard" : "Get Started"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a
              href="#mockup"
              className="px-6 py-3.5 bg-zinc-900 hover:bg-zinc-800 text-gray-200 border border-zinc-700 rounded-xl text-sm font-bold transition-all flex items-center gap-2 cursor-pointer"
            >
              <span>Interactive Demo</span>
              <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded text-[10px] font-mono text-gray-400">Live</kbd>
            </a>
          </motion.div>

          {/* Quick Keyboard Matrix */}
          <div id="shortcuts" className="pt-10">
            <div className="p-3 bg-card border border-border rounded-2xl shadow-xl max-w-3xl mx-auto grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-left">
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Sales</span><kbd className="text-[10px] font-mono bg-blue-900/40 text-blue-300 px-1 py-0.2 rounded">F8</kbd></div>
                <div className="text-xs font-bold text-gray-200">GST Invoice</div>
              </div>
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Purchase</span><kbd className="text-[10px] font-mono bg-purple-900/40 text-purple-300 px-1 py-0.2 rounded">F9</kbd></div>
                <div className="text-xs font-bold text-gray-200">AI Bill Scan</div>
              </div>
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Search</span><kbd className="text-[10px] font-mono bg-zinc-800 text-gray-300 px-1 py-0.2 rounded">⌘K</kbd></div>
                <div className="text-xs font-bold text-gray-200">Command Box</div>
              </div>
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Save</span><kbd className="text-[10px] font-mono bg-green-900/40 text-green-300 px-1 py-0.2 rounded">^A</kbd></div>
                <div className="text-xs font-bold text-gray-200">Instant Post</div>
              </div>
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Masters</span><kbd className="text-[10px] font-mono bg-amber-900/40 text-amber-300 px-1 py-0.2 rounded">Alt+C</kbd></div>
                <div className="text-xs font-bold text-gray-200">On the Fly</div>
              </div>
              <div className="p-2.5 bg-zinc-950/60 rounded-xl border border-zinc-800 space-y-1">
                <div className="flex justify-between items-center"><span className="text-[10px] text-gray-400 uppercase font-semibold">Date</span><kbd className="text-[10px] font-mono bg-zinc-800 text-gray-300 px-1 py-0.2 rounded">F2</kbd></div>
                <div className="text-xs font-bold text-gray-200">Change Period</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Grid with Lucide Icons */}
      <section id="features" className="py-20 border-t border-border bg-zinc-950/40">
        <div className="max-w-7xl mx-auto px-6 space-y-12">
          <div className="text-center max-w-2xl mx-auto space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-widest text-blue-400">Next-Generation Features</h2>
            <p className="text-3xl font-extrabold tracking-tight">Engineered for Rapid Business Operations</p>
            <p className="text-sm text-gray-400">Everything an accountant, business owner, or enterprise operator needs.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Feature 1 */}
            <div className="p-6 bg-card border border-border rounded-2xl space-y-3 shadow-sm hover:border-blue-500/50 transition-all group">
              <div className="w-12 h-12 bg-blue-600/10 text-blue-400 rounded-xl flex items-center justify-center border border-blue-500/20 group-hover:scale-105 transition-transform">
                <Keyboard className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white">Lightning Fast Data Entry</h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                F4-F9 shortcuts you already know. Never touch your mouse. Create masters on the fly with <kbd className="px-1 bg-zinc-800 rounded font-mono">Alt+C</kbd> and post vouchers instantly with <kbd className="px-1 bg-zinc-800 rounded font-mono">Ctrl+A</kbd>.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 bg-card border border-border rounded-2xl space-y-3 shadow-sm hover:border-purple-500/50 transition-all group">
              <div className="w-12 h-12 bg-purple-600/10 text-purple-400 rounded-xl flex items-center justify-center border border-purple-500/20 group-hover:scale-105 transition-transform">
                <Scan className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white">Automated Accounts Payable</h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                Upload a purchase bill photo or PDF. Our AI extracts the items, matches the GSTIN, validates HSN codes, and prepares the voucher with zero manual typing.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 bg-card border border-border rounded-2xl space-y-3 shadow-sm hover:border-green-500/50 transition-all group">
              <div className="w-12 h-12 bg-green-600/10 text-green-400 rounded-xl flex items-center justify-center border border-green-500/20 group-hover:scale-105 transition-transform">
                <FileCheck className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white">Flawless GST Compliance</h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                Auto-calculates CGST, SGST, and IGST based on 2-digit state codes. Automatic inventory stock adjustments and audit-proof double-entry balancing.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="p-6 bg-card border border-border rounded-2xl space-y-3 shadow-sm hover:border-amber-500/50 transition-all group">
              <div className="w-12 h-12 bg-amber-600/10 text-amber-400 rounded-xl flex items-center justify-center border border-amber-500/20 group-hover:scale-105 transition-transform">
                <TrendingUp className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white">AI Business Intelligence</h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                RFM customer value clustering and real-time sales growth forecasting. Identifies whether daily revenue is Booming 🚀, Steady ⚖️, or Slowing down 📉.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Interactive Mockup Section (Visual Anchor with Framer Motion Animation) */}
      <section id="mockup" className="py-24 border-t border-border bg-zinc-950/60 relative overflow-hidden">
        <div className="max-w-6xl mx-auto px-6 space-y-8">
          <div className="text-center space-y-2 max-w-2xl mx-auto">
            <div className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-400 uppercase tracking-wider">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Live Scanning Simulation</span>
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight">See AI OCR & Split-Screen in Action</h2>
            <p className="text-xs text-gray-400">
              Drag-and-drop supplier bills to extract line items, quantities, and GST rates in seconds.
            </p>
          </div>

          {/* Stylized Browser Window */}
          <div className="rounded-2xl border border-zinc-700/80 bg-zinc-900 shadow-2xl overflow-hidden">
            {/* Window Titlebar */}
            <div className="px-4 py-3 bg-zinc-950 border-b border-zinc-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500/80 inline-block"></span>
                <span className="w-3 h-3 rounded-full bg-yellow-500/80 inline-block"></span>
                <span className="w-3 h-3 rounded-full bg-green-500/80 inline-block"></span>
              </div>
              <div className="px-6 py-1 bg-zinc-900 rounded-lg text-[11px] font-mono text-gray-400 border border-zinc-800 flex items-center gap-2">
                <span className="text-green-500">🔒</span>
                <span>https://app.vouch.in/purchases/new</span>
              </div>
              <div className="text-xs text-gray-500 font-mono">F9 Purchase Scan</div>
            </div>

            {/* Split Screen Content inside Mockup */}
            <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-6 bg-zinc-950/80">
              {/* Left: Simulated Original Bill Receipt with Pulse / Scanning Beam */}
              <div className="relative bg-zinc-900 border border-zinc-800 rounded-xl p-5 overflow-hidden flex flex-col justify-between h-[360px]">
                {/* Framer Motion Scanline Beam */}
                <motion.div
                  animate={{
                    top: ["0%", "100%", "0%"],
                  }}
                  transition={{
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                  className="absolute left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-400 to-transparent shadow-[0_0_15px_#3b82f6] pointer-events-none z-10"
                />

                <div className="space-y-4">
                  <div className="flex justify-between items-start border-b border-zinc-800 pb-3">
                    <div>
                      <div className="text-xs font-bold text-white font-mono">TAX INVOICE</div>
                      <div className="text-[11px] text-gray-400">Satyam & Co.</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-mono text-blue-400 font-bold"># G/0015278</div>
                      <div className="text-[10px] text-gray-400 font-mono">Date: 05/11/2025</div>
                    </div>
                  </div>

                  <div className="space-y-2 text-[11px] font-mono text-gray-300">
                    <div className="flex justify-between text-gray-500 text-[10px] border-b border-zinc-800/60 pb-1">
                      <span>ITEM DESCRIPTION</span>
                      <span>HSN</span>
                      <span>QTY</span>
                      <span>AMOUNT</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="font-semibold text-white">TIMING BELTS 760-8MX50</span>
                      <span className="text-gray-400">40103999</span>
                      <span>2.00 PCS</span>
                      <span>₹1,600.00</span>
                    </div>
                    <div className="flex justify-between text-gray-400">
                      <span>CGST (9.00%)</span>
                      <span></span>
                      <span></span>
                      <span>₹144.00</span>
                    </div>
                    <div className="flex justify-between text-gray-400">
                      <span>SGST (9.00%)</span>
                      <span></span>
                      <span></span>
                      <span>₹144.00</span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-zinc-800 flex justify-between items-center text-xs font-bold font-mono">
                  <span className="text-gray-400">GRAND TOTAL:</span>
                  <span className="text-green-400 text-sm">₹ 1,888.00</span>
                </div>
              </div>

              {/* Right: Extracted JSON / Verified ERP Form */}
              <div className="bg-zinc-900 border border-blue-500/30 rounded-xl p-5 space-y-4 flex flex-col justify-between h-[360px]">
                <div className="space-y-3">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-green-500 animate-ping"></span>
                      <span className="text-xs font-bold text-white">AI OCR Extracted Data</span>
                    </div>
                    <span className="px-2 py-0.5 bg-green-500/10 text-green-400 rounded text-[10px] font-bold border border-green-500/20">
                      100% Match
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 bg-zinc-950 rounded-lg border border-zinc-800">
                      <div className="text-[10px] text-gray-400 uppercase">Supplier</div>
                      <div className="font-semibold text-white truncate">Satyam & Co.</div>
                    </div>
                    <div className="p-2 bg-zinc-950 rounded-lg border border-zinc-800">
                      <div className="text-[10px] text-gray-400 uppercase">GSTIN</div>
                      <div className="font-mono text-blue-400 font-bold">09ACHFS9225Q1Z7</div>
                    </div>
                    <div className="p-2 bg-zinc-950 rounded-lg border border-zinc-800">
                      <div className="text-[10px] text-gray-400 uppercase">State Code</div>
                      <div className="font-mono text-gray-200">09 (Uttar Pradesh)</div>
                    </div>
                    <div className="p-2 bg-zinc-950 rounded-lg border border-zinc-800">
                      <div className="text-[10px] text-gray-400 uppercase">Invoice No</div>
                      <div className="font-mono text-purple-400 font-bold">G/0015278</div>
                    </div>
                  </div>

                  <div className="p-2.5 bg-zinc-950 rounded-lg border border-zinc-800 space-y-1 text-xs">
                    <div className="flex justify-between text-[10px] text-gray-400 font-mono">
                      <span>TAXABLE: ₹1,600.00</span>
                      <span>CGST: ₹144.00 | SGST: ₹144.00</span>
                    </div>
                    <div className="flex justify-between text-xs font-bold text-white font-mono">
                      <span>Total Amount:</span>
                      <span className="text-green-400">₹1,888.00</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    href="/purchases/new"
                    className="w-full py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-bold text-center transition-colors shadow-lg"
                  >
                    ✓ Post to Accounting Ledger
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Get Started / Call to Action */}
      <section id="get-started" className="py-20 bg-gradient-to-b from-transparent to-zinc-950 border-t border-border">
        <div className="max-w-4xl mx-auto px-6 text-center space-y-6">
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Ready to streamline your business accounting?
          </h2>
          <p className="text-gray-400 text-sm max-w-xl mx-auto">
            Experience lightning-fast double-entry bookkeeping, automated GST invoices, and AI accounts payable today.
          </p>
          <div className="pt-2 flex items-center justify-center gap-4 flex-wrap">
            <Link
              href={isAuth ? "/dashboard" : "/register"}
              className="px-8 py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-bold shadow-xl shadow-blue-600/25 transition-all inline-flex items-center gap-2 cursor-pointer"
            >
              <span>{isAuth ? "Enter Dashboard" : "Get Started Now"}</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Comprehensive Footer */}
      <footer className="border-t border-border bg-zinc-950 py-12 text-xs text-gray-400">
        <div className="max-w-7xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
          <div className="space-y-2">
            <div className="text-sm font-bold text-white">Vouch</div>
            <p className="text-xs text-gray-500 leading-relaxed">
              Keyboard-first double-entry accounting and AI accounts payable platform for modern businesses.
            </p>
          </div>
          <div className="space-y-2">
            <div className="text-xs font-bold uppercase tracking-wider text-gray-200">Product</div>
            <ul className="space-y-1.5 text-gray-400">
              <li><Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link></li>
              <li><Link href="/sales" className="hover:text-white transition-colors">Sales Invoicing (F8)</Link></li>
              <li><Link href="/purchases" className="hover:text-white transition-colors">AI Bill Scanner (F9)</Link></li>
              <li><Link href="/vouchers/grid" className="hover:text-white transition-colors">High-Density AG Grid</Link></li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="text-xs font-bold uppercase tracking-wider text-gray-200">Resources</div>
            <ul className="space-y-1.5 text-gray-400">
              <li><button onClick={() => setIsHelpOpen(true)} className="hover:text-white transition-colors cursor-pointer">Keyboard Shortcuts (F1)</button></li>
              <li><Link href="/dashboard" className="hover:text-white transition-colors">Documentation</Link></li>
              <li><Link href="/dashboard" className="hover:text-white transition-colors">GST Compliance Guide</Link></li>
              <li><Link href="/~offline" className="hover:text-white transition-colors">Offline Support (PWA)</Link></li>
            </ul>
          </div>
          <div className="space-y-2">
            <div className="text-xs font-bold uppercase tracking-wider text-gray-200">Legal & Trust</div>
            <ul className="space-y-1.5 text-gray-400">
              <li><span className="text-gray-500">Privacy Policy</span></li>
              <li><span className="text-gray-500">Terms of Service</span></li>
              <li><span className="text-gray-500">Strict ACID Compliance</span></li>
              <li><span className="text-gray-500">Zero Cloud Storage Overhead</span></li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 pt-6 border-t border-zinc-900 flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] text-gray-500">
          <div>
            © {new Date().getFullYear()} Vouch Platform. Built for Modern Businesses.
          </div>
          <div className="flex items-center gap-4 font-mono">
            <span>PWA Enabled</span>
            <span>•</span>
            <span>Installable Desktop & Mobile</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
