"use client";
import React, { useState } from "react";
import { usePathname } from "next/navigation";
import { useShortcuts } from "@/context/ShortcutContext";

export default function HelpModal() {
  const { isHelpOpen, setIsHelpOpen, startTour } = useShortcuts();
  const pathname = usePathname();
  const [tab, setTab] = useState<"SHORTCUTS" | "GUIDE">("SHORTCUTS");
  const [expandedTopic, setExpandedTopic] = useState<string>("sales");

  if (!isHelpOpen) return null;

  const isSalesPage = pathname.includes("/sales");
  const isPurchasePage = pathname.includes("/purchases");
  const isGridPage = pathname.includes("/vouchers/grid");
  const isVoucherPage = isSalesPage || isPurchasePage || isGridPage || pathname.includes("/vouchers");

  const categories = [
    {
      title: "Voucher Types (Standard F-Keys)",
      shortcuts: [
        { key: "F4", label: "Contra Voucher", desc: "Bank & cash transfers", active: pathname.includes("CONTRA") },
        { key: "F5", label: "Payment Voucher", desc: "Pay suppliers & expenses", active: pathname.includes("PAYMENT") },
        { key: "F6", label: "Receipt Voucher", desc: "Receive money from customers", active: pathname.includes("RECEIPT") },
        { key: "F7", label: "Journal Voucher", desc: "Adjustments & non-cash entries", active: pathname.includes("JOURNAL") },
        { key: "F8", label: "Sales Invoice", desc: "Customer GST bill generation", active: isSalesPage },
        { key: "F9", label: "Purchase Invoice", desc: "Inward bill & AI Scanner", active: isPurchasePage },
      ],
    },
    {
      title: "Fast Keyboard Actions",
      shortcuts: [
        { key: "Ctrl + A", label: "Accept / Save Form", desc: "Instantly submit without mouse", active: isVoucherPage },
        { key: "Alt + C", label: "Create on the Fly", desc: "Add new Customer/Product inside form", active: isVoucherPage },
        { key: "Alt + P", label: "Print Active Invoice", desc: "Generate GST print preview", active: isSalesPage || isPurchasePage },
        { key: "Tab / Enter", label: "Next Cell / Field", desc: "Move between input boxes", active: isGridPage || isVoucherPage },
      ],
    },
    {
      title: "System & Navigation",
      shortcuts: [
        { key: "Ctrl + K", label: "Command Palette", desc: "Instant search for ledgers & items", active: true },
        { key: "F2", label: "Change Working Date", desc: "Adjust current voucher date", active: true },
        { key: "Esc", label: "Back / Close", desc: "Step back or dismiss popup", active: true },
        { key: "F1", label: "Help & Tutorials", desc: "Toggle this guide anytime", active: true },
      ],
    },
  ];

  const tutorials = [
    {
      id: "sales",
      title: "🧾 1. How to Create a Sales Invoice (F8)",
      content: (
        <div className="space-y-2 text-xs text-gray-300">
          <p><strong>Step 1:</strong> Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">F8</kbd> from any screen to open the Sales Invoice page.</p>
          <p><strong>Step 2:</strong> Select your <strong>Customer (Party)</strong>. If the customer is new, simply press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Alt + C</kbd> to add them right there.</p>
          <p><strong>Step 3:</strong> Enter your line items, quantities, and rates. The system automatically detects whether it's local (CGST + SGST) or out-of-state (IGST) and computes taxes.</p>
          <p><strong>Step 4:</strong> Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Ctrl + A</kbd> to immediately save and post the invoice to your accounts and deduct inventory stock!</p>
        </div>
      ),
    },
    {
      id: "ocr",
      title: "🤖 2. How the AI Bill Scanner Works (F9)",
      content: (
        <div className="space-y-2 text-xs text-gray-300">
          <p><strong>Step 1:</strong> Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">F9</kbd> to open Purchase Invoices.</p>
          <p><strong>Step 2:</strong> Click <strong>Browse Document</strong> or drop a PDF/photo of your vendor bill.</p>
          <p><strong>Step 3:</strong> In a few seconds, our AI reads the bill in-memory (zero privacy risks) and opens a <strong>Split-Screen View</strong>: your original document on the left, and pre-filled invoice fields on the right.</p>
          <p><strong>Step 4:</strong> Review the extracted line items, modify anything if needed, and click <strong>Approve & Save</strong> to update accounts and add stock.</p>
        </div>
      ),
    },
    {
      id: "altc",
      title: "✨ 3. Create Masters on the Fly (Alt + C)",
      content: (
        <div className="space-y-2 text-xs text-gray-300">
          <p>Whenever you are creating an invoice and realize a customer or product does not exist yet:</p>
          <p>• Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Alt + C</kbd> anywhere on the screen.</p>
          <p>• A quick popup lets you enter the Customer Name, GSTIN, State, or Product HSN and Rate.</p>
          <p>• Hit Save, and the new item is <strong>automatically selected in your active invoice</strong> without losing your work.</p>
        </div>
      ),
    },
    {
      id: "analytics",
      title: "📈 4. Understanding Growth Status & Customer Groups",
      content: (
        <div className="space-y-2 text-xs text-gray-300">
          <p><strong>• Sales Pace (Booming / Constant / Declining):</strong> We monitor your daily revenue trajectory. If sales are growing faster than previous days, your status is <strong>Booming 🚀</strong>. If sales are slowing down, it alerts you as <strong>Declining 📉</strong> so you can follow up with buyers.</p>
          <p><strong>• Customer Value Groups:</strong></p>
          <p className="pl-2">⭐ <strong>High Value (VIP):</strong> Your most active customers with highest total spend. Prioritize fast fulfillment for them!</p>
          <p className="pl-2">⚡ <strong>Medium Value:</strong> Reliable repeat buyers.</p>
          <p className="pl-2">💤 <strong>Low Value:</strong> Haven't purchased in a while or small volume. Call them to re-engage.</p>
        </div>
      ),
    },
    {
      id: "grid",
      title: "⌨️ 5. Pure Keyboard Data Entry (AG Grid)",
      content: (
        <div className="space-y-2 text-xs text-gray-300">
          <p>Visit <strong>AG Grid Voucher Entry</strong> from the sidebar for fast multi-line journals or payments:</p>
          <p>• Use <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Tab</kbd> or <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Enter</kbd> to move from cell to cell.</p>
          <p>• Type <strong>Dr</strong> or <strong>Cr</strong> to switch column focus.</p>
          <p>• Watch the live <strong>Balanced</strong> indicator at the bottom bar.</p>
          <p>• Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-white">Ctrl + A</kbd> to save immediately.</p>
        </div>
      ),
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-200 p-4">
      <div className="w-full max-w-3xl bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-white max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 bg-zinc-950">
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-1 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-md text-xs font-mono font-bold">
              F1
            </span>
            <div>
              <h3 className="text-xl font-bold text-white">User Guide & Shortcuts Hub</h3>
              <p className="text-xs text-gray-400">Everything you need to master your accounting system</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setIsHelpOpen(false);
                startTour();
              }}
              className="px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white rounded-lg text-xs font-bold shadow-md transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <span>🚀 Start Interactive Tour</span>
            </button>
            <button
              onClick={() => setIsHelpOpen(false)}
              className="text-gray-400 hover:text-white text-sm font-bold px-2 py-1 cursor-pointer"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-zinc-800 bg-zinc-950/60 px-6 pt-2">
          <button
            onClick={() => setTab("SHORTCUTS")}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              tab === "SHORTCUTS"
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            ⌨️ Keyboard Shortcuts Cheat Sheet
          </button>
          <button
            onClick={() => setTab("GUIDE")}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition-all cursor-pointer ${
              tab === "GUIDE"
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            📚 How-To Tutorials & System Guide
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {tab === "SHORTCUTS" && (
            <div className="space-y-6">
              {categories.map((cat, idx) => (
                <div key={idx} className="space-y-3">
                  <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider border-b border-zinc-800 pb-1">
                    {cat.title}
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {cat.shortcuts.map((sc, sIdx) => (
                      <div
                        key={sIdx}
                        className={`flex items-center justify-between p-3 rounded-xl border transition-all ${
                          sc.active
                            ? "bg-blue-950/30 border-blue-500/40 shadow-sm"
                            : "bg-zinc-950/60 border-zinc-800"
                        }`}
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-gray-100">{sc.label}</span>
                            {sc.active && (
                              <span className="px-1.5 py-0.2 bg-blue-500/20 text-blue-300 text-[10px] rounded font-semibold">
                                On This Page
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-gray-400">{sc.desc}</div>
                        </div>
                        <kbd className="px-2.5 py-1 bg-zinc-800 border border-zinc-700 text-gray-200 font-mono text-xs rounded-md shadow-inner whitespace-nowrap">
                          {sc.key}
                        </kbd>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "GUIDE" && (
            <div className="space-y-4">
              <div className="p-3 bg-blue-950/30 border border-blue-500/30 rounded-xl text-xs text-blue-300 flex items-center justify-between">
                <span>💡 Click on any tutorial below to learn how to use that feature quickly.</span>
              </div>

              {tutorials.map((item) => (
                <div
                  key={item.id}
                  className="bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden shadow-sm"
                >
                  <button
                    onClick={() => setExpandedTopic(expandedTopic === item.id ? "" : item.id)}
                    className="w-full text-left p-4 font-bold text-sm text-gray-200 hover:text-white flex items-center justify-between transition-colors cursor-pointer"
                  >
                    <span>{item.title}</span>
                    <span className="text-gray-400 text-xs">{expandedTopic === item.id ? "▲ Collapse" : "▼ Read"}</span>
                  </button>
                  {expandedTopic === item.id && (
                    <div className="p-4 pt-0 border-t border-zinc-800/80 mt-1">
                      {item.content}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-zinc-950 border-t border-zinc-800 text-xs text-gray-400 flex items-center justify-between">
          <span>Press <kbd className="px-1.5 py-0.5 bg-zinc-800 rounded font-mono text-zinc-300">Esc</kbd> anytime to close</span>
          <span className="font-mono text-zinc-500">Vouch Keyboard Platform</span>
        </div>
      </div>
    </div>
  );
}
