"use client";
import React, { useState, useRef } from "react";
import * as XLSX from "xlsx";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { getAccessToken } from "@/utils/auth";
import { useToast } from "@/context/ToastContext";
import {
  Upload,
  FileSpreadsheet,
  FileText,
  X,
  CheckCircle2,
  Trash2,
  AlertCircle,
  Tag,
  Search,
} from "lucide-react";

interface PriceListItem {
  name: string;
  selling_price: number;
  purchase_price: number;
  opening_qty: number;
  unit: string;
}

interface PriceListImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  categoryId: string;
  categoryName: string;
  companyId: string;
  existingBrands: string[];
  onImportSuccess: () => void;
}

export default function PriceListImportModal({
  isOpen,
  onClose,
  categoryId,
  categoryName,
  companyId,
  existingBrands,
  onImportSuccess,
}: PriceListImportModalProps) {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [brand, setBrand] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [parsedItems, setParsedItems] = useState<PriceListItem[]>([]);
  const [filterSearch, setFilterSearch] = useState("");

  if (!isOpen) return null;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    await parseFile(selected);
  };

  const parseFile = async (selectedFile: File) => {
    setParsing(true);
    const fileName = selectedFile.name.toLowerCase();

    try {
      if (fileName.endsWith(".csv") || fileName.endsWith(".xlsx") || fileName.endsWith(".xls")) {
        const buffer = await selectedFile.arrayBuffer();
        const workbook = XLSX.read(buffer, { type: "array" });
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];
        const rows: any[] = XLSX.utils.sheet_to_json(sheet, { header: 1 });

        if (rows.length < 2) {
          toast.error("File is empty or missing data rows.");
          setParsing(false);
          return;
        }

        // Detect header row
        const headers: string[] = rows[0].map((h: any) => String(h || "").trim().toLowerCase());
        
        // Find index of Name, MRP/Price, Purchase Price, Quantity
        const nameIdx = headers.findIndex((h) =>
          h.includes("name") || h.includes("item") || h.includes("size") || h.includes("part") || h.includes("description") || h.includes("model")
        );
        const mrpIdx = headers.findIndex((h) =>
          h.includes("mrp") || h.includes("retail") || h.includes("list price") || h.includes("selling") || h.includes("rate") || h.includes("price")
        );
        const purchaseIdx = headers.findIndex((h) =>
          h.includes("purchase") || h.includes("cost") || h.includes("buy")
        );
        const qtyIdx = headers.findIndex((h) =>
          h.includes("qty") || h.includes("quantity") || h.includes("stock")
        );
        const unitIdx = headers.findIndex((h) =>
          h.includes("unit") || h.includes("uom")
        );

        const items: PriceListItem[] = [];
        for (let i = 1; i < rows.length; i++) {
          const row = rows[i];
          if (!row || row.length === 0) continue;

          const rawName = String(nameIdx !== -1 ? row[nameIdx] : row[0] || "").trim();
          if (!rawName) continue;

          const rawMrp = parseFloat(String(mrpIdx !== -1 ? row[mrpIdx] : row[1] || "0").replace(/[^0-9.]/g, "")) || 0;
          const rawPurchase = purchaseIdx !== -1 ? parseFloat(String(row[purchaseIdx] || "0").replace(/[^0-9.]/g, "")) || 0 : 0;
          const rawQty = qtyIdx !== -1 ? parseFloat(String(row[qtyIdx] || "0").replace(/[^0-9.]/g, "")) || 0 : 0;
          const rawUnit = unitIdx !== -1 ? String(row[unitIdx] || "PCS").trim().toUpperCase() : "PCS";

          items.push({
            name: rawName,
            selling_price: rawMrp,
            purchase_price: rawPurchase,
            opening_qty: rawQty,
            unit: rawUnit || "PCS",
          });
        }

        setParsedItems(items);
        toast.success(`Extracted ${items.length} items from ${selectedFile.name}`);
      } else if (fileName.endsWith(".pdf")) {
        // Upload to backend PDF extractor
        const token = getAccessToken();
        const formData = new FormData();
        formData.append("file", selectedFile);

        const res = await axios.post(
          `${API_BASE_URL}/api/v1/inventory/parse-price-list-pdf/${companyId}/`,
          formData,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "multipart/form-data",
            },
          }
        );

        if (res.data.success && res.data.items) {
          setParsedItems(res.data.items);
          toast.success(`Extracted ${res.data.items.length} items from PDF price list`);
        } else {
          toast.error("Failed to parse PDF price list", res.data.error || "No items detected.");
        }
      } else {
        toast.warning("Unsupported file format. Please upload CSV, Excel (.xlsx/.xls), or PDF.");
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to parse file", err.message || "Unknown error");
    } finally {
      setParsing(false);
    }
  };

  const handleImportSubmit = async () => {
    if (!brand.trim()) {
      toast.warning("Please enter or select a Brand name for this price list.");
      return;
    }
    if (parsedItems.length === 0) {
      toast.warning("No items detected to import.");
      return;
    }

    setImporting(true);
    try {
      const token = getAccessToken();
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/inventory/price-list-import/${companyId}/`,
        {
          category_id: categoryId,
          brand: brand.trim(),
          items: parsedItems,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (res.data.success) {
        toast.success(
          `Price list imported successfully!`,
          `Created: ${res.data.created}, Updated: ${res.data.updated} items under ${brand}`
        );
        onImportSuccess();
        onClose();
      } else {
        toast.error("Import failed", res.data.error);
      }
    } catch (err: any) {
      toast.error("Import error", err.response?.data?.error || err.message);
    } finally {
      setImporting(false);
    }
  };

  const updateItemField = (idx: number, field: keyof PriceListItem, val: any) => {
    setParsedItems((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], [field]: val };
      return copy;
    });
  };

  const removeItem = (idx: number) => {
    setParsedItems((prev) => prev.filter((_, i) => i !== idx));
  };

  const filteredItems = parsedItems.filter((i) =>
    i.name.toLowerCase().includes(filterSearch.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity" onClick={onClose} />

      {/* Modal Card */}
      <div className="relative bg-card border border-border/80 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 flex items-center justify-between bg-muted/20">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Import Price List</h3>
              <p className="text-xs text-muted-foreground">
                Upload CSV, Excel, or PDF to batch create or update items in{" "}
                <span className="text-foreground font-semibold">{categoryName}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          
          {/* Step 1: Brand Specification */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5" />
              <span>Step 1: Assign Brand Name for this Price List *</span>
            </label>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <input
                type="text"
                placeholder="e.g. PIX, Fenner, Gates, SKF"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                className="w-full sm:w-72 bg-muted/30 border border-border/70 rounded-lg px-3.5 py-2 text-sm text-foreground font-semibold outline-none focus:ring-2 focus:ring-blue-500 transition-all"
              />
              {existingBrands.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-muted-foreground">Existing brands:</span>
                  {existingBrands.map((b) => (
                    <button
                      key={b}
                      type="button"
                      onClick={() => setBrand(b)}
                      className={`px-2 py-0.5 rounded text-xs font-mono transition-colors cursor-pointer border ${
                        brand === b
                          ? "bg-blue-600 text-white border-blue-500 font-bold"
                          : "bg-muted/60 text-muted-foreground hover:text-foreground border-border/50"
                      }`}
                    >
                      {b}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Step 2: File Upload Area */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" />
              <span>Step 2: Upload Price List (CSV, Excel .xlsx / .xls, or PDF)</span>
            </label>
            
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border/70 hover:border-blue-500/60 bg-muted/10 hover:bg-muted/30 rounded-xl p-6 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv, .xlsx, .xls, .pdf"
                onChange={handleFileChange}
                className="hidden"
              />
              <div className="w-12 h-12 rounded-2xl bg-muted/60 text-muted-foreground flex items-center justify-center">
                {file ? <FileText className="w-6 h-6 text-blue-400" /> : <Upload className="w-6 h-6" />}
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {file ? file.name : "Click to browse or drop price list file here"}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Supports CSV, Excel spreadsheets (.xlsx, .xls), and PDF manufacturer catalogs
                </p>
              </div>
              {parsing && (
                <div className="text-xs text-blue-400 font-medium animate-pulse mt-1">
                  Parsing price list items...
                </div>
              )}
            </div>
          </div>

          {/* Step 3: Parsed Items Preview Table */}
          {parsedItems.length > 0 && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <h4 className="text-sm font-bold text-foreground">
                    Parsed Items ({parsedItems.length} items detected)
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Verify item names, MRPs, and optional purchase prices before importing
                  </p>
                </div>

                <div className="relative w-56">
                  <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search in preview..."
                    value={filterSearch}
                    onChange={(e) => setFilterSearch(e.target.value)}
                    className="w-full bg-muted/30 border border-border/70 rounded-md pl-8 pr-2.5 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="border border-border/60 rounded-xl overflow-hidden max-h-64 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-muted/50 text-muted-foreground sticky top-0 border-b border-border/60">
                    <tr>
                      <th className="p-2.5 font-medium">Item Name / Size</th>
                      <th className="p-2.5 font-medium w-28">MRP / List Price (₹)</th>
                      <th className="p-2.5 font-medium w-28">Purchase Price (₹)</th>
                      <th className="p-2.5 font-medium w-20">Opening Qty</th>
                      <th className="p-2.5 font-medium w-16">Unit</th>
                      <th className="p-2.5 font-medium text-center w-12">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {filteredItems.slice(0, 100).map((item, idx) => (
                      <tr key={idx} className="hover:bg-muted/20">
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.name}
                            onChange={(e) => updateItemField(idx, "name", e.target.value)}
                            className="w-full bg-transparent text-foreground font-medium outline-none"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="number"
                            step="0.01"
                            value={item.selling_price}
                            onChange={(e) => updateItemField(idx, "selling_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/30 border border-border/50 rounded px-1.5 py-1 font-mono font-bold text-foreground outline-none"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="number"
                            step="0.01"
                            value={item.purchase_price}
                            onChange={(e) => updateItemField(idx, "purchase_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/30 border border-border/50 rounded px-1.5 py-1 font-mono text-muted-foreground outline-none"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="number"
                            value={item.opening_qty}
                            onChange={(e) => updateItemField(idx, "opening_qty", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/30 border border-border/50 rounded px-1.5 py-1 font-mono text-muted-foreground outline-none"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.unit}
                            onChange={(e) => updateItemField(idx, "unit", e.target.value.toUpperCase())}
                            className="w-full bg-muted/30 border border-border/50 rounded px-1.5 py-1 font-mono text-xs text-muted-foreground outline-none"
                          />
                        </td>
                        <td className="p-2 text-center">
                          <button
                            type="button"
                            onClick={() => removeItem(idx)}
                            className="p-1 text-muted-foreground hover:text-rose-400 transition-colors"
                            title="Remove row"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border/60 bg-muted/20 flex items-center justify-between">
          <div className="text-xs text-muted-foreground">
            {parsedItems.length > 0 && (
              <span>
                Ready to import <strong>{parsedItems.length}</strong> items under brand{" "}
                <strong>{brand || "(No brand entered)"}</strong>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted/60 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={importing || parsedItems.length === 0 || !brand.trim()}
              onClick={handleImportSubmit}
              className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{importing ? "Importing..." : `Import ${parsedItems.length} Items`}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
