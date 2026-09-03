"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { getAccessToken } from "@/utils/auth";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [ledgers, setLedgers] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
      fetchQuickData();
    }
  }, [isOpen]);

  const fetchQuickData = async () => {
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const cid = compRes.data.data?.[0]?.id;
      if (!cid) return;

      const [ledgersRes, productsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cid}/`, { headers }).catch(() => ({ data: { data: [] } })),
        axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cid}/`, { headers }).catch(() => ({ data: { data: [] } })),
      ]);

      setLedgers(ledgersRes.data?.data || []);
      setProducts(productsRes.data?.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  const navActions = [
    { label: "Create Sales Invoice", shortcut: "F8", action: () => router.push("/sales/new") },
    { label: "Create Purchase Invoice (with AI OCR)", shortcut: "F9", action: () => router.push("/purchases/new") },
    { label: "B2B Network EDI Inbox (Auto-Handshake)", shortcut: "EDI", action: () => router.push("/network/inbox") },
    { label: "Export to Tally XML (TallyPrime & CA Guide)", shortcut: "Alt+O", action: () => router.push("/export/tally") },
    { label: "View Dashboard & AI Analytics", shortcut: "D", action: () => router.push("/dashboard") },
    { label: "Inventory Products Master", shortcut: "I", action: () => router.push("/inventory") },
    { label: "Parties & Customers List", shortcut: "P", action: () => router.push("/parties") },
    { label: "Payments & Receipts Vouchers", shortcut: "V", action: () => router.push("/vouchers") },
    { label: "Profile & Company Settings", shortcut: "S", action: () => router.push("/settings") },
  ];

  const filteredNav = navActions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()));
  const filteredLedgers = ledgers.filter((l) => l.name.toLowerCase().includes(query.toLowerCase())).slice(0, 5);
  const filteredProducts = products.filter((p) => p.name.toLowerCase().includes(query.toLowerCase()) || p.sku?.toLowerCase().includes(query.toLowerCase())).slice(0, 5);

  const allItems = [
    ...filteredNav.map((item) => ({ type: "action", ...item })),
    ...filteredLedgers.map((item) => ({
      type: "ledger",
      label: item.name,
      subtext: `${item.group_name || item.group || 'Ledger'} • Bal: ₹${item.current_balance || 0}`,
      action: () => router.push(`/parties`),
    })),
    ...filteredProducts.map((item) => ({
      type: "product",
      label: item.name,
      subtext: `SKU: ${item.sku} • Stock: ${item.stock_quantity || 0} ${item.unit || 'PCS'} • ₹${item.selling_price || 0}`,
      action: () => router.push(`/inventory`),
    })),
  ];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (allItems.length || 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + (allItems.length || 1)) % (allItems.length || 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const selected = allItems[selectedIndex];
      if (selected) {
        selected.action();
        onClose();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-2xl bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-white">
        {/* Search Input */}
        <div className="flex items-center px-4 border-b border-zinc-800">
          <svg className="w-5 h-5 text-gray-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type a command, ledger, or product name..."
            className="w-full py-4 bg-transparent text-white placeholder-gray-500 focus:outline-none text-base font-medium"
          />
          <kbd className="px-2 py-1 text-xs font-mono text-gray-400 bg-zinc-800 rounded border border-zinc-700">ESC</kbd>
        </div>

        {/* Results List */}
        <div className="max-h-96 overflow-y-auto p-2 space-y-1">
          {allItems.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">No commands, ledgers, or products matching "{query}"</div>
          ) : (
            allItems.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={idx}
                  onClick={() => {
                    item.action();
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                    isSelected ? "bg-blue-600 text-white font-medium" : "hover:bg-zinc-800/80 text-gray-200"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-xs px-2 py-0.5 rounded uppercase font-mono bg-zinc-800 text-gray-300 border border-zinc-700">
                      {item.type}
                    </span>
                    <div>
                      <div className="text-sm">{item.label}</div>
                      {(item as any).subtext && (
                        <div className={`text-xs ${isSelected ? "text-blue-200" : "text-gray-400"}`}>
                          {(item as any).subtext}
                        </div>
                      )}
                    </div>
                  </div>

                  {(item as any).shortcut && (
                    <kbd className={`px-2 py-0.5 text-xs font-mono rounded ${
                      isSelected ? "bg-blue-700 text-white" : "bg-zinc-800 text-gray-400 border border-zinc-700"
                    }`}>
                      {(item as any).shortcut}
                    </kbd>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts helper */}
        <div className="px-4 py-2 bg-zinc-950/80 border-t border-zinc-800 text-xs text-gray-400 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span>↑↓ Navigate</span>
            <span>↵ Select</span>
            <span>ESC Close</span>
          </div>
          <div className="font-mono text-zinc-500">Vouch Keyboard Engine</div>
        </div>
      </div>
    </div>
  );
}
