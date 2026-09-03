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
  Tag,
  Search,
  Percent,
  Calendar,
  Layers,
  Sparkles,
} from "lucide-react";

interface PriceListItem {
  name: string;
  selling_price: number;
  purchase_price: number;
  opening_qty: number;
  unit: string;
  section?: string;
  case_qty?: number;
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
  const [effectiveDate, setEffectiveDate] = useState("");
  const [parsingEngine, setParsingEngine] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [parsedItems, setParsedItems] = useState<PriceListItem[]>([]);
  const [filterSearch, setFilterSearch] = useState("");
  const [discountPercent, setDiscountPercent] = useState<number>(30);

  if (!isOpen) return null;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    await parseFile(selected);
  };

  const parseFile = async (selectedFile: File) => {
    setParsing(true);
    setParsingEngine(null);
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

        const headers: string[] = rows[0].map((h: any) => String(h || "").trim().toLowerCase());

        const nameIdx = headers.findIndex((h) =>
          h.includes("name") || h.includes("item") || h.includes("size") || h.includes("part") || h.includes("bearing") || h.includes("model")
        );
        const mrpIdx = headers.findIndex((h) =>
          h.includes("mrp") || h.includes("retail") || h.includes("list price") || h.includes("selling") || h.includes("rate") || h.includes("price")
        );
        const purchaseIdx = headers.findIndex((h) =>
          h.includes("purchase") || h.includes("cost") || h.includes("buy")
        );
        const qtyIdx = headers.findIndex((h) =>
          h.includes("stock") || h.includes("qty") || h.includes("quantity")
        );
        const caseQtyIdx = headers.findIndex((h) =>
          h.includes("case") || h.includes("box") || h.includes("pack") || h.includes("moq")
        );
        const sectionIdx = headers.findIndex((h) =>
          h.includes("section") || h.includes("category") || h.includes("group") || h.includes("type") || h.includes("desc")
        );
        const unitIdx = headers.findIndex((h) => h.includes("unit") || h.includes("uom"));

        const items: PriceListItem[] = [];
        for (let i = 1; i < rows.length; i++) {
          const row = rows[i];
          if (!row || row.length === 0) continue;

          const rawName = nameIdx !== -1 ? String(row[nameIdx] || "").trim() : "";
          if (!rawName) continue;

          const mrpVal = mrpIdx !== -1 ? parseFloat(String(row[mrpIdx] || "0").replace(/[^0-9.]/g, "")) || 0 : 0;
          const purchaseVal = purchaseIdx !== -1 ? parseFloat(String(row[purchaseIdx] || "0").replace(/[^0-9.]/g, "")) || 0 : mrpVal * 0.70;
          const stockVal = qtyIdx !== -1 ? parseFloat(String(row[qtyIdx] || "0").replace(/[^0-9.]/g, "")) || 0 : 0;
          const caseQtyVal = caseQtyIdx !== -1 ? parseInt(String(row[caseQtyIdx] || "1").replace(/[^0-9]/g, "")) || 1 : 1;
          const sectionVal = sectionIdx !== -1 ? String(row[sectionIdx] || "").trim() : "";
          const unitVal = unitIdx !== -1 ? String(row[unitIdx] || "PCS").trim().toUpperCase() : "PCS";

          items.push({
            name: rawName,
            selling_price: mrpVal,
            purchase_price: Math.round(purchaseVal * 100) / 100,
            opening_qty: stockVal,
            case_qty: caseQtyVal,
            section: sectionVal,
            unit: unitVal || "PCS",
          });
        }

        setParsedItems(items);
        setParsingEngine("Spreadsheet Importer");
        toast.success(`Extracted ${items.length} items from spreadsheet`);
      } else if (fileName.endsWith(".pdf")) {
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
          const rawItems = res.data.items.map((it: any) => ({
            name: it.name || it.item_name,
            selling_price: parseFloat(it.mrp || it.selling_price || 0),
            purchase_price: parseFloat(it.purchase_price || (it.mrp ? it.mrp * 0.70 : 0)),
            opening_qty: parseFloat(it.opening_qty || 0),
            case_qty: parseInt(it.case_qty || 1),
            section: it.section || "",
            unit: it.unit || "PCS",
          }));

          setParsedItems(rawItems);
          if (res.data.brand && !brand) {
            setBrand(res.data.brand);
          }
          if (res.data.effective_date) {
            setEffectiveDate(res.data.effective_date);
          }
          setParsingEngine(res.data.source === "AI_GEMINI" ? "Gemini AI Document Model" : "Multi-Column Industrial Parser");
          toast.success(`Extracted ${rawItems.length} items from PDF price list`);
        } else {
          toast.error("Failed to parse PDF price list", res.data.error || "No items detected.");
        }
      } else {
        toast.warning("Unsupported format. Please upload CSV, Excel (.xlsx/.xls), or PDF.");
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to parse file", err.message || "Unknown error");
    } finally {
      setParsing(false);
    }
  };

  const handleApplyTradeDiscount = () => {
    if (parsedItems.length === 0) return;
    const factor = (100 - discountPercent) / 100;
    setParsedItems((prev) =>
      prev.map((it) => ({
        ...it,
        purchase_price: Math.round(it.selling_price * factor * 100) / 100,
      }))
    );
    toast.success(`Updated purchase prices with ${discountPercent}% trade discount from MRP!`);
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
    i.name.toLowerCase().includes(filterSearch.toLowerCase()) ||
    (i.section && i.section.toLowerCase().includes(filterSearch.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity" onClick={onClose} />

      {/* Modal Card */}
      <div className="relative bg-card border border-border/80 w-full max-w-5xl rounded-2xl shadow-2xl overflow-hidden z-10 flex flex-col max-h-[92vh] animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border/60 flex items-center justify-between bg-muted/20">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center justify-center">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Import Manufacturer Price List</h3>
              <p className="text-xs text-muted-foreground">
                Upload CSV, Excel, or PDF catalog to extract items into{" "}
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
              <span>Step 1: Brand Specification *</span>
            </label>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <input
                type="text"
                placeholder="e.g. PIX, NBC, Fenner, Gates, SKF"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                className="w-full sm:w-72 bg-muted/30 border border-border/70 rounded-xl px-3.5 py-2 text-sm text-foreground font-semibold outline-none focus:ring-2 focus:ring-blue-500 transition-all"
              />
              {existingBrands.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-muted-foreground">Existing:</span>
                  {existingBrands.map((b) => (
                    <button
                      key={b}
                      type="button"
                      onClick={() => setBrand(b)}
                      className={`px-2 py-0.5 rounded-lg text-xs font-mono transition-colors cursor-pointer border ${
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
              <span>Step 2: Upload Catalog / Price List (PDF, Excel, or CSV)</span>
            </label>
            
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border/70 hover:border-blue-500/60 bg-muted/10 hover:bg-muted/30 rounded-2xl p-6 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2"
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
                  Supports multi-column manufacturer catalogs (PIX V-Belts, NBC Bearings, SKF), spreadsheets & CSVs
                </p>
              </div>
              {parsing && (
                <div className="text-xs text-blue-400 font-medium animate-pulse mt-1 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Extracting items, prices, case quantities & sections...</span>
                </div>
              )}
            </div>
          </div>

          {/* Extracted Metadata Banner */}
          {(effectiveDate || parsingEngine) && (
            <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                {effectiveDate && (
                  <span className="flex items-center gap-1 text-blue-400 font-medium">
                    <Calendar className="w-3.5 h-3.5" />
                    <span>Effective: {effectiveDate}</span>
                  </span>
                )}
              </div>
              {parsingEngine && (
                <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded text-[10px] font-semibold border border-blue-500/30">
                  Engine: {parsingEngine}
                </span>
              )}
            </div>
          )}

          {/* Step 3: Parsed Items Preview Table */}
          {parsedItems.length > 0 && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between gap-4 flex-wrap bg-muted/20 p-3 rounded-xl border border-border/60">
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <span>Parsed Items ({parsedItems.length})</span>
                    <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded text-[10px] font-bold border border-emerald-500/20">
                      Ready to Import
                    </span>
                  </h4>
                  <p className="text-[11px] text-muted-foreground">
                    Review item sizes, sections, MRPs, and adjust purchase trade discounts
                  </p>
                </div>

                {/* Bulk Trade Discount Tool */}
                <div className="flex items-center gap-2 bg-muted/40 p-1.5 rounded-lg border border-border/50">
                  <Percent className="w-3.5 h-3.5 text-blue-400" />
                  <span className="text-xs text-muted-foreground">Trade Disc:</span>
                  <input
                    type="number"
                    value={discountPercent}
                    onChange={(e) => setDiscountPercent(parseFloat(e.target.value) || 0)}
                    className="w-12 bg-muted/50 border border-border/70 text-foreground text-xs px-1 py-0.5 rounded text-center font-bold outline-none"
                  />
                  <span className="text-xs text-muted-foreground">%</span>
                  <button
                    type="button"
                    onClick={handleApplyTradeDiscount}
                    className="px-2 py-0.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-bold transition-colors cursor-pointer"
                  >
                    Apply to All
                  </button>
                </div>

                {/* Search in preview */}
                <div className="relative w-52">
                  <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search size, code, section..."
                    value={filterSearch}
                    onChange={(e) => setFilterSearch(e.target.value)}
                    className="w-full bg-muted/40 border border-border/70 rounded-lg pl-8 pr-2.5 py-1 text-xs text-foreground outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>

              {/* Items Grid */}
              <div className="border border-border/70 rounded-xl overflow-hidden max-h-72 overflow-y-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-muted/50 text-muted-foreground sticky top-0 border-b border-border/60 text-[10px] uppercase font-semibold">
                    <tr>
                      <th className="p-2.5 font-medium">Item Name / Size</th>
                      <th className="p-2.5 font-medium">Section / Description</th>
                      <th className="p-2.5 font-medium w-28 text-right">MRP / List Price (₹)</th>
                      <th className="p-2.5 font-medium w-28 text-right">Purchase Price (₹)</th>
                      <th className="p-2.5 font-medium w-20 text-center">Case Qty</th>
                      <th className="p-2.5 font-medium w-16 text-center">Unit</th>
                      <th className="p-2.5 font-medium text-center w-12">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                    {filteredItems.slice(0, 150).map((item, idx) => (
                      <tr key={idx} className="hover:bg-muted/20">
                        {/* Name */}
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.name}
                            onChange={(e) => updateItemField(idx, "name", e.target.value)}
                            className="w-full bg-transparent text-foreground font-bold outline-none"
                          />
                        </td>

                        {/* Section / Category */}
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.section || ""}
                            onChange={(e) => updateItemField(idx, "section", e.target.value)}
                            placeholder="Section / Specs"
                            className="w-full bg-transparent text-muted-foreground text-[11px] outline-none"
                          />
                        </td>

                        {/* MRP */}
                        <td className="p-2 text-right">
                          <input
                            type="number"
                            step="0.01"
                            value={item.selling_price}
                            onChange={(e) => updateItemField(idx, "selling_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono font-bold text-foreground text-right outline-none"
                          />
                        </td>

                        {/* Purchase Price */}
                        <td className="p-2 text-right">
                          <input
                            type="number"
                            step="0.01"
                            value={item.purchase_price}
                            onChange={(e) => updateItemField(idx, "purchase_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono text-emerald-400 font-semibold text-right outline-none"
                          />
                        </td>

                        {/* Case Qty */}
                        <td className="p-2 text-center">
                          <input
                            type="number"
                            value={item.case_qty || 1}
                            onChange={(e) => updateItemField(idx, "case_qty", parseInt(e.target.value) || 1)}
                            className="w-16 bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono text-center text-muted-foreground outline-none"
                          />
                        </td>

                        {/* Unit */}
                        <td className="p-2 text-center">
                          <input
                            type="text"
                            value={item.unit}
                            onChange={(e) => updateItemField(idx, "unit", e.target.value.toUpperCase())}
                            className="w-12 bg-muted/40 border border-border/50 rounded px-1 py-1 font-mono text-[11px] text-center text-muted-foreground outline-none"
                          />
                        </td>

                        {/* Action */}
                        <td className="p-2 text-center">
                          <button
                            type="button"
                            onClick={() => removeItem(idx)}
                            className="p-1 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
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
              {filteredItems.length > 150 && (
                <p className="text-[11px] text-muted-foreground text-right italic">
                  Showing first 150 of {filteredItems.length} items in preview. All will be imported upon submission.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border/60 bg-muted/20 flex items-center justify-between">
          <div className="text-xs text-muted-foreground">
            {parsedItems.length > 0 && (
              <span>
                Ready to import <strong>{parsedItems.length}</strong> items under brand{" "}
                <strong className="text-foreground">{brand || "(Enter brand name above)"}</strong>
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
              className="px-5 py-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{importing ? "Importing..." : `Import ${parsedItems.length} Items to Inventory`}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
