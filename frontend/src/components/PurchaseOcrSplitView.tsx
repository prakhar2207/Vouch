"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/utils/auth";
import StateSelect from "./StateSelect";
import { useToast } from "@/context/ToastContext";

interface LineItem {
  description: string;
  hsn_code: string;
  quantity: number;
  unit: string;
  rate: number;
  amount: number;
  gst_rate: number;
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
  line_items: LineItem[];
  is_mock?: boolean;
  mock_reason?: string;
}

interface PurchaseOcrSplitViewProps {
  companyId: string;
  onSuccess?: () => void;
}

export default function PurchaseOcrSplitView({ companyId, onSuccess }: PurchaseOcrSplitViewProps) {
  const router = useRouter();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  // Inventory Category Allocation State
  const [categories, setCategories] = useState<any[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string>("");
  const [isCreatingNewCategory, setIsCreatingNewCategory] = useState<boolean>(false);
  const [newCategoryName, setNewCategoryName] = useState<string>("");

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

  // Client-side image compressor if > 2MB
  const compressImageFile = (file: File): Promise<{ base64: string; compressedSize: number }> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          let { width, height } = img;
          const maxDim = 1800;
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

          let quality = 0.85;
          let dataUrl = canvas.toDataURL("image/jpeg", quality);
          // If still > 2MB, reduce quality
          while (dataUrl.length * 0.75 > 1.9 * 1024 * 1024 && quality > 0.4) {
            quality -= 0.15;
            dataUrl = canvas.toDataURL("image/jpeg", quality);
          }
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

      // Create native Blob URL for 100% reliable PDF / Image rendering
      const newBlobUrl = URL.createObjectURL(file);
      setBlobUrl(newBlobUrl);

      const MAX_BYTES = 2 * 1024 * 1024; // 2MB
      const origSizeMB = (file.size / (1024 * 1024)).toFixed(2);

      if (mime.startsWith("image/") && file.size > MAX_BYTES) {
        try {
          const { base64, compressedSize } = await compressImageFile(file);
          const newSizeMB = (compressedSize / (1024 * 1024)).toFixed(2);
          setCompressionNotice(`⚡ Auto-compressed image from ${origSizeMB} MB to ${newSizeMB} MB for storage.`);
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
        if (file.size > MAX_BYTES) {
          setCompressionNotice(`⚡ PDF is ${origSizeMB} MB. Stored copy will be auto-compressed under 2MB.`);
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

  const processOcr = async (base64: string, mime: string) => {
    setLoading(true);
    setError(null);
    setScanStatusToast("AI is scanning your bill, please wait a few seconds...");

    const maxRetries = 3;
    let attempt = 0;
    let success = false;

    while (attempt < maxRetries && !success) {
      try {
        attempt++;
        if (attempt > 1) {
          setScanStatusToast(`AI is scanning your bill, please wait a few seconds... (Attempt ${attempt}/${maxRetries})`);
          await new Promise((res) => setTimeout(res, 2500));
        }

        const token = getAccessToken();
        const headers = { Authorization: `Bearer ${token}` };

        const res = await axios.post(
          `${API_BASE_URL}/api/ocr/extract/`,
          { file_base64: base64, mime_type: mime },
          { headers }
        );

        if (res.data.success) {
          setInvoice(res.data.data);
          success = true;
          setScanStatusToast(null);
        } else {
          if (attempt >= maxRetries) {
            setError(res.data.error || "Failed to extract invoice data.");
          }
        }
      } catch (err: any) {
        if (attempt >= maxRetries) {
          setError(err.response?.data?.error || err.message || "OCR Extraction Error.");
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

    if (field === "quantity" || field === "rate") {
      const q = parseFloat(String(updatedItems[index].quantity)) || 0;
      const r = parseFloat(String(updatedItems[index].rate)) || 0;
      updatedItems[index].amount = Number((q * r).toFixed(2));
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
        { description: "New Item", hsn_code: "", quantity: 1, unit: "PCS", rate: 0, amount: 0, gst_rate: 18 },
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
    setSaving(true);
    setError(null);

    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Create or get Party Ledger for the Supplier
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

      // 2. Format Items for Voucher Creation with Category Allocation
      const formattedItems = invoice.line_items.map((item) => ({
        product_name: item.description,
        hsn_code: item.hsn_code,
        quantity: item.quantity,
        rate: item.rate,
        unit: item.unit || "PCS",
        discount_percent: 0,
        gst_rate: item.gst_rate || 18,
        category_id: !isCreatingNewCategory && selectedCategoryId ? selectedCategoryId : undefined,
        category_name: isCreatingNewCategory && newCategoryName.trim() ? newCategoryName.trim() : undefined,
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
      {/* Upload Banner */}
      {!fileBase64 && (
        <div className="border-2 border-dashed border-zinc-700 bg-zinc-900/40 rounded-2xl p-10 text-center hover:border-blue-500 transition-colors">
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
              <h3 className="text-lg font-bold text-white">Upload Supplier Invoice (PDF or Image)</h3>
              <p className="text-xs text-gray-400">
                Supports PDF, PNG, JPEG, WebP. Files over 2MB are automatically compressed.
              </p>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg text-xs shadow-lg transition-colors cursor-pointer"
            >
              Browse Document
            </button>
          </div>
        </div>
      )}

      {/* Loading Overlay */}
      {loading && (
        <div className="p-8 bg-zinc-900 border border-blue-500/30 rounded-2xl flex flex-col items-center justify-center space-y-3 shadow-xl animate-in fade-in">
          <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <div className="text-sm font-bold text-white flex items-center gap-2">
            <span>{scanStatusToast || "AI is scanning your bill, please wait a few seconds..."}</span>
          </div>
          <div className="text-xs text-blue-400 font-mono bg-blue-500/10 px-3 py-1 rounded-full border border-blue-500/20 animate-pulse">
            Gemini AI Invoice Extraction in Progress
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

      {/* Compression Banner */}
      {compressionNotice && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-xs text-blue-300">
          {compressionNotice}
        </div>
      )}

      {/* Split-Screen Review Workspace */}
      {fileBase64 && invoice && !loading && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-zinc-900 p-4 rounded-xl border border-zinc-800">
            <div className="flex items-center gap-3">
              <span className="text-xl">📑</span>
              <div>
                <div className="text-sm font-bold text-white">{fileName}</div>
                <div className="text-xs text-gray-400 font-mono">
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
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg text-xs font-semibold border border-zinc-700 transition-colors cursor-pointer"
              >
                Upload Different Bill
              </button>
              <button
                onClick={handleSaveToAccounting}
                disabled={saving}
                className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-bold shadow-lg transition-colors flex-1 sm:flex-none cursor-pointer"
              >
                {saving ? "Saving..." : "✓ Approve & Save to ERP"}
              </button>
            </div>
          </div>

          {/* 50 / 50 Split Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* Left Pane: Document Viewer */}
            <div className="bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col h-[750px] overflow-hidden">
              <div className="flex items-center justify-between border-b border-border pb-3 mb-3 text-xs text-gray-400">
                <span className="font-semibold text-gray-200">Original Document Preview</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setZoomLevel((z) => Math.max(50, z - 25))} className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded text-xs cursor-pointer">-</button>
                  <span className="font-mono">{zoomLevel}%</span>
                  <button onClick={() => setZoomLevel((z) => Math.min(200, z + 25))} className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-white rounded text-xs cursor-pointer">+</button>
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
                    <div className="text-center p-4 text-xs text-gray-400">
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
            <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-6 h-[750px] overflow-y-auto">
              <div>
                <h3 className="text-base font-bold text-white border-b border-border pb-2 mb-4">
                  Extracted Bill Details (Review & Edit)
                </h3>

                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Supplier Name</label>
                    <input
                      type="text"
                      value={invoice.supplier_name}
                      onChange={(e) => setInvoice({ ...invoice, supplier_name: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-semibold outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Supplier GSTIN</label>
                    <input
                      type="text"
                      value={invoice.supplier_gstin}
                      onChange={(e) => setInvoice({ ...invoice, supplier_gstin: e.target.value.toUpperCase() })}
                      className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono uppercase outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">State Code / Place of Supply</label>
                    <StateSelect
                      value={invoice.state_code}
                      onChange={(val) => setInvoice({ ...invoice, state_code: val })}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Invoice Number</label>
                    <input
                      type="text"
                      value={invoice.invoice_number}
                      onChange={(e) => setInvoice({ ...invoice, invoice_number: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Invoice Date</label>
                    <input
                      type="date"
                      value={invoice.invoice_date}
                      onChange={(e) => setInvoice({ ...invoice, invoice_date: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 text-white p-2.5 rounded-lg text-sm font-mono outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Inventory Category Allocation Card */}
              <div className="p-3.5 bg-blue-500/10 border border-blue-500/30 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>📦</span>
                    <span>Add Scanned Items to Inventory Category:</span>
                  </label>
                  {isCreatingNewCategory ? (
                    <button 
                      type="button" 
                      onClick={() => setIsCreatingNewCategory(false)}
                      className="text-[11px] text-gray-400 hover:text-white underline cursor-pointer"
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
                  <input
                    type="text"
                    placeholder="e.g. V Belts, Bearings, Lubricants"
                    value={newCategoryName}
                    onChange={(e) => setNewCategoryName(e.target.value)}
                    className="w-full bg-zinc-950 border border-blue-500/50 text-white p-2 rounded-lg text-xs font-medium outline-none focus:ring-1 focus:ring-blue-500"
                  />
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
                    className="w-full bg-zinc-950 border border-zinc-700 text-white p-2 rounded-lg text-xs font-medium outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer"
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
                <p className="text-[10px] text-gray-400">
                  Scanned items will be automatically created in this category with real-time stock and purchase price updated.
                </p>
              </div>

              {/* Line Items Table */}
              <div>
                <div className="flex items-center justify-between border-b border-border pb-2 mb-3">
                  <h4 className="text-xs font-bold text-gray-300 uppercase tracking-wider">Line Items</h4>
                  <button onClick={addLineItem} type="button" className="text-xs text-blue-400 hover:text-blue-300 font-bold cursor-pointer">
                    + Add Item
                  </button>
                </div>

                <div className="space-y-3">
                  {invoice.line_items.map((item, idx) => (
                    <div key={idx} className="p-3 bg-zinc-900/80 border border-zinc-800 rounded-lg space-y-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <input
                          type="text"
                          value={item.description}
                          onChange={(e) => updateItem(idx, "description", e.target.value)}
                          placeholder="Item Description"
                          className="flex-1 bg-zinc-950 border border-zinc-700 text-white p-1.5 rounded outline-none font-medium"
                        />
                        <button onClick={() => removeLineItem(idx)} className="text-red-400 hover:text-red-300 px-1 font-bold cursor-pointer">✕</button>
                      </div>

                      <div className="grid grid-cols-4 gap-2">
                        <div>
                          <label className="block text-[10px] text-gray-400">HSN</label>
                          <input
                            type="text"
                            value={item.hsn_code}
                            onChange={(e) => updateItem(idx, "hsn_code", e.target.value)}
                            className="w-full bg-zinc-950 border border-zinc-700 text-white p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-gray-400">Qty</label>
                          <input
                            type="number"
                            value={item.quantity}
                            onChange={(e) => updateItem(idx, "quantity", e.target.value)}
                            className="w-full bg-zinc-950 border border-zinc-700 text-white p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-gray-400">Rate (₹)</label>
                          <input
                            type="number"
                            value={item.rate}
                            onChange={(e) => updateItem(idx, "rate", e.target.value)}
                            className="w-full bg-zinc-950 border border-zinc-700 text-white p-1.5 rounded outline-none font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-gray-400">Taxable (₹)</label>
                          <input
                            type="number"
                            value={item.amount}
                            readOnly
                            className="w-full bg-zinc-950/50 border border-zinc-800 text-blue-400 p-1.5 rounded outline-none font-mono font-bold"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Totals Summary */}
              <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-2 font-mono text-xs">
                <div className="flex justify-between text-gray-400">
                  <span>Subtotal:</span>
                  <span>₹{invoice.subtotal.toFixed(2)}</span>
                </div>
                {invoice.cgst_amount > 0 && (
                  <div className="flex justify-between text-gray-400">
                    <span>CGST (9%):</span>
                    <span>₹{invoice.cgst_amount.toFixed(2)}</span>
                  </div>
                )}
                {invoice.sgst_amount > 0 && (
                  <div className="flex justify-between text-gray-400">
                    <span>SGST (9%):</span>
                    <span>₹{invoice.sgst_amount.toFixed(2)}</span>
                  </div>
                )}
                {invoice.igst_amount > 0 && (
                  <div className="flex justify-between text-gray-400">
                    <span>IGST (18%):</span>
                    <span>₹{invoice.igst_amount.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-white border-t border-zinc-800 pt-2">
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
