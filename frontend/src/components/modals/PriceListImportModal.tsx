"use client";
import React, { useState, useRef, useEffect, useMemo } from "react";
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
  Sparkles,
  KeyRound,
} from "lucide-react";

interface PriceListItem {
  id?: string;
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
  const [selectedSection, setSelectedSection] = useState<string>("ALL");
  const [previewPage, setPreviewPage] = useState<number>(1);
  const PAGE_SIZE = 100;
  const [filterSearch, setFilterSearch] = useState("");
  const [discountPercent, setDiscountPercent] = useState<number>(30);
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [showKeyInput, setShowKeyInput] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedKey = localStorage.getItem("vouch_gemini_key") || "";
      if (savedKey) setGeminiApiKey(savedKey);
    }
  }, []);

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

        const KEY_TERMS = [
          "section", "size", "price", "mrp", "rate", "cost", "stock", "qty", "quantity",
          "item", "name", "bearing", "part", "sku", "code", "unit", "description", "value"
        ];

        let bestHeaderIdx = 0;
        let bestScore = 0;

        for (let r = 0; r < Math.min(25, rows.length); r++) {
          const row = rows[r];
          if (!row || !Array.isArray(row)) continue;
          let score = 0;
          for (const cell of row) {
            const cellClean = String(cell || "").trim().toLowerCase();
            if (KEY_TERMS.some((term) => cellClean.includes(term))) {
              score++;
            }
          }
          if (score > bestScore) {
            bestScore = score;
            bestHeaderIdx = r;
          }
        }

        const headers: string[] = (rows[bestHeaderIdx] || []).map((h: any) =>
          String(h || "").trim().toLowerCase()
        );

        let sectionIdx = -1;
        let sizeIdx = -1;
        let nameIdx = -1;
        let mrpIdx = -1;
        let purchaseIdx = -1;
        let qtyIdx = -1;
        let caseQtyIdx = -1;
        let unitIdx = -1;

        for (let c = 0; c < headers.length; c++) {
          const h = headers[c];
          if (h.includes("section")) sectionIdx = c;
          else if (h.includes("size")) sizeIdx = c;
          else if (["item", "name", "part", "bearing", "product", "description", "title"].some((k) => h.includes(k))) {
            if (nameIdx === -1) nameIdx = c;
          } else if (["mrp", "retail", "list price", "unit price", "selling", "price", "rate"].some((k) => h.includes(k))) {
            if (mrpIdx === -1) mrpIdx = c;
          } else if (["purchase", "cost", "buy"].some((k) => h.includes(k))) {
            purchaseIdx = c;
          } else if (["quantity in stock", "stock", "qty", "quantity"].some((k) => h.includes(k))) {
            if (qtyIdx === -1) qtyIdx = c;
          } else if (["case", "box", "pack", "moq"].some((k) => h.includes(k))) {
            caseQtyIdx = c;
          } else if (["unit", "uom"].some((k) => h.includes(k))) {
            unitIdx = c;
          }
        }

        const items: PriceListItem[] = [];
        for (let i = bestHeaderIdx + 1; i < rows.length; i++) {
          const row = rows[i];
          if (!row || !Array.isArray(row) || !row.some((cell: any) => cell !== null && cell !== undefined && cell !== "")) continue;

          let rawName = "";
          const sectionVal = sectionIdx !== -1 && sectionIdx < row.length ? String(row[sectionIdx] || "").trim() : "";
          const sizeVal = sizeIdx !== -1 && sizeIdx < row.length ? String(row[sizeIdx] || "").trim() : "";

          if (sectionVal && sizeVal) {
            rawName = `${sectionVal} ${sizeVal}`.trim();
          } else if (nameIdx !== -1 && nameIdx < row.length && String(row[nameIdx] || "").trim()) {
            rawName = String(row[nameIdx] || "").trim();
          } else if (sizeVal) {
            rawName = sizeVal;
          } else if (sectionVal) {
            rawName = sectionVal;
          } else {
            for (let c = 0; c < row.length; c++) {
              const val = String(row[c] || "").trim();
              if (val && isNaN(Number(val))) {
                rawName = val;
                break;
              }
            }
          }

          if (!rawName || ["total", "subtotal", "reorder", "discontinued"].includes(rawName.toLowerCase())) {
            continue;
          }

          let mrpVal = 0;
          if (mrpIdx !== -1 && mrpIdx < row.length) {
            const cleanP = String(row[mrpIdx] || "").replace(/[^0-9.]/g, "");
            mrpVal = parseFloat(cleanP) || 0;
          }

          let purchaseVal = mrpVal * 0.70;
          if (purchaseIdx !== -1 && purchaseIdx < row.length) {
            const cleanCost = String(row[purchaseIdx] || "").replace(/[^0-9.]/g, "");
            const parsedCost = parseFloat(cleanCost);
            if (!isNaN(parsedCost) && parsedCost > 0) {
              purchaseVal = parsedCost;
            }
          }

          let stockVal = 0;
          if (qtyIdx !== -1 && qtyIdx < row.length) {
            const cleanS = String(row[qtyIdx] || "").replace(/[^0-9.]/g, "");
            stockVal = parseFloat(cleanS) || 0;
          }

          const caseQtyVal = caseQtyIdx !== -1 && caseQtyIdx < row.length ? parseInt(String(row[caseQtyIdx] || "1").replace(/[^0-9]/g, "")) || 1 : 1;
          const sectionFinal = sectionVal || "";
          const unitVal = unitIdx !== -1 && unitIdx < row.length ? String(row[unitIdx] || "PCS").trim().toUpperCase() : "PCS";

          items.push({
            id: `item_ss_${i}`,
            name: rawName,
            selling_price: mrpVal,
            purchase_price: Math.round(purchaseVal * 100) / 100,
            opening_qty: stockVal,
            case_qty: caseQtyVal,
            section: sectionFinal,
            unit: unitVal || "PCS",
          });
        }

        setParsedItems(items);
        setSelectedSection("ALL");
        setPreviewPage(1);
        setParsingEngine("Spreadsheet Importer");
        toast.success(`Extracted ${items.length} items from spreadsheet`);
      } else if (fileName.endsWith(".pdf")) {
        const token = getAccessToken();
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("filename", selectedFile.name);

        const headers: Record<string, string> = {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        };

        if (geminiApiKey.trim()) {
          headers["X-Gemini-Key"] = geminiApiKey.trim();
        }

        const res = await axios.post(
          `${API_BASE_URL}/api/v1/inventory/parse-price-list-pdf/${companyId}/`,
          formData,
          { headers }
        );

        let rawList: any[] = [];
        if (Array.isArray(res.data.items)) {
          rawList = res.data.items;
        } else if (res.data.items && Array.isArray(res.data.items.items)) {
          rawList = res.data.items.items;
        } else if (Array.isArray(res.data.data)) {
          rawList = res.data.data;
        }

        if (res.data.success && rawList.length > 0) {
          const rawItems = rawList.map((it: any, idx: number) => ({
            id: `item_pdf_${idx}`,
            name: it.name || it.item_name,
            selling_price: parseFloat(it.mrp || it.selling_price || 0),
            purchase_price: parseFloat(it.purchase_price || (it.mrp ? it.mrp * 0.70 : 0)),
            opening_qty: parseFloat(it.opening_qty || 0),
            case_qty: parseInt(it.case_qty || 1),
            section: it.section || "",
            unit: it.unit || "PCS",
          }));

          setParsedItems(rawItems);
          setSelectedSection("ALL");
          setPreviewPage(1);
          if (res.data.brand && !brand) {
            setBrand(res.data.brand);
          }
          if (res.data.effective_date) {
            setEffectiveDate(res.data.effective_date);
          }
          setParsingEngine(
            res.data.source === "AI_GEMINI_VISION"
              ? "Gemini Vision AI OCR"
              : "Multi-Column Industrial Parser"
          );
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

  const updateItemField = (id: string | undefined, index: number, field: keyof PriceListItem, val: any) => {
    setParsedItems((prev) =>
      prev.map((item, i) => {
        if (id ? item.id === id : i === index) {
          return { ...item, [field]: val };
        }
        return item;
      })
    );
  };

  const removeItem = (id: string | undefined, index: number) => {
    setParsedItems((prev) => prev.filter((item, i) => (id ? item.id !== id : i !== index)));
  };

  const availableSections = useMemo(() => {
    const counts: Record<string, number> = {};
    parsedItems.forEach((item) => {
      const s = item.section?.trim() || "Other";
      counts[s] = (counts[s] || 0) + 1;
    });
    return counts;
  }, [parsedItems]);

  const sectionList = useMemo(() => {
    return Object.keys(availableSections).sort();
  }, [availableSections]);

  const filteredItems = useMemo(() => {
    const query = filterSearch.trim().toLowerCase();
    return parsedItems.filter((i) => {
      // 1. Section Filter Tab
      if (selectedSection !== "ALL") {
        const itemSec = i.section?.trim() || "Other";
        if (itemSec !== selectedSection) return false;
      }
      // 2. Search Text
      if (!query) return true;
      if (i.name.toLowerCase().includes(query)) return true;
      // Only match section if query is > 2 characters
      if (query.length > 2 && i.section && i.section.toLowerCase().includes(query)) return true;
      return false;
    });
  }, [parsedItems, selectedSection, filterSearch]);

  const totalPages = Math.ceil(filteredItems.length / PAGE_SIZE) || 1;
  const paginatedItems = useMemo(() => {
    const start = (previewPage - 1) * PAGE_SIZE;
    return filteredItems.slice(start, start + PAGE_SIZE);
  }, [filteredItems, previewPage]);

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

          {/* Vision OCR / Gemini Key Accordion */}
          <div className="p-3 bg-purple-500/10 border border-purple-500/25 rounded-xl space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-bold text-purple-400">Gemini Vision AI OCR Available</span>
              </div>
              <button
                type="button"
                onClick={() => setShowKeyInput(!showKeyInput)}
                className="text-[11px] text-purple-400 hover:text-purple-300 underline cursor-pointer flex items-center gap-1"
              >
                <KeyRound className="w-3 h-3" />
                <span>{showKeyInput ? "Hide API Key" : "Configure Custom Key"}</span>
              </button>
            </div>
            {showKeyInput && (
              <div className="pt-1 flex items-center gap-2">
                <input
                  type="password"
                  placeholder="Paste your Gemini API Key (optional)"
                  value={geminiApiKey}
                  onChange={(e) => {
                    setGeminiApiKey(e.target.value);
                    if (typeof window !== "undefined") {
                      localStorage.setItem("vouch_gemini_key", e.target.value);
                    }
                  }}
                  className="w-full bg-zinc-950 border border-purple-500/40 text-foreground px-3 py-1.5 rounded-lg text-xs font-mono outline-none focus:ring-1 focus:ring-purple-500"
                />
                {geminiApiKey && (
                  <button
                    type="button"
                    onClick={() => {
                      setGeminiApiKey("");
                      if (typeof window !== "undefined") localStorage.removeItem("vouch_gemini_key");
                    }}
                    className="text-xs text-muted-foreground hover:text-rose-400 px-2"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
            <p className="text-[10px] text-muted-foreground">
              Automatic Vision OCR reads multi-column scanned catalogs and complex table formats. Also works offline with high-speed built-in industrial tokenizer.
            </p>
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
                  Supports multi-column catalogs (PIX V-Belts, NBC Bearings, SKF), spreadsheets & CSVs
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
                    onChange={(e) => { setFilterSearch(e.target.value); setPreviewPage(1); }}
                    className="w-full bg-muted/40 border border-border/70 rounded-lg pl-8 pr-2.5 py-1 text-xs text-foreground outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>

              {/* Section Filter Tabs */}
              {sectionList.length > 1 && (
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
                  <button
                    type="button"
                    onClick={() => { setSelectedSection("ALL"); setPreviewPage(1); }}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                      selectedSection === "ALL"
                        ? "bg-primary text-primary-foreground shadow-xs"
                        : "bg-muted/40 text-muted-foreground hover:text-foreground border border-border/50"
                    }`}
                  >
                    All Sections ({parsedItems.length})
                  </button>
                  {sectionList.map((sec: string) => {
                    const count = availableSections[sec] || 0;
                    const isSelected = selectedSection === sec;
                    const displayLabel = sec.replace(/\s*\([^)]*\)/, "").trim();
                    return (
                      <button
                        key={sec}
                        type="button"
                        onClick={() => { setSelectedSection(sec); setPreviewPage(1); }}
                        className={`px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer flex items-center gap-1.5 border ${
                          isSelected
                            ? "bg-blue-600 text-white border-blue-500 shadow-xs"
                            : "bg-muted/40 text-muted-foreground hover:text-foreground border-border/50"
                        }`}
                      >
                        <span>{displayLabel}</span>
                        <span className={`text-[10px] font-mono px-1 rounded ${isSelected ? 'bg-blue-800 text-blue-100' : 'bg-muted text-muted-foreground'}`}>
                          {count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

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
                    {paginatedItems.map((item: PriceListItem, idx: number) => (
                      <tr key={item.id || idx} className="hover:bg-muted/20">
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.name}
                            onChange={(e) => updateItemField(item.id, idx, "name", e.target.value)}
                            className="w-full bg-transparent text-foreground font-bold outline-none"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="text"
                            value={item.section || ""}
                            onChange={(e) => updateItemField(item.id, idx, "section", e.target.value)}
                            placeholder="Section / Specs"
                            className="w-full bg-transparent text-muted-foreground text-[11px] outline-none"
                          />
                        </td>
                        <td className="p-2 text-right">
                          <input
                            type="number"
                            step="0.01"
                            value={item.selling_price}
                            onChange={(e) => updateItemField(item.id, idx, "selling_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono font-bold text-foreground text-right outline-none"
                          />
                        </td>
                        <td className="p-2 text-right">
                          <input
                            type="number"
                            step="0.01"
                            value={item.purchase_price}
                            onChange={(e) => updateItemField(item.id, idx, "purchase_price", parseFloat(e.target.value) || 0)}
                            className="w-full bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono text-emerald-400 font-semibold text-right outline-none"
                          />
                        </td>
                        <td className="p-2 text-center">
                          <input
                            type="number"
                            value={item.case_qty || 1}
                            onChange={(e) => updateItemField(item.id, idx, "case_qty", parseInt(e.target.value) || 1)}
                            className="w-16 bg-muted/40 border border-border/50 rounded px-1.5 py-1 font-mono text-center text-muted-foreground outline-none"
                          />
                        </td>
                        <td className="p-2 text-center">
                          <input
                            type="text"
                            value={item.unit}
                            onChange={(e) => updateItemField(item.id, idx, "unit", e.target.value.toUpperCase())}
                            className="w-12 bg-muted/40 border border-border/50 rounded px-1 py-1 font-mono text-[11px] text-center text-muted-foreground outline-none"
                          />
                        </td>
                        <td className="p-2 text-center">
                          <button
                            type="button"
                            onClick={() => removeItem(item.id, idx)}
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

              {/* Pagination Controls */}
              <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
                <span>
                  Showing {filteredItems.length > 0 ? (previewPage - 1) * PAGE_SIZE + 1 : 0} -{" "}
                  {Math.min(previewPage * PAGE_SIZE, filteredItems.length)} of {filteredItems.length} items
                  {selectedSection !== "ALL" && ` in ${selectedSection}`}
                </span>
                {totalPages > 1 && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={previewPage <= 1}
                      onClick={() => setPreviewPage((p) => Math.max(1, p - 1))}
                      className="px-2.5 py-1 rounded bg-muted/60 hover:bg-muted disabled:opacity-40 border border-border/60 font-medium cursor-pointer"
                    >
                      Previous
                    </button>
                    <span className="font-mono text-xs">
                      Page {previewPage} of {totalPages}
                    </span>
                    <button
                      type="button"
                      disabled={previewPage >= totalPages}
                      onClick={() => setPreviewPage((p) => Math.min(totalPages, p + 1))}
                      className="px-2.5 py-1 rounded bg-muted/60 hover:bg-muted disabled:opacity-40 border border-border/60 font-medium cursor-pointer"
                    >
                      Next
                    </button>
                  </div>
                )}
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
