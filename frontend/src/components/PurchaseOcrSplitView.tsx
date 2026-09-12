"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/utils/auth";
import StateSelect from "./StateSelect";
import { useToast } from "@/context/ToastContext";
import { offlineDb } from "@/lib/db/offlineDb";

interface LineItem {
  description: string;
  brand?: string;
  hsn_code: string;
  quantity: number;
  unit: string;
  rate: number;
  discount_percent: number;
  amount: number;
  gst_rate: number;
}

interface ValidationReport {
  math_valid: boolean;
  difference: number;
  discrepancy_message?: string | null;
  calculated_subtotal: number;
  expected_total: number;
  gstin_valid: boolean;
  tax_warnings?: string[];
  risk_level: 'HIGH_CONFIDENCE' | 'NEEDS_REVIEW' | 'HIGH_RISK';
  confidence: number;
  field_confidence?: Record<string, number>;
}

interface ExtractedInvoice {
  supplier_name: string;
  supplier_gstin: string;
  invoice_number: string;
  invoice_date: string;
  state_code: string;
  subtotal: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_amount: number;
  category_detected?: string;
  requires_category_confirmation?: boolean;
  categories_found?: string[];
  line_items: LineItem[];
  is_mock?: boolean;
  mock_reason?: string;
  source?: string;
  model_used?: string;
  scan_mode?: string;
  validation?: ValidationReport;
}

interface PurchaseOcrSplitViewProps {
  companyId: string;
  onSuccess?: () => void;
}

export default function PurchaseOcrSplitView({ companyId, onSuccess }: PurchaseOcrSplitViewProps) {
  const router = useRouter();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [scanMode, setScanMode] = useState<'printed' | 'handwritten'>('printed');
  const [fileBase64, setFileBase64] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [fileMimeType, setFileMimeType] = useState<string>("application/pdf");
  const [fileName, setFileName] = useState<string>("");
  const [compressionNotice, setCompressionNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanStatusToast, setScanStatusToast] = useState<string | null>(null);

  const [invoice, setInvoice] = useState<ExtractedInvoice | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [mobileTab, setMobileTab] = useState<'DOCUMENT' | 'FORM'>('FORM');
  const [autoFilled, setAutoFilled] = useState<boolean>(false);

  // Gemini API Key State (synchronized with localStorage vouch_gemini_key)
  const [geminiApiKey, setGeminiApiKey] = useState<string>("");
  const [showApiKeyAccordion, setShowApiKeyAccordion] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedKey = localStorage.getItem("vouch_gemini_key") || "";
      if (savedKey) setGeminiApiKey(savedKey);
    }
  }, []);

  // Inventory Category Allocation State
  const [categories, setCategories] = useState<any[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const [isCreatingNewCategory, setIsCreatingNewCategory] = useState<boolean>(false);
  const [newCategoryName, setNewCategoryName] = useState<string>("");
  const [categoryDetectedMsg, setCategoryDetectedMsg] = useState<string | null>(null);

  useEffect(() => {
    if (companyId) {
      const fetchCategories = async () => {
        try {
          const token = getAccessToken();
          const res = await axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${companyId}/`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          const cats = res.data.data || [];
          setCategories(cats);
          if (cats.length > 0) {
            setSelectedCategoryId(cats[0].id);
          }
        } catch (e) {
          console.error("Failed to fetch categories", e);
        }
      };
      fetchCategories();
    }
  }, [companyId]);

  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  // Canvas-based compression utility to resize mobile camera captures (max 1600px, 0.8 JPEG quality)
  const compressImageFile = (file: File): Promise<{ base64: string; compressedSize: number }> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          let { width, height } = img;
          const maxDim = 1600; // max 1600px per specification
          if (width > maxDim || height > maxDim) {
            if (width > height) {
              height = Math.round((height * maxDim) / width);
              width = maxDim;
            } else {
              width = Math.round((width * maxDim) / height);
              height = maxDim;
            }
          }
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            resolve({ base64: e.target?.result as string, compressedSize: file.size });
            return;
          }
          ctx.drawImage(img, 0, 0, width, height);

          const quality = 0.8; // 0.8 JPEG quality per specification
          const dataUrl = canvas.toDataURL("image/jpeg", quality);
          resolve({ base64: dataUrl, compressedSize: Math.round(dataUrl.length * 0.75) });
        };
        img.onerror = () => resolve({ base64: e.target?.result as string, compressedSize: file.size });
        img.src = e.target?.result as string;
      };
      reader.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const mime = file.type || "application/pdf";
      setFileName(file.name);
      setFileMimeType(mime);
      setCompressionNotice(null);
      setError(null);
      setAutoFilled(false);

      // Create native Blob URL for reliable PDF / Image rendering
      const newBlobUrl = URL.createObjectURL(file);
      setBlobUrl(newBlobUrl);

      if (mime.startsWith("image/")) {
        try {
          const { base64, compressedSize } = await compressImageFile(file);
          const origSizeMB = (file.size / (1024 * 1024)).toFixed(2);
          const newSizeMB = (compressedSize / (1024 * 1024)).toFixed(2);
          setCompressionNotice(`⚡ PWA Camera Optimizer: Resized to max 1600px (${origSizeMB} MB → ${newSizeMB} MB).`);
          setFileBase64(base64);
          processOcr(base64, "image/jpeg");
        } catch {
          const reader = new FileReader();
          reader.onload = (evt) => {
            const b64 = evt.target?.result as string;
            setFileBase64(b64);
            processOcr(b64, mime);
          };
          reader.readAsDataURL(file);
        }
      } else {
        const MAX_BYTES = 2 * 1024 * 1024; // 2MB notice
        const origSizeMB = (file.size / (1024 * 1024)).toFixed(2);
        if (file.size > MAX_BYTES) {
          setCompressionNotice(`⚡ PDF is ${origSizeMB} MB. Stored copy will be processed in-memory without disk overhead.`);
        }
        const reader = new FileReader();
        reader.onload = (event) => {
          const base64 = event.target?.result as string;
          setFileBase64(base64);
          processOcr(base64, mime);
        };
        reader.readAsDataURL(file);
      }
    }
  };

  const processOcr = async (base64: string, mime: string, overrideMode?: 'printed' | 'handwritten') => {
    const activeMode = overrideMode || scanMode;
    setLoading(true);
    setError(null);
    setScanStatusToast(
      activeMode === 'handwritten'
        ? "Deep scan analyzing handwritten bill details..."
        : "Scanning printed invoice..."
    );

    // Compute hash for local caching
    let cacheKey = "";
    try {
      const hashBuffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(base64.slice(0, 10000) + base64.length));
      cacheKey = `ocr_${activeMode}_` + Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, "0")).join("");
      
      const cached = await offlineDb.ocrCache.get(cacheKey);
      if (cached && cached.result) {
        console.log("[PWA Cache] Loaded purchase OCR result from local IndexedDB cache!");
        const data: ExtractedInvoice = cached.result;
        setInvoice(data);
        setAutoFilled(true);
        setScanStatusToast("⚡ Loaded instantly from local cache (0ms)!");
        setTimeout(() => setScanStatusToast(null), 3000);
        setLoading(false);
        return;
      }
    } catch (cacheErr) {
      console.warn("[PWA Cache] OCR cache error:", cacheErr);
    }

    // Phase 23: Offline Guard for new OCR document processing
    if (typeof window !== "undefined" && !navigator.onLine) {
      setLoading(false);
      setScanStatusToast(null);
      setError("Internet connection required to process new AI OCR documents. Cached documents remain available offline.");
      toast.error("Offline", "Internet connection required to process new documents.");
      return;
    }

    const maxRetries = 3;
    let attempt = 0;
    let success = false;

    while (attempt < maxRetries && !success) {
      try {
        attempt++;
        if (attempt > 1) {
          setScanStatusToast(`Analyzing bill... (Attempt ${attempt}/${maxRetries})`);
          await new Promise((res) => setTimeout(res, 2000));
        }

        const token = getAccessToken();
        const effectiveKey = geminiApiKey?.trim() || (typeof window !== "undefined" ? localStorage.getItem("vouch_gemini_key") || "" : "");
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        if (effectiveKey) {
          headers["X-Gemini-Key"] = effectiveKey;
        }

        const res = await axios.post(
          `${API_BASE_URL}/api/ocr/extract/`,
          {
            file_base64: base64,
            mime_type: mime,
            gemini_api_key: effectiveKey || undefined,
            scan_mode: activeMode,
          },
          { headers, timeout: 120000 }
        );

        if (res.data.success) {
          const data: ExtractedInvoice = res.data.data;

          // Strip redundant category prefix from line item descriptions
          const catDetected = (data.category_detected || "").trim();
          const cleanPrefixRegex = /^(?:(?:v[\s\-_]*)?belts?|fan[\s\-_]*belts?|timing[\s\-_]*belts?|conveyor[\s\-_]*belts?|bearings?|pulleys?|oil[\s\-_]*seals?)\s*[:\-_]?\s*/i;
          if (data.line_items && data.line_items.length > 0) {
            data.line_items = data.line_items.map((item) => {
              let d = (item.description || "").trim();
              if (catDetected) {
                const escaped = catDetected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/[\s\-_]+/g, '[\\s\\-_]*');
                d = d.replace(new RegExp(`^${escaped}(?:s|es)?\\s*[:\\-_]?\\s*`, 'i'), '').trim();
              }
              d = d.replace(cleanPrefixRegex, '').trim();
              return { ...item, description: d || item.description };
            });
          }

          setInvoice(data);
          setAutoFilled(true);
          success = true;
          setScanStatusToast(null);

          // Save to local IndexedDB cache
          if (cacheKey) {
            offlineDb.ocrCache.put({
              fileHash: cacheKey,
              fileName: fileName || "bill",
              fileSize: base64.length,
              result: data,
              cachedAt: Date.now(),
            }).catch((e) => console.warn("[PWA Cache] Failed to persist OCR cache:", e));
          }

          // Smart Category Differentiation & Pre-Selection
          if (catDetected) {
            const detectedLower = catDetected.toLowerCase();
            const matchedCat = categories.find((c) => {
              const cName = (c.name || "").toLowerCase().trim();
              return cName === detectedLower || detectedLower.includes(cName) || cName.includes(detectedLower);
            });

            if (matchedCat) {
              setSelectedCategoryId(matchedCat.id);
              setIsCreatingNewCategory(false);
              setCategoryDetectedMsg(`Identified category "${matchedCat.name}" from bill.`);
            } else {
              setIsCreatingNewCategory(true);
              setNewCategoryName(catDetected);
              setCategoryDetectedMsg(`Detected new category "${catDetected}" from bill (will be created in database first).`);
            }
          }
        } else {
          if (attempt >= maxRetries) {
            setError(res.data.error || "Failed to extract invoice data.");
          }
        }
      } catch (err: any) {
        if (attempt >= maxRetries) {
          const errMsg = err.response?.status === 401 
            ? "Authentication session expired. Please log in again." 
            : (err.response?.data?.error || err.message || "OCR Extraction Error.");
          setError(errMsg);
        }
      }
    }

    setScanStatusToast(null);
    setLoading(false);
  };

  const updateItem = (index: number, field: keyof LineItem, value: any) => {
    if (!invoice) return;
    const updatedItems = [...invoice.line_items];
    (updatedItems[index] as any)[field] = value;

    if (field === "quantity" || field === "rate" || field === "discount_percent") {
      const q = parseFloat(String(updatedItems[index].quantity)) || 0;
      const r = parseFloat(String(updatedItems[index].rate)) || 0;
      const d = parseFloat(String(updatedItems[index].discount_percent)) || 0;
      const amountBeforeDiscount = q * r;
      const finalAmount = amountBeforeDiscount - (amountBeforeDiscount * (d / 100));
      updatedItems[index].amount = Number(finalAmount.toFixed(2));
    }

    const sub = updatedItems.reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const cgst = invoice.cgst_amount > 0 ? Number((sub * 0.09).toFixed(2)) : 0;
    const sgst = invoice.sgst_amount > 0 ? Number((sub * 0.09).toFixed(2)) : 0;
    const igst = invoice.igst_amount > 0 ? Number((sub * 0.18).toFixed(2)) : 0;
    const tot = Number((sub + cgst + sgst + igst).toFixed(2));

    setInvoice({
      ...invoice,
      line_items: updatedItems,
      subtotal: sub,
      cgst_amount: cgst,
      sgst_amount: sgst,
      igst_amount: igst,
      total_amount: tot,
    });
  };

  const addLineItem = () => {
    if (!invoice) return;
    setInvoice({
      ...invoice,
      line_items: [
        ...invoice.line_items,
        { description: "New Item", brand: "", hsn_code: "", quantity: 1, unit: "PCS", rate: 0, discount_percent: 0, amount: 0, gst_rate: 18 },
      ],
    });
  };

  const removeLineItem = (index: number) => {
    if (!invoice || invoice.line_items.length <= 1) return;
    const updated = invoice.line_items.filter((_, i) => i !== index);
    const sub = updated.reduce((s, i) => s + (Number(i.amount) || 0), 0);
    setInvoice({ ...invoice, line_items: updated, subtotal: sub });
  };

  const handleSaveToAccounting = async () => {
    if (!invoice || !companyId) return;

    // Validate category requirement (enforce category created first)
    if (isCreatingNewCategory) {
      if (!newCategoryName.trim()) {
        setError("Category name is required. Please provide a category name before saving.");
        toast.error("Category Required", "Please enter a category name (e.g. V Belts).");
        return;
      }
    } else if (!selectedCategoryId) {
      setError("Please select an inventory category for these items before saving.");
      toast.error("Category Required", "Please select an inventory category.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      let effectiveCategoryId = selectedCategoryId;

      // 1. Create Category FIRST in database before purchase voucher if user specified new category
      if (isCreatingNewCategory && newCategoryName.trim()) {
        const defaultHsn = invoice.line_items[0]?.hsn_code || "";
        const defaultGst = invoice.line_items[0]?.gst_rate || 18;
        const catRes = await axios.post(
          `${API_BASE_URL}/api/v1/inventory/categories/${companyId}/`,
          {
            name: newCategoryName.trim(),
            hsn_code: defaultHsn,
            gst_rate: defaultGst,
          },
          { headers }
        );
        if (catRes.data.success && catRes.data.data?.id) {
          effectiveCategoryId = catRes.data.data.id;
          setCategories((prev) => [...prev, catRes.data.data]);
          setSelectedCategoryId(effectiveCategoryId);
          setIsCreatingNewCategory(false);
        } else {
          throw new Error(catRes.data.error || "Failed to create category in database.");
        }
      }

      // 2. Create or get Party Ledger for the Supplier
      const partyRes = await axios.post(
        `${API_BASE_URL}/api/v1/ledgers/${companyId}/`,
        {
          name: invoice.supplier_name,
          group_name: "Creditors",
          ledger_type: "SUPPLIER",
          gstin: invoice.supplier_gstin,
          state_code: invoice.state_code,
        },
        { headers }
      );

      const partyLedgerId = partyRes.data.data?.id;

      // 3. Format Items for Voucher Creation with Category Allocation
      const formattedItems = invoice.line_items.map((item) => ({
        product_name: item.description,
        brand: item.brand && item.brand.trim() ? item.brand.trim() : undefined,
        hsn_code: item.hsn_code,
        quantity: item.quantity,
        rate: item.rate,
        unit: item.unit || "PCS",
        discount_percent: item.discount_percent || 0,
        gst_rate: item.gst_rate || 18,
        category_id: effectiveCategoryId || undefined,
      }));

      // 3. Post to Universal Voucher Engine with attached document
      const payload = {
        company_id: companyId,
        voucher_type: "PURCHASE",
        voucher_date: invoice.invoice_date || new Date().toISOString().split("T")[0],
        voucher_number: invoice.invoice_number || undefined,
        party_ledger_id: partyLedgerId,
        items: formattedItems,
        narration: `AI-Extracted Purchase Invoice from ${invoice.supplier_name} (#${invoice.invoice_number})`,
        attachment_data: fileBase64,
        attachment_mime: fileMimeType,
      };

      const res = await axios.post(`${API_BASE_URL}/api/vouchers/`, payload, { headers });

      toast.success(
        `Purchase Invoice #${res.data.voucher_number || res.data.data?.voucher_number} posted!`,
        `Scanned items automatically linked to inventory with stock updated.`
      );

      if (onSuccess) {
        onSuccess();
      } else {
        router.push("/purchases");
      }
    } catch (err: any) {
      setError(err.response?.data?.error || err.message || "Failed to post purchase invoice.");
      toast.error("Failed to post invoice", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Dual-Engine Hybrid Mode Bar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-900/90 border border-border p-3.5 rounded-2xl shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2.5">
          <span className="text-xs font-bold text-foreground/80 uppercase tracking-wider flex items-center gap-1.5">
            <span>⚡</span> OCR Engine:
          </span>
          <div className="inline-flex rounded-xl bg-zinc-950 p-1 border border-border">
            <button
              type="button"
              onClick={() => setScanMode("printed")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                scanMode === "printed"
                  ? "bg-blue-600 text-foreground shadow-md"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span>⚡ Printed Bill</span>
              <span className="text-[10px] opacity-80 hidden sm:inline font-normal">(Flash-Lite: 2x Faster, High Quota)</span>
            </button>
            <button
              type="button"
              onClick={() => setScanMode("handwritten")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                scanMode === "handwritten"
                  ? "bg-purple-600 text-foreground shadow-md"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span>🧠 Handwritten / Kaccha</span>
              <span className="text-[10px] opacity-80 hidden sm:inline font-normal">(3.6 Flash: Deep Vision)</span>
            </button>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowApiKeyAccordion(!showApiKeyAccordion)}
          className="text-xs text-purple-400 hover:text-purple-300 flex items-center gap-1.5 underline cursor-pointer self-end md:self-auto"
        >
          <span>🔑</span>
          <span>{showApiKeyAccordion ? "Hide Key Settings" : geminiApiKey ? "Custom Key Configured ✓" : "Configure Custom Key"}</span>
        </button>
      </div>

      {/* Collapsible API Key Configuration */}
      {showApiKeyAccordion && (
        <div className="p-3.5 bg-purple-500/10 border border-purple-500/25 rounded-2xl space-y-2">
          <div className="flex items-center justify-between text-xs text-purple-300 font-semibold">
            <span>Custom Scanner API Key (saved in browser):</span>
            {geminiApiKey && (
              <button
                type="button"
                onClick={() => {
                  setGeminiApiKey("");
                  if (typeof window !== "undefined") localStorage.removeItem("vouch_gemini_key");
                }}
                className="text-[11px] text-red-400 hover:text-red-300 cursor-pointer font-bold"
              >
                Clear Key
              </button>
            )}
          </div>
          <input
            type="password"
            placeholder="Paste your custom API Key here..."
            value={geminiApiKey}
            onChange={(e) => {
              const val = e.target.value.trim();
              setGeminiApiKey(val);
              if (typeof window !== "undefined") {
                if (val) localStorage.setItem("vouch_gemini_key", val);
                else localStorage.removeItem("vouch_gemini_key");
              }
            }}
            className="w-full bg-zinc-950 border border-purple-500/35 text-foreground px-3 py-2 rounded-xl text-xs font-mono outline-none focus:ring-1 focus:ring-purple-500"
          />
          <p className="text-[10px] text-muted-foreground">
            Optional custom key for high-volume bill scanning and price list imports.
          </p>
        </div>
      )}

      {/* Upload Banner */}
      {!fileBase64 && (
        <div className="border-2 border-dashed border-input bg-zinc-900/40 rounded-2xl p-10 text-center hover:border-blue-500 transition-colors">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept="application/pdf,image/png,image/jpeg,image/webp"
            className="hidden"
          />
          <div className="flex flex-col items-center space-y-4">
            <div className="w-16 h-16 bg-blue-600/10 text-blue-500 rounded-full flex items-center justify-center text-2xl font-bold">
              📄
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-foreground">Upload Supplier Invoice (Photo or PDF)</h3>
              <p className="text-xs text-muted-foreground">
                Active scanner: <strong className="text-foreground">{scanMode === 'printed' ? 'Standard (Printed Bills)' : 'Deep Scan (Handwritten / Complex)'}</strong>
              </p>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-foreground font-bold rounded-lg text-xs shadow-lg transition-colors cursor-pointer"
            >
              Browse Document / Photo
            </button>
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {loading && (
        <div className="p-8 bg-muted/50 border border-blue-500/30 rounded-2xl flex flex-col items-center justify-center space-y-3 shadow-xl animate-in fade-in">
          <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <div className="text-sm font-bold text-foreground flex items-center gap-2 text-center px-4">
            <span>{scanStatusToast || "Scanning your bill, please wait a few seconds..."}</span>
          </div>
          <div className="text-xs font-mono px-3 py-1 rounded-full border animate-pulse flex items-center gap-1.5 bg-blue-500/10 text-blue-400 border-blue-500/20">
            {scanMode === 'handwritten' ? (
              <><span>🧠</span><span>Deep Scan Mode</span></>
            ) : (
              <><span>⚡</span><span>Standard Scan Mode</span></>
            )}
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="font-bold ml-4">✕</button>
        </div>
      )}

      {/* Unreadable / Mock Banner */}
      {invoice?.is_mock && !loading && (
        <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-start gap-3">
          <span className="text-lg">⚠️</span>
          <div className="space-y-1">
            <div className="font-bold">Text extraction was partial or unclear from this photo</div>
            <p className="text-amber-400/90 text-[11px]">
              {invoice.mock_reason || "Could not recognize all invoice details automatically. Please verify or fill in the supplier and item details on the right."}
            </p>
          </div>
        </div>
      )}

      {/* Compression Banner */}
      {compressionNotice && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-xs text-blue-300">
          {compressionNotice}
        </div>
      )}

      {/* Split-Screen Review Workspace */}
      {fileBase64 && invoice && !loading && (
        <div className="space-y-4">
          {/* Phase 10 & 11 Mathematical Discrepancy Warning */}
          {invoice.validation && !invoice.validation.math_valid && (
            <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-start justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <span className="text-base">⚠️</span>
                <div>
                  <div className="font-bold">
                    {invoice.validation.discrepancy_message || `Vouch found a ₹${invoice.validation.difference.toFixed(2)} difference in extracted totals.`}
                  </div>
                  <div className="text-[11px] text-amber-400/90 mt-0.5">
                    Calculated line items total ₹{invoice.validation.expected_total.toFixed(2)}, but document states ₹{invoice.total_amount.toFixed(2)}. Please verify rates and quantities in the form before posting.
                  </div>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 whitespace-nowrap">
                Review Required
              </span>
            </div>
          )}

          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-muted/50 p-4 rounded-xl border border-border">
            <div className="flex items-center gap-3">
              <span className="text-xl">📑</span>
              <div>
                <div className="text-sm font-bold text-foreground flex items-center gap-2 flex-wrap">
                  <span>{fileName}</span>
                  {invoice.source?.startsWith("AI_GEMINI_VISION") && (
                    <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 bg-purple-500/10 text-purple-400 border-purple-500/20">
                      <span>✨</span><span>Smart Scan</span>
                    </span>
                  )}
                  {invoice.source === "RAPID_OCR_VISION" && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      ⚡ Smart Scan
                    </span>
                  )}
                  {invoice.source === "PDF_TEXT_STREAM" && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      📄 Digital Document
                    </span>
                  )}
                  {invoice.validation && (
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${
                      invoice.validation.risk_level === 'HIGH_CONFIDENCE'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : invoice.validation.risk_level === 'NEEDS_REVIEW'
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    }`}>
                      {invoice.validation.risk_level === 'HIGH_CONFIDENCE' ? '✓ Verified' : invoice.validation.risk_level === 'NEEDS_REVIEW' ? '⚠️ Needs Review' : '⛔ High Risk'}
                    </span>
                  )}

                  {/* Quick Engine Re-scan Button */}
                  <button
                    type="button"
                    onClick={() => {
                      const nextMode = (invoice.model_used?.includes("flash-lite") || invoice.source?.includes("flash-lite")) ? "handwritten" : "printed";
                      setScanMode(nextMode);
                      processOcr(fileBase64, fileMimeType, nextMode);
                    }}
                    disabled={loading}
                    className="px-2 py-0.5 bg-muted hover:bg-zinc-700 text-foreground/80 rounded text-[10px] font-medium border border-input transition-colors flex items-center gap-1 cursor-pointer ml-1"
                    title="Re-run OCR using the complementary engine"
                  >
                    <span>🔄 Re-scan with {(invoice.model_used?.includes("flash-lite") || invoice.source?.includes("flash-lite")) ? "🧠 3.6 Flash" : "⚡ Flash-Lite"}</span>
                  </button>
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-0.5">
                  {fileMimeType} • Extracted in-memory
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <button
                onClick={() => {
                  setFileBase64(null);
                  setBlobUrl(null);
                  setInvoice(null);
                  setCompressionNotice(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
                className="px-4 py-2 bg-muted hover:bg-zinc-700 text-foreground/80 rounded-lg text-xs font-semibold border border-input transition-colors cursor-pointer"
              >
                Upload Different Bill
              </button>
              <button
                onClick={handleSaveToAccounting}
                disabled={saving}
                className="px-6 py-2 bg-green-600 hover:bg-green-700 text-foreground rounded-lg text-sm font-bold shadow-lg transition-colors flex-1 sm:flex-none cursor-pointer"
              >
                {saving ? "Saving..." : "✓ Approve & Save to ERP"}
              </button>
            </div>
          </div>

          {/* Mobile Screen Segmented Switcher (< lg) */}
          <div className="flex lg:hidden items-center bg-muted/50 border border-border p-1 rounded-xl shadow-inner mb-2">
            <button
              type="button"
              onClick={() => setMobileTab('DOCUMENT')}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                mobileTab === 'DOCUMENT'
                  ? 'bg-blue-600 text-foreground shadow-md'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <span>📄 Bill Preview</span>
            </button>
            <button
              type="button"
              onClick={() => setMobileTab('FORM')}
              className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
                mobileTab === 'FORM'
                  ? 'bg-blue-600 text-foreground shadow-md'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <span>✍️ Form ({invoice.line_items.length} items)</span>
              {autoFilled && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
            </button>
          </div>

          {/* Responsive Split Grid: Desktop Side-by-Side with Sticky Preview; Mobile Tabbed */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* Left Pane: Document Viewer (Sticky on Desktop) */}
            <div className={`bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col h-[650px] lg:h-[780px] lg:sticky lg:top-4 overflow-hidden ${
              mobileTab === 'DOCUMENT' ? 'block' : 'hidden lg:flex'
            }`}>
              <div className="flex items-center justify-between border-b border-border pb-3 mb-3 text-xs text-muted-foreground">
                <span className="font-semibold text-foreground">Original Document Preview</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setZoomLevel((z) => Math.max(50, z - 25))} className="px-2 py-1 bg-muted hover:bg-zinc-700 text-foreground rounded text-xs cursor-pointer">-</button>
                  <span className="font-mono">{zoomLevel}%</span>
                  <button onClick={() => setZoomLevel((z) => Math.min(200, z + 25))} className="px-2 py-1 bg-muted hover:bg-zinc-700 text-foreground rounded text-xs cursor-pointer">+</button>
                  {blobUrl && (
                    <a
                      href={blobUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2 py-1 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 rounded text-xs font-bold"
                    >
                      ↗ Pop Out
                    </a>
                  )}
                </div>
              </div>

              <div className="flex-1 bg-zinc-950 rounded-lg overflow-auto flex items-center justify-center p-2">
                {fileMimeType.includes("pdf") ? (
                  <object
                    data={blobUrl || fileBase64}
                    type="application/pdf"
                    className="w-full h-full rounded border-0"
                  >
                    <embed src={blobUrl || fileBase64} type="application/pdf" className="w-full h-full" />
                    <div className="text-center p-4 text-xs text-muted-foreground">
                      PDF preview not supported directly in this view.
                      <a href={blobUrl || fileBase64} target="_blank" rel="noreferrer" className="text-blue-400 underline ml-2">Click to open PDF</a>
                    </div>
                  </object>
                ) : (
                  <div className="w-full h-full overflow-auto flex items-center justify-center">
                    <img
                      src={blobUrl || fileBase64}
                      alt="Invoice"
                      style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: "center center" }}
                      className="max-w-full max-h-full object-contain rounded transition-transform"
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Right Pane: Pre-filled Human-in-the-Loop Form */}
            <div className={`bg-card border border-border rounded-xl p-5 shadow-sm space-y-6 h-[650px] lg:h-[780px] overflow-y-auto ${
              mobileTab === 'FORM' ? 'block' : 'hidden lg:block'
            }`}>
              <div>
                <div className="flex items-center justify-between border-b border-border pb-2 mb-4">
                  <h3 className="text-base font-bold text-foreground">
                    Extracted Bill Details (Review & Edit)
                  </h3>
                  {autoFilled && (
                    <span className="px-2.5 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-full text-[11px] font-semibold flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Auto-filled by AI
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                  <div className="sm:col-span-2">
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase">Supplier Name</label>
                      {autoFilled && invoice.supplier_name && (
                        <span className="text-[10px] text-emerald-400 font-medium">✨ AI Auto-Filled</span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={invoice.supplier_name}
                      onChange={(e) => setInvoice({ ...invoice, supplier_name: e.target.value })}
                      className={`w-full bg-muted/50 border ${
                        autoFilled && invoice.supplier_name ? 'border-emerald-500/40 focus:ring-emerald-500' : 'border-input focus:ring-blue-500'
                      } text-foreground p-2.5 rounded-lg text-sm font-semibold outline-none focus:ring-2`}
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase">Supplier GSTIN</label>
                      {autoFilled && invoice.supplier_gstin && (
                        <span className="text-[10px] text-emerald-400 font-medium">✨ AI Auto-Filled</span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={invoice.supplier_gstin}
                      onChange={(e) => setInvoice({ ...invoice, supplier_gstin: e.target.value.toUpperCase() })}
                      className={`w-full bg-muted/50 border ${
                        autoFilled && invoice.supplier_gstin ? 'border-emerald-500/40 focus:ring-emerald-500' : 'border-input focus:ring-blue-500'
                      } text-foreground p-2.5 rounded-lg text-sm font-mono uppercase outline-none focus:ring-2`}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">State Code / Place of Supply</label>
                    <StateSelect
                      value={invoice.state_code}
                      onChange={(val) => setInvoice({ ...invoice, state_code: val })}
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase">Invoice Number</label>
                      {autoFilled && invoice.invoice_number && (
                        <span className="text-[10px] text-emerald-400 font-medium">✨ AI Auto-Filled</span>
                      )}
                    </div>
                    <input
                      type="text"
                      value={invoice.invoice_number}
                      onChange={(e) => setInvoice({ ...invoice, invoice_number: e.target.value })}
                      className={`w-full bg-muted/50 border ${
                        autoFilled && invoice.invoice_number ? 'border-emerald-500/40 focus:ring-emerald-500' : 'border-input focus:ring-blue-500'
                      } text-foreground p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2`}
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-muted-foreground uppercase">Invoice Date</label>
                      {autoFilled && invoice.invoice_date && (
                        <span className="text-[10px] text-emerald-400 font-medium">✨ AI Auto-Filled</span>
                      )}
                    </div>
                    <input
                      type="date"
                      value={invoice.invoice_date}
                      onChange={(e) => setInvoice({ ...invoice, invoice_date: e.target.value })}
                      className={`w-full bg-muted/50 border ${
                        autoFilled && invoice.invoice_date ? 'border-emerald-500/40 focus:ring-emerald-500' : 'border-input focus:ring-blue-500'
                      } text-foreground p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2`}
                    />
                  </div>
                </div>
              </div>

              {/* Inventory Category Allocation Card */}
              <div className={`p-3.5 rounded-xl space-y-2 border transition-colors ${
                invoice.requires_category_confirmation
                  ? 'bg-amber-500/10 border-amber-500/40'
                  : 'bg-blue-500/10 border-blue-500/30'
              }`}>
                {/* AI Category Confirmation Warning Banner */}
                {invoice.requires_category_confirmation && (
                  <div className="p-2.5 bg-amber-500/15 border border-amber-500/30 rounded-lg text-xs text-amber-200 flex items-start gap-2">
                    <span className="text-sm">⚠️</span>
                    <div className="space-y-0.5">
                      <div className="font-bold">Category Confirmation Required</div>
                      <p className="text-[11px] text-amber-300/90 leading-relaxed">
                        The bill did not clearly specify an inventory category or contains multiple categories. Please confirm or select the correct category below before saving.
                      </p>
                    </div>
                  </div>
                )}

                {/* AI Detected Category Notification */}
                {categoryDetectedMsg && (
                  <div className="p-2 bg-blue-500/15 border border-blue-500/30 rounded-lg text-xs text-blue-200 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-medium">
                      <span>✨</span>
                      <span>{categoryDetectedMsg}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setCategoryDetectedMsg(null)}
                      className="text-blue-400 hover:text-blue-200 font-bold ml-2 cursor-pointer text-xs"
                    >
                      ✕
                    </button>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>📦</span>
                    <span>Add Scanned Items to Inventory Category (Required):</span>
                    <span className="text-red-400">*</span>
                  </label>
                  {isCreatingNewCategory ? (
                    <button 
                      type="button" 
                      onClick={() => setIsCreatingNewCategory(false)}
                      className="text-[11px] text-muted-foreground hover:text-foreground underline cursor-pointer"
                    >
                      Choose Existing
                    </button>
                  ) : (
                    <button 
                      type="button" 
                      onClick={() => setIsCreatingNewCategory(true)}
                      className="text-[11px] text-blue-400 hover:text-blue-300 underline cursor-pointer"
                    >
                      + New Category
                    </button>
                  )}
                </div>

                {isCreatingNewCategory ? (
                  <div className="space-y-1">
                    <input
                      type="text"
                      placeholder="e.g. V Belts, Bearings, Lubricants"
                      value={newCategoryName}
                      onChange={(e) => setNewCategoryName(e.target.value)}
                      className="w-full bg-zinc-950 border border-blue-500/60 text-foreground p-2.5 rounded-lg text-xs font-semibold outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <p className="text-[10px] text-emerald-400">
                      ⚡ This category will be created in the database first before saving voucher items.
                    </p>
                  </div>
                ) : (
                  <select
                    value={selectedCategoryId}
                    onChange={(e) => {
                      if (e.target.value === '__NEW__') {
                        setIsCreatingNewCategory(true);
                      } else {
                        setSelectedCategoryId(e.target.value);
                      }
                    }}
                    className={`w-full bg-zinc-950 border ${
                      !selectedCategoryId ? 'border-amber-500/60 focus:ring-amber-500' : 'border-input focus:ring-blue-500'
                    } text-foreground p-2.5 rounded-lg text-xs font-medium outline-none focus:ring-2 cursor-pointer`}
                  >
                    <option value="">-- Select Category (e.g. V Belts) --</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} {c.hsn_code ? `(HSN: ${c.hsn_code})` : ''}
                      </option>
                    ))}
                    <option value="__NEW__">+ Create New Category</option>
                  </select>
                )}
                <p className="text-[10px] text-muted-foreground">
                  Scanned items will be automatically created in this category with real-time stock and purchase price updated.
                </p>
              </div>

              {/* Line Items Table */}
              <div>
                <div className="flex items-center justify-between border-b border-border pb-2 mb-3">
                  <div className="flex items-center gap-2">
                    <h4 className="text-xs font-bold text-foreground/80 uppercase tracking-wider">Line Items</h4>
                    {autoFilled && invoice.line_items.length > 0 && (
                      <span className="text-[10px] text-emerald-400 font-medium bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                        ✨ {invoice.line_items.length} items parsed
                      </span>
                    )}
                  </div>
                  <button onClick={addLineItem} type="button" className="text-xs text-blue-400 hover:text-blue-300 font-bold cursor-pointer">
                    + Add Item
                  </button>
                </div>

                <div className="space-y-3">
                  {invoice.line_items.map((item, idx) => (
                    <div key={idx} className={`p-3 bg-zinc-900/80 border ${autoFilled ? 'border-emerald-500/25 hover:border-emerald-500/50' : 'border-border'} rounded-lg space-y-2 text-xs transition-colors`}>
                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2">
                        <div className="flex-1 flex items-center gap-2">
                          <input
                            type="text"
                            value={item.description}
                            onChange={(e) => updateItem(idx, "description", e.target.value)}
                            placeholder="Item Description / Product Name"
                            className="flex-1 bg-zinc-950 border border-input text-foreground p-2 sm:p-1.5 rounded outline-none font-medium"
                          />
                          <button onClick={() => removeLineItem(idx)} className="sm:hidden text-red-400 hover:text-red-300 p-1 font-bold cursor-pointer" title="Delete item">✕</button>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={item.brand || ""}
                            onChange={(e) => updateItem(idx, "brand", e.target.value)}
                            placeholder="Brand (e.g. Fenner, SKF)"
                            className="flex-1 sm:w-44 bg-zinc-950 border border-input text-foreground p-2 sm:p-1.5 rounded outline-none text-xs"
                          />
                          <button onClick={() => removeLineItem(idx)} className="hidden sm:inline-block text-red-400 hover:text-red-300 px-1 font-bold cursor-pointer" title="Delete item">✕</button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                        <div>
                          <label className="block text-[10px] text-muted-foreground">HSN</label>
                          <input
                            type="text"
                            value={item.hsn_code}
                            onChange={(e) => updateItem(idx, "hsn_code", e.target.value)}
                            className="w-full bg-zinc-950 border border-input text-foreground p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-muted-foreground">Qty</label>
                          <input
                            type="number"
                            value={item.quantity}
                            onChange={(e) => updateItem(idx, "quantity", e.target.value)}
                            className="w-full bg-zinc-950 border border-input text-foreground p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-muted-foreground">Rate (₹)</label>
                          <input
                            type="number"
                            value={item.rate}
                            onChange={(e) => updateItem(idx, "rate", e.target.value)}
                            className="w-full bg-zinc-950 border border-input text-foreground p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-muted-foreground">Disc %</label>
                          <input
                            type="number"
                            value={item.discount_percent || ""}
                            onChange={(e) => updateItem(idx, "discount_percent", e.target.value)}
                            className="w-full bg-zinc-950 border border-input text-foreground p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div className="col-span-2 sm:col-span-1">
                          <label className="block text-[10px] text-muted-foreground">Taxable (₹)</label>
                          <input
                            type="number"
                            value={item.amount}
                            readOnly
                            className="w-full bg-zinc-950/50 border border-border text-blue-400 p-1.5 rounded outline-none font-mono font-bold"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Totals Summary */}
              <div className="p-4 bg-zinc-950 border border-border rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <span>Subtotal:</span>
                  <span>₹{invoice.subtotal.toFixed(2)}</span>
                </div>
                {invoice.cgst_amount > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>CGST (9%):</span>
                    <span>₹{invoice.cgst_amount.toFixed(2)}</span>
                  </div>
                )}
                {invoice.sgst_amount > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>SGST (9%):</span>
                    <span>₹{invoice.sgst_amount.toFixed(2)}</span>
                  </div>
                )}
                {invoice.igst_amount > 0 && (
                  <div className="flex justify-between text-muted-foreground">
                    <span>IGST (18%):</span>
                    <span>₹{invoice.igst_amount.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-foreground border-t border-border pt-2">
                  <span>Grand Total:</span>
                  <span className="text-green-400">₹{invoice.total_amount.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
