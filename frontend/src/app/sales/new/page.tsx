"use client";
import { API_BASE_URL } from '@/utils/api';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getAccessToken, isAuthenticated } from '@/utils/auth';
import DashboardLayout from '@/components/DashboardLayout';
import { useShortcuts } from '@/context/ShortcutContext';
import { useFinancialYear } from '@/context/FinancialYearContext';
import { useCompany } from '@/context/CompanyContext';
import { useToast } from '@/context/ToastContext';
import {
  ChevronDown,
  ChevronUp,
  ScanBarcode,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  Hash,
  Plus,
  Calculator,
  Sparkles,
  RefreshCw,
  Truck,
  QrCode,
  Sliders,
  DollarSign,
  FileText,
  User,
  Scale,
  Search,
  X,
  Tag,
  Check,
  Layers,
  Trash2,
} from 'lucide-react';
import { queueOfflineVoucher, ingestVoucherLocally } from '@/lib/sync/sync-worker';
import { offlineDb } from '@/lib/db/offlineDb';

/**
 * Resolves remembered party rate strictly matching the brand.
 * Prevents cross-brand price and purchase cost leakage (e.g. Modicord vs PIX).
 */
function resolvePartyRateForBrand(
  rates: Record<string, any> | null | undefined,
  productId?: string | null,
  productName?: string | null,
  brand?: string | null
): any | null {
  if (!rates || !productName) return null;
  const cleanName = String(productName).trim().toLowerCase();
  const cleanBrand = String(brand || '').trim().toLowerCase();
  const nameAlpha = cleanName.replace(/[\s\-_/.]/g, '');
  const brandAlpha = cleanBrand.replace(/[\s\-_/.]/g, '');

  // 1. If we have a product ID, check exact ID in rates
  if (productId && rates[productId]) {
    const entry = rates[productId];
    const entryBrand = String(entry.brand || '').trim().toLowerCase();
    // If brand is specified on the line item, verify it matches
    if (!cleanBrand || entryBrand === cleanBrand || !entryBrand) {
      return entry;
    }
  }

  // 2. Strict match by name and brand
  if (cleanBrand) {
    const keyBrand = `${cleanName}|${cleanBrand}`;
    if (rates[keyBrand]) return rates[keyBrand];

    const keyAlpha = `${nameAlpha}|${brandAlpha}`;
    if (rates[keyAlpha]) return rates[keyAlpha];

    // Do NOT fall back to generic cleanName when a brand is specified!
    return null;
  }

  // 3. If unbranded or no brand specified on item
  const unbrandedKey = `${cleanName}|`;
  if (rates[unbrandedKey]) return rates[unbrandedKey];

  if (rates[cleanName]) {
    const entry = rates[cleanName];
    if (!entry.brand || entry.brand.trim() === '') {
      return entry;
    }
  }

  return null;
}

export default function SalesPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { activeCompany, companyId: activeCompanyId } = useCompany();
  const [isPostingImpactOpen, setIsPostingImpactOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const { workingDate, registerSaveHandler, registerAltCCallback, registerDeleteLineHandler, registerEditMasterHandler, setIsCalculatorOpen } = useShortcuts();
  const { activeFY, isReadOnly } = useFinancialYear();
  const [activeRow, setActiveRow] = useState<{ gIndex: number; iIndex: number } | null>(null);
  const [seqPreview, setSeqPreview] = useState('');
  const [companyId, setCompanyId] = useState('');
  const [company, setCompany] = useState<any>(null);
  const [ledgers, setLedgers] = useState<any[]>([]);
  
  const [partyLedgerId, setPartyLedgerId] = useState('');
  const [salesLedgerId, setSalesLedgerId] = useState('');
  const [cgstLedgerId, setCgstLedgerId] = useState('');
  const [sgstLedgerId, setSgstLedgerId] = useState('');
  const [igstLedgerId, setIgstLedgerId] = useState('');
  
  const [enableLedgerMapping, setEnableLedgerMapping] = useState(false);
  const [enableManualInvoice, setEnableManualInvoice] = useState(false);
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [invoiceDate, setInvoiceDate] = useState(workingDate);
  const [companyStateCode, setCompanyStateCode] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  // Progressive disclosure accordion state
  const [activeAccordion, setActiveAccordion] = useState<string | null>(null);

  // 1. Walk-in / Cash Customer Details
  const [buyerName, setBuyerName] = useState('');
  const [buyerPhone, setBuyerPhone] = useState('');
  const [buyerAddress, setBuyerAddress] = useState('');
  const [buyerGstin, setBuyerGstin] = useState('');
  const [buyerStateCode, setBuyerStateCode] = useState('');
  
  // 2. Transport & E-Way Bill Details
  const [transporterName, setTransporterName] = useState('');
  const [transporterId, setTransporterId] = useState('');
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [transportDocNo, setTransportDocNo] = useState('');
  const [transportDocDate, setTransportDocDate] = useState('');
  const [transportMode, setTransportMode] = useState('ROAD');
  const [distanceKm, setDistanceKm] = useState('');

  // 3. Additional Charges & Discount
  const [cartageAmount, setCartageAmount] = useState<number | string>('');
  const [additionalDiscount, setAdditionalDiscount] = useState<number | string>('');

  // 4. Bank & UPI QR on Bill
  const [selectedBankLedgerId, setSelectedBankLedgerId] = useState('');
  const [upiId, setUpiId] = useState('');

  // 5. Terms, Order Ref & Remarks
  const [narration, setNarration] = useState('');
  const [creditDays, setCreditDays] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [poNumber, setPoNumber] = useState('');
  const [poDate, setPoDate] = useState('');
  
  const [categories, setCategories] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [activeSearch, setActiveSearch] = useState<string | null>(null);
  const [brandModalTarget, setBrandModalTarget] = useState<{ gIndex: number; iIndex: number } | null>(null);
  const [brandSearchQuery, setBrandSearchQuery] = useState('');
  const [showBrandInInvoice, setShowBrandInInvoice] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('vouch_show_brand_in_sales_invoice');
      return stored !== null ? stored === 'true' : true;
    }
    return true;
  });
  const [partyRates, setPartyRates] = useState<Record<string, any>>({});
  const [loadingPartyRates, setLoadingPartyRates] = useState(false);
  const [groupedItems, setGroupedItems] = useState<any[]>([
    { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', product_id: '', brand: '', unit: 'PCS', quantity: 1, rate: 0, discount_percent: 0, purchase_cost: 0, last_party_rate: null, last_party_date: null, last_party_vnum: null } ] }
  ]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const barcodeInputRef = React.useRef<HTMLInputElement>(null);

  // Close brand modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && brandModalTarget) {
        setBrandModalTarget(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [brandModalTarget]);

  // Tally Alt + D: Delete current line item
  useEffect(() => {
    return registerDeleteLineHandler(() => {
      if (activeRow) {
        removeRow(activeRow.gIndex, activeRow.iIndex);
      } else {
        setGroupedItems(prev => {
          const lastGIdx = prev.length - 1;
          if (lastGIdx < 0) return prev;
          const lastGroup = prev[lastGIdx];
          if (lastGroup.items.length > 1) {
            return prev.map((g, idx) => idx === lastGIdx ? { ...g, items: g.items.slice(0, -1) } : g);
          } else if (prev.length > 1) {
            return prev.slice(0, -1);
          }
          return prev;
        });
      }
    });
  }, [registerDeleteLineHandler, activeRow]);

  // Tally Ctrl + Enter: Edit focused Master inline
  useEffect(() => {
    return registerEditMasterHandler(() => {
      if (activeRow) {
        const item = groupedItems[activeRow.gIndex]?.items[activeRow.iIndex];
        if (item?.product_id) {
          window.open(`/inventory/items?edit=${item.product_id}`, '_blank');
          return;
        }
      }
      if (partyLedgerId) {
        window.open(`/sales/customers/${partyLedgerId}`, '_blank');
      }
    });
  }, [registerEditMasterHandler, activeRow, groupedItems, partyLedgerId]);

  useEffect(() => {
    if (workingDate) {
      setInvoiceDate(workingDate);
    }
  }, [workingDate]);

  useEffect(() => {
    if (activeFY) {
      if (invoiceDate < activeFY.start_date || invoiceDate > activeFY.end_date) {
        setInvoiceDate(activeFY.start_date);
      }
    }
  }, [activeFY]);

  useEffect(() => {
    const fetchSeq = async () => {
      try {
        const token = getAccessToken();
        const res = await axios.get(
          `${API_BASE_URL}/api/v1/financial-years/sequence-preview/?voucher_type=SALES&date=${invoiceDate}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (res.data?.success && res.data.data?.preview_number) {
          setSeqPreview(res.data.data.preview_number);
        }
      } catch (err) {
        // quiet fallback
      }
    };
    if (companyId) {
      fetchSeq();
    }
  }, [invoiceDate, companyId]);


  useEffect(() => {
    registerAltCCallback((newEntity: any) => {
      if (newEntity?.group_name || newEntity?.ledger_type) {
        setLedgers((prev) => [...prev, newEntity]);
        setPartyLedgerId(newEntity.id);
        const disc = Number(newEntity.discount_percent || 0);
        if (disc > 0) {
          setGroupedItems(prev => prev.map((group: any) => ({
            ...group,
            items: group.items.map((item: any) => ({
              ...item,
              discount_percent: disc
            }))
          })));
        }
      }
    });
  }, [registerAltCCallback]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push('/login');
      return;
    }
    const targetCid = activeCompanyId || (typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') : null);
    fetchBaseData(targetCid || undefined);
  }, [router]);

  // Reactive listener: when user switches company in DashboardLayout, automatically switch everything
  useEffect(() => {
    if (activeCompanyId && activeCompanyId !== companyId) {
      setPartyLedgerId('');
      setPartyRates({});
      setSelectedBankLedgerId('');
      setGroupedItems([{
        group_title: 'Main Items',
        items: [{
          product_id: null,
          product_name: '',
          sku: '',
          hsn_code: '',
          quantity: 1,
          unit: 'PCS',
          rate: 0,
          discount_percent: 0,
          purchase_cost: 0,
          taxable_amount: 0,
          tax_rate: 18,
          cgst_rate: 9,
          sgst_rate: 9,
          igst_rate: 0,
          cgst_amount: 0,
          sgst_amount: 0,
          igst_amount: 0,
          total_amount: 0,
          is_custom_item: false,
          brand: '',
          last_party_rate: null,
          last_party_date: null,
          last_party_vnum: null
        }]
      }]);
      if (activeCompany) {
        setCompany(activeCompany);
        setCompanyId(activeCompany.id);
        setCompanyStateCode(activeCompany.state_code || '');
        setUpiId(activeCompany.upi_id || '');
        setEnableLedgerMapping(activeCompany.settings?.enable_ledger_mapping || false);
        setEnableManualInvoice(activeCompany.settings?.enable_manual_invoice_number || false);
      }
      fetchBaseData(activeCompanyId);
    }
  }, [activeCompanyId, activeCompany]);

  const fetchBaseData = async (targetCompanyId?: string) => {
    try {
      const resolvedCompanyId = targetCompanyId || activeCompanyId || (typeof window !== 'undefined' ? localStorage.getItem('vouch_active_company_id') : null);

      // Purge legacy unscoped offline cache keys to prevent cross-tenant contamination
      offlineDb.masters.bulkDelete(['company', 'ledgers', 'categories', 'products']).catch(() => {});

      // 1. Attempt to load company-scoped cached masters immediately
      if (resolvedCompanyId) {
        try {
          const [cachedComp, cachedLedgers, cachedCats, cachedProds] = await Promise.all([
            offlineDb.masters.get(`company_${resolvedCompanyId}`),
            offlineDb.masters.get(`ledgers_${resolvedCompanyId}`),
            offlineDb.masters.get(`categories_${resolvedCompanyId}`),
            offlineDb.masters.get(`products_${resolvedCompanyId}`),
          ]);

          if (cachedComp?.data) {
            setCompany(cachedComp.data);
            setCompanyId(cachedComp.data.id);
            setCompanyStateCode(cachedComp.data.state_code || '');
            setUpiId(cachedComp.data.upi_id || '');
            setEnableLedgerMapping(cachedComp.data.settings?.enable_ledger_mapping || false);
            setEnableManualInvoice(cachedComp.data.settings?.enable_manual_invoice_number || false);
          }
          if (cachedLedgers?.data?.length) {
            setLedgers(cachedLedgers.data);
            applyDefaultLedgers(cachedLedgers.data, cachedComp?.data?.settings?.enable_ledger_mapping || false, resolvedCompanyId);
          }
          if (cachedCats?.data?.length) setCategories(cachedCats.data);
          if (cachedProds?.data?.length) setProducts(cachedProds.data);
        } catch (cacheErr) {
          console.warn('Could not read from local offline cache', cacheErr);
        }
      }

      // 2. Fetch fresh masters from server
      const token = getAccessToken();
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      if (resolvedCompanyId) {
        headers['X-Company-ID'] = resolvedCompanyId;
      }
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const compList = Array.isArray(compRes.data) ? compRes.data : (compRes.data?.data || []);
      const comp = (resolvedCompanyId ? compList.find((c: any) => c.id === resolvedCompanyId) : null) || compList[0];
      const cId = comp?.id;
      if (!cId) return;

      setCompany(comp);
      setCompanyId(cId);
      setCompanyStateCode(comp.state_code || '');
      setUpiId(comp.upi_id || '');
      
      const isMappingEnabled = comp.settings?.enable_ledger_mapping || false;
      setEnableLedgerMapping(isMappingEnabled);
      setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);

      // Cache scoped by company
      offlineDb.masters.put({ key: `company_${cId}`, data: comp, updatedAt: Date.now() }).catch(() => {});

      const [ledgersRes, catsRes, prodsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cId}/`, { headers }).catch(() => ({ data: { data: [] } }))
      ]);
      const ledgerList = ledgersRes.data?.data || (Array.isArray(ledgersRes.data) ? ledgersRes.data : []);
      const catList = catsRes.data?.data || (Array.isArray(catsRes.data) ? catsRes.data : []);
      const prodList = prodsRes.data?.data || (Array.isArray(prodsRes.data) ? prodsRes.data : []);

      setLedgers(ledgerList);
      setCategories(catList);
      setProducts(prodList);
      
      // Save freshly fetched data to company-scoped offline DB
      offlineDb.masters.put({ key: `ledgers_${cId}`, data: ledgerList, updatedAt: Date.now() }).catch(() => {});
      offlineDb.masters.put({ key: `categories_${cId}`, data: catList, updatedAt: Date.now() }).catch(() => {});
      offlineDb.masters.put({ key: `products_${cId}`, data: prodList, updatedAt: Date.now() }).catch(() => {});

      applyDefaultLedgers(ledgerList, isMappingEnabled, cId);
    } catch (err) {
      console.error('Network fetch failed, continuing with offline cache if available:', err);
    } finally {
      setLoading(false);
    }
  };

  const applyDefaultLedgers = (ledgerList: any[], isMappingEnabled: boolean, cId?: string) => {
    const debtors = ledgerList.filter((l: any) => 
      l.ledger_type === 'CUSTOMER' ||
      (l.group && (l.group.toLowerCase().includes('debtor') || l.group.toLowerCase().includes('customer')))
    );
    const party = debtors.find((l: any) => l.name.toLowerCase().includes('customer')) || debtors[0];
    const genericSales = ledgerList.find((l:any) => l.name === 'Sales Account' || l.name === 'Local Sales') || ledgerList.find((l:any) => l.name.toLowerCase().includes('sales'));
    const sales = isMappingEnabled 
        ? ledgerList.find((l:any) => l.name.toLowerCase().includes('sales')) 
        : genericSales;
        
    const cgst = ledgerList.find((l:any) => l.name === 'CGST' || l.name === 'Output CGST' || l.name.toLowerCase().includes('cgst'));
    const sgst = ledgerList.find((l:any) => l.name === 'SGST' || l.name === 'Output SGST' || l.name.toLowerCase().includes('sgst'));
    const igst = ledgerList.find((l:any) => l.name === 'IGST' || l.name === 'Output IGST' || l.name.toLowerCase().includes('igst'));
    
    if (party) {
      setPartyLedgerId(party.id);
      if (cId) fetchPartyRates(party.id, cId);
      const partyDisc = Number(party.discount_percent || 0);
      if (partyDisc > 0) {
        setGroupedItems(prev => prev.map((group: any) => ({
          ...group,
          items: group.items.map((item: any) => ({
            ...item,
            discount_percent: partyDisc
          }))
        })));
      }
    }
    if (sales) setSalesLedgerId(sales.id);
    else if (genericSales) setSalesLedgerId(genericSales.id);
    if (cgst) setCgstLedgerId(cgst.id);
    if (sgst) setSgstLedgerId(sgst.id);
    if (igst) setIgstLedgerId(igst.id);
  };

  const fetchPartyRates = async (pId: string, currentCompanyId?: string) => {
    const targetCompanyId = currentCompanyId || companyId;
    if (!pId || !targetCompanyId) return;
    try {
      setLoadingPartyRates(true);
      const token = getAccessToken();
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.get(
        `${API_BASE_URL}/api/v1/accounting/party-rates/?party_id=${pId}&company_id=${targetCompanyId}`,
        { headers }
      );
      if (res.data?.success) {
        const rates = res.data.data || {};
        setPartyRates(rates);

        // Auto-populate past party rates onto any already-selected line items
        setGroupedItems(prev => prev.map((group: any) => ({
          ...group,
          items: group.items.map((item: any) => {
            if (!item.product_name) return item;
            const pastRateInfo = resolvePartyRateForBrand(rates, item.product_id, item.product_name, item.brand);
            const purchaseCost = (item.purchase_cost && Number(item.purchase_cost) > 0)
              ? Number(item.purchase_cost)
              : (pastRateInfo?.purchase_cost ?? 0);
            if (pastRateInfo && Number(pastRateInfo.rate) > 0) {
              return {
                ...item,
                rate: Number(pastRateInfo.rate),
                last_party_rate: Number(pastRateInfo.rate),
                last_party_date: pastRateInfo.voucher_date,
                last_party_vnum: pastRateInfo.voucher_number,
                purchase_cost: purchaseCost
              };
            }
            return {
              ...item,
              last_party_rate: null,
              last_party_date: null,
              last_party_vnum: null,
              purchase_cost: purchaseCost
            };
          })
        })));
      }
    } catch (err) {
      console.error('Failed to fetch party rates', err);
    } finally {
      setLoadingPartyRates(false);
    }
  };

  const handlePartyChange = (selectedId: string) => {
    setPartyLedgerId(selectedId);
    fetchPartyRates(selectedId);
    const party = ledgers.find(l => l.id === selectedId);
    const disc = Number(party?.discount_percent || 0);

    // If Cash or Bank ledger, auto-expand walk-in buyer details
    const isCashOrBank = party && (
      party.ledger_type === 'CASH' ||
      party.ledger_type === 'BANK' ||
      party.group?.toLowerCase().includes('cash') ||
      party.group?.toLowerCase().includes('bank') ||
      party.name?.toLowerCase().includes('cash')
    );
    if (isCashOrBank) {
      setActiveAccordion('buyer');
    }

    // Auto-populate customer's default discount across all line items
    setGroupedItems(prev => prev.map((group: any) => ({
      ...group,
      items: group.items.map((item: any) => ({
        ...item,
        discount_percent: disc
      }))
    })));

    if (disc > 0) {
      toast.info(`Default ${disc}% discount applied for ${party?.name}`, "You can edit discount per item in the table below if needed.");
    }
  };

  const handleToggleManualInvoice = (manual: boolean) => {
    setEnableManualInvoice(manual);
    if (manual && !invoiceNumber && seqPreview) {
      setInvoiceNumber(seqPreview);
    }

    if (manual) {
      toast.info("Switched to Manual Invoice Numbering", "You can specify custom invoice numbers. Saved to your settings.");
    } else {
      toast.info("Switched to Automatic Invoice Numbering", "Invoices will be sequentially numbered automatically (GST Rule 46b).");
    }

    // Persist setting to company settings asynchronously
    const targetCid = companyId || company?.id;
    if (targetCid) {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      axios.patch(`${API_BASE_URL}/api/v1/companies/${targetCid}/update_settings/`, {
        enable_manual_invoice_number: manual
      }, { headers }).catch(err => {
        console.warn('Could not persist manual invoice setting to backend', err);
      });

      if (company) {
        const updatedComp = {
          ...company,
          settings: {
            ...(company.settings || {}),
            enable_manual_invoice_number: manual
          }
        };
        setCompany(updatedComp);
        offlineDb.masters.put({ key: `company_${targetCid}`, data: updatedComp, updatedAt: Date.now() }).catch(() => {});
      }
    }
  };

  const handleSave = async () => {
    if (!partyLedgerId || !salesLedgerId) {
      toast.warning("Please select Party and Sales ledgers!");
      return;
    }

    if (enableManualInvoice && !invoiceNumber.trim()) {
      toast.warning("Manual Invoice Number Required", "Please enter an invoice number, or toggle to Auto Numbering.");
      return;
    }
    
    // Flatten grouped items for payload
    const flatItems: any[] = [];
    for (let i=0; i<groupedItems.length; i++) {
        const group = groupedItems[i];
        if (!group.category_id) {
          toast.warning(`Category Group ${i+1} is missing a category selection!`);
          return;
        }
        for (let j=0; j<group.items.length; j++) {
            const item = group.items[j];
            if (!item.product_name) {
              toast.warning(`Category Group ${i+1}, Row ${j+1} is missing a product name!`);
              return;
            }
            if (item.quantity <= 0) {
              toast.warning(`Category Group ${i+1}, Row ${j+1} must have a quantity > 0!`);
              return;
            }
            flatItems.push({
                ...item,
                category_id: group.category_id,
                hsn_code: group.hsn_code,
                gst_rate: group.gst_rate
            });
        }
    }
    
    setSaving(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const payload: any = {
        company_id: companyId,
        party_ledger_id: partyLedgerId,
        voucher_number: enableManualInvoice && invoiceNumber.trim() ? invoiceNumber.trim() : undefined,
        voucher_date: invoiceDate,
        items: flatItems.map((it: any) => {
          const itemCopy = { ...it };
          if (!itemCopy.product_id) delete itemCopy.product_id;
          if (!itemCopy.category_id) delete itemCopy.category_id;
          return itemCopy;
        }),
        post_immediately: true,
        is_reverse_charge: false,
      };
      if (buyerName.trim()) payload.buyer_name = buyerName.trim();
      if (buyerPhone.trim()) payload.buyer_phone = buyerPhone.trim();
      if (buyerAddress.trim()) payload.buyer_address = buyerAddress.trim();
      if (buyerGstin.trim()) payload.buyer_gstin = buyerGstin.trim().toUpperCase();
      if (buyerStateCode.trim()) payload.buyer_state_code = buyerStateCode.trim();
      
      if (salesLedgerId) payload.sales_ledger_id = salesLedgerId;
      if (cgstLedgerId) payload.cgst_ledger_id = cgstLedgerId;
      if (sgstLedgerId) payload.sgst_ledger_id = sgstLedgerId;
      if (igstLedgerId) payload.igst_ledger_id = igstLedgerId;
      if (cartageAmount && Number(cartageAmount) > 0) {
        payload.cartage_amount = Number(cartageAmount);
      }
      if (additionalDiscount && Number(additionalDiscount) > 0) {
        payload.discount_amount = Number(additionalDiscount);
      }
      if (narration.trim()) payload.narration = narration.trim();
      if (dueDate) payload.due_date = dueDate;
      if (poNumber.trim()) payload.po_number = poNumber.trim();
      if (poDate) payload.po_date = poDate;
      if (vehicleNumber.trim() || transporterName.trim() || transporterId.trim() || transportDocNo.trim()) {
        payload.transport_details = {
          transporter_name: transporterName.trim(),
          transporter_id: transporterId.trim().toUpperCase(),
          vehicle_number: vehicleNumber.trim().toUpperCase(),
          transport_doc_no: transportDocNo.trim(),
          transport_doc_date: transportDocDate,
          transport_mode: transportMode,
          distance_km: distanceKm ? Number(distanceKm) : undefined,
        };
      }
      if (selectedBankLedgerId) {
        payload.bank_ledger_id = selectedBankLedgerId;
      }
      if (upiId.trim()) {
        payload.upi_id = upiId.trim();
      }
      
      try {
        const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/sales-invoice/`, payload, { headers, timeout: 8000 });
        if (res.data?.voucher) {
          const vData = res.data.voucher;
          await ingestVoucherLocally(companyId, {
            ...vData,
            voucherNumber: vData.voucher_number || vData.voucherNumber || res.data.voucher_number,
            voucherDate: vData.voucher_date || vData.voucherDate || invoiceDate,
            totalAmount: vData.total_amount || vData.totalAmount || grandTotal,
            voucherType: 'SALES',
            partyName: selectedParty?.name || vData.party_name || vData.partyName,
            partyLedgerId: selectedParty?.id || vData.party_ledger_id || vData.partyLedgerId,
          });
        }
        toast.success(`Sales Invoice generated!`, `Voucher: ${res.data.voucher_number}`);
        router.push('/sales');
        router.refresh();
      } catch (postErr: any) {
        // If offline or network error, store in local IndexedDB outbox!
        const isNetworkErr = !navigator.onLine || postErr.code === 'ERR_NETWORK' || !postErr.response;
        if (isNetworkErr) {
          const offlineRes = await queueOfflineVoucher('SALES', payload, invoiceDate);
          await ingestVoucherLocally(companyId, {
            id: offlineRes.localId,
            voucherType: 'SALES',
            voucherNumber: offlineRes.localId,
            voucherDate: invoiceDate,
            dueDate: (payload as any).due_date || invoiceDate,
            totalAmount: grandTotal,
            partyName: selectedParty?.name || 'Customer',
            partyLedgerId: selectedParty?.id || null,
            status: 'POSTED',
          });
          toast.success(
            "Saved Offline",
            `Saved to your device. Will sync automatically when connected.`
          );
          router.push('/sales');
          router.refresh();
        } else {
          throw postErr;
        }
      }
    } catch (err: any) {
      console.error(err);
      toast.error("Failed to save sales invoice", err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    return registerSaveHandler(handleSave);
  }, [registerSaveHandler, handleSave]);

  const updateGroup = (gIndex: number, field: string, value: any) => {
    const newGroups = [...groupedItems];
    (newGroups[gIndex] as any)[field] = value;
    if (field === 'category_id') {
      const cat = categories.find(c => c.id === value);
      if (cat) {
        newGroups[gIndex].hsn_code = cat.hsn_code || '';
        newGroups[gIndex].gst_rate = Number(cat.gst_rate) || 18;
      }
      // Re-evaluate existing items in this group against the newly selected category
      newGroups[gIndex].items = newGroups[gIndex].items.map((item: any) => {
        if (!item.product_name) return item;
        const cleanVal = String(item.product_name || '').trim().toLowerCase();
        const alphaVal = cleanVal.replace(/[\s\-_/.]/g, '');
        const catProds = products.filter(p => p.category_id === value);
        const match = 
          catProds.find((p: any) => 
            (item.brand && (p.brand || '').toLowerCase() === item.brand.toLowerCase()) &&
            (p.name.toLowerCase() === cleanVal || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
          ) ||
          catProds.find((p: any) => 
            p.name.toLowerCase() === cleanVal ||
            p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal ||
            (p.alias && (p.alias.toLowerCase() === cleanVal || p.alias.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)) ||
            p.sku.toLowerCase() === cleanVal
          );
        if (match) {
          const mrp = parseFloat(match.selling_price) || 0;
          return {
            ...item,
            product_id: match.id,
            brand: match.brand || item.brand || '',
            unit: match.unit || item.unit || 'PCS',
            stock_quantity: match.stock_quantity ?? 0,
            rate: mrp > 0 ? mrp : item.rate,
            discount_percent: (!item.discount_percent || Number(item.discount_percent) === 0) && currentPartyDiscount > 0
              ? currentPartyDiscount
              : item.discount_percent
          };
        }
        return item;
      });
    }
    setGroupedItems(newGroups);
  };

  const selectProduct = (gIndex: number, iIndex: number, prod: any) => {
    const newGroups = [...groupedItems];
    const group = newGroups[gIndex];
    const item = group.items[iIndex];
    
    item.product_name = prod.name;
    item.product_id = prod.id;
    item.brand = prod.brand || '';
    item.unit = prod.unit || 'PCS';
    item.stock_quantity = prod.stock_quantity ?? 0;
    
    const catalogMrp = parseFloat(prod.selling_price) || 0;
    item.mrp = catalogMrp;
    
    // Look up remembered sales rate for this party strictly for this brand
    const pastRateInfo = resolvePartyRateForBrand(partyRates, prod.id, prod.name, prod.brand);
    const purchaseCost = parseFloat(prod.purchase_price) > 0 
      ? parseFloat(prod.purchase_price) 
      : (pastRateInfo?.purchase_cost ?? 0);
    item.purchase_cost = purchaseCost;

    if (pastRateInfo && Number(pastRateInfo.rate) > 0) {
      item.rate = Number(pastRateInfo.rate);
      item.last_party_rate = Number(pastRateInfo.rate);
      item.last_party_date = pastRateInfo.voucher_date;
      item.last_party_vnum = pastRateInfo.voucher_number;
    } else if (catalogMrp > 0) {
      item.rate = catalogMrp;
      item.last_party_rate = null;
      item.last_party_date = null;
      item.last_party_vnum = null;
    } else {
      item.rate = 0;
      item.last_party_rate = null;
      item.last_party_date = null;
      item.last_party_vnum = null;
    }
    
    if ((!item.discount_percent || Number(item.discount_percent) === 0) && currentPartyDiscount > 0) {
      item.discount_percent = currentPartyDiscount;
    }
    
    if (!group.category_id && prod.category_id) {
      group.category_id = prod.category_id;
      const cat = categories.find(c => c.id === prod.category_id);
      if (cat) {
        group.hsn_code = cat.hsn_code || '';
        group.gst_rate = Number(cat.gst_rate) || 18;
      }
    }
    
    setGroupedItems(newGroups);
  };

  const selectBrand = (gIndex: number, iIndex: number, brandName: string) => {
    const newGroups = [...groupedItems];
    const group = newGroups[gIndex];
    const item = group.items[iIndex];
    
    item.brand = brandName;
    
    const cleanVal = String(item.product_name || '').trim().toLowerCase();
    const alphaVal = cleanVal.replace(/[\s\-_/.]/g, '');
    
    if (cleanVal) {
      const catProds = products.filter((p: any) => !group.category_id || p.category_id === group.category_id);
      const match = 
        catProds.find((p: any) => 
          (p.brand || '').trim().toLowerCase() === brandName.trim().toLowerCase() &&
          (p.name.toLowerCase() === cleanVal || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
        ) ||
        products.find((p: any) => 
          (p.brand || '').trim().toLowerCase() === brandName.trim().toLowerCase() &&
          (p.name.toLowerCase() === cleanVal || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
        );
        
      if (match) {
        item.product_id = match.id;
        item.brand = match.brand || brandName;
        item.unit = match.unit || 'PCS';
        item.stock_quantity = match.stock_quantity ?? 0;
        const catalogMrp = parseFloat(match.selling_price) || 0;
        item.mrp = catalogMrp;

        // Look up remembered sales rate strictly for this brand
        const pastRateInfo = resolvePartyRateForBrand(partyRates, match.id, match.name, match.brand || brandName);
        const purchaseCost = parseFloat(match.purchase_price) > 0 
          ? parseFloat(match.purchase_price) 
          : (pastRateInfo?.purchase_cost ?? 0);
        item.purchase_cost = purchaseCost;

        if (pastRateInfo && Number(pastRateInfo.rate) > 0) {
          item.rate = Number(pastRateInfo.rate);
          item.last_party_rate = Number(pastRateInfo.rate);
          item.last_party_date = pastRateInfo.voucher_date;
          item.last_party_vnum = pastRateInfo.voucher_number;
        } else if (catalogMrp > 0) {
          item.rate = catalogMrp;
          item.last_party_rate = null;
          item.last_party_date = null;
          item.last_party_vnum = null;
        }
      } else {
        item.last_party_rate = null;
        item.last_party_date = null;
        item.last_party_vnum = null;
      }
    }
    
    setGroupedItems(newGroups);
  };

  const updateItem = (gIndex: number, iIndex: number, field: string, value: any) => {
    const newGroups = [...groupedItems];
    const group = newGroups[gIndex];
    const item = group.items[iIndex];
    (item as any)[field] = value;

    if (field === 'brand') {
      selectBrand(gIndex, iIndex, value);
      return;
    }

    if (field === 'product_name') {
      const cleanVal = String(value || '').trim().toLowerCase();
      const alphaVal = cleanVal.replace(/[\s\-_/.]/g, '');
      
      if (cleanVal) {
        // Prioritize products in this group's category
        const catProds = products.filter((p: any) => !group.category_id || p.category_id === group.category_id);
        
        // 1. If item already has a brand, match product with BOTH name and brand!
        let match = catProds.find((p: any) => 
          item.brand && (p.brand || '').trim().toLowerCase() === item.brand.trim().toLowerCase() &&
          (p.name.toLowerCase() === cleanVal || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
        );

        // 2. Check if user typed query containing brand like "PIX B 55"
        if (!match) {
          match = catProds.find((p: any) => 
            p.brand && (
              cleanVal.includes(p.brand.toLowerCase()) && 
              (cleanVal.includes(p.name.toLowerCase()) || alphaVal.includes(p.name.toLowerCase().replace(/[\s\-_/.]/g, '')))
            )
          );
        }

        // 3. Match by name: if multiple exist, prioritize product with stock > 0, then rate > 0
        if (!match) {
          const matches = catProds.filter((p: any) => 
            p.name.toLowerCase() === cleanVal ||
            p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal ||
            (p.alias && (p.alias.toLowerCase() === cleanVal || p.alias.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)) ||
            p.sku.toLowerCase() === cleanVal
          );
          if (matches.length > 0) {
            match = matches.find((p: any) => Number(p.stock_quantity ?? 0) > 0) ||
                    matches.find((p: any) => parseFloat(p.selling_price || 0) > 0) ||
                    matches[0];
          }
        }

        // 4. Global fallback across categories
        if (!match) {
          const globalMatches = products.filter((p: any) => 
            p.name.toLowerCase() === cleanVal ||
            p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal ||
            (p.alias && (p.alias.toLowerCase() === cleanVal || p.alias.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)) ||
            p.sku.toLowerCase() === cleanVal
          );
          if (globalMatches.length > 0) {
            match = (item.brand ? globalMatches.find((p: any) => (p.brand || '').toLowerCase() === item.brand.toLowerCase()) : null) ||
                    globalMatches.find((p: any) => Number(p.stock_quantity ?? 0) > 0) ||
                    globalMatches.find((p: any) => parseFloat(p.selling_price || 0) > 0) ||
                    globalMatches[0];
          }
        }

        if (match) {
          const catalogMrp = parseFloat(match.selling_price) || 0;
          item.mrp = catalogMrp;

          const pastRateInfo = resolvePartyRateForBrand(partyRates, match.id, match.name, match.brand || item.brand);
          const purchaseCost = parseFloat(match.purchase_price) > 0 
            ? parseFloat(match.purchase_price) 
            : (pastRateInfo?.purchase_cost ?? 0);
          item.purchase_cost = purchaseCost;

          if (pastRateInfo && Number(pastRateInfo.rate) > 0) {
            item.rate = Number(pastRateInfo.rate);
            item.last_party_rate = Number(pastRateInfo.rate);
            item.last_party_date = pastRateInfo.voucher_date;
            item.last_party_vnum = pastRateInfo.voucher_number;
          } else if (catalogMrp > 0) {
            item.rate = catalogMrp;
            item.last_party_rate = null;
            item.last_party_date = null;
            item.last_party_vnum = null;
          } else {
            item.rate = 0;
            item.last_party_rate = null;
            item.last_party_date = null;
            item.last_party_vnum = null;
          }

          item.product_id = match.id;
          item.brand = match.brand || item.brand || '';
          item.unit = match.unit || 'PCS';
          item.stock_quantity = match.stock_quantity ?? 0;
          
          // Auto-apply customer discount if item currently has 0 discount
          if ((!item.discount_percent || Number(item.discount_percent) === 0) && currentPartyDiscount > 0) {
            item.discount_percent = currentPartyDiscount;
          }

          // If group category is unselected, auto-set to matched product's category
          if (!group.category_id && match.category_id) {
            group.category_id = match.category_id;
            const cat = categories.find(c => c.id === match.category_id);
            if (cat) {
              group.hsn_code = cat.hsn_code || '';
              group.gst_rate = Number(cat.gst_rate) || 18;
            }
          }
        }
      }
    }
    setGroupedItems(newGroups);
  };

  const selectedParty = ledgers.find(l => l.id === partyLedgerId);
  const currentPartyDiscount = Number(selectedParty?.discount_percent || 0);

  const addRow = (gIndex: number) => {
    const newGroups = [...groupedItems];
    newGroups[gIndex].items.push({ 
      product_name: '', 
      product_id: '',
      brand: '',
      unit: 'PCS',
      quantity: 1, 
      rate: 0, 
      discount_percent: currentPartyDiscount,
      purchase_cost: 0,
      last_party_rate: null,
      last_party_date: null,
      last_party_vnum: null
    });
    setGroupedItems(newGroups);
  };

  const removeRow = (gIndex: number, iIndex: number) => {
    const newGroups = [...groupedItems];
    if (newGroups[gIndex].items.length === 1) {
      if (newGroups.length > 1) {
        setGroupedItems(newGroups.filter((_, idx) => idx !== gIndex));
      } else {
        newGroups[gIndex].items[0] = {
          product_name: '',
          product_id: '',
          brand: '',
          unit: 'PCS',
          quantity: 1,
          rate: 0,
          discount_percent: currentPartyDiscount,
          purchase_cost: 0,
          last_party_rate: null,
          last_party_date: null,
          last_party_vnum: null
        };
        setGroupedItems(newGroups);
      }
      return;
    }
    newGroups[gIndex].items = newGroups[gIndex].items.filter((_: any, i: number) => i !== iIndex);
    setGroupedItems(newGroups);
  };

  const addCategoryGroup = () => {
    setGroupedItems([
      ...groupedItems, 
      { 
        category_id: '', 
        hsn_code: '', 
        gst_rate: 18, 
        items: [ 
          { product_name: '', product_id: '', brand: '', unit: 'PCS', quantity: 1, rate: 0, discount_percent: currentPartyDiscount } 
        ] 
      }
    ]);
  };

  const handleBarcodeScan = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const rawCode = barcodeInput.trim();
    if (!rawCode) return;

    const codeLower = rawCode.toLowerCase();
    const matchedProd = products.find((p: any) => 
      (p.barcode && String(p.barcode).trim().toLowerCase() === codeLower) ||
      (p.sku && String(p.sku).trim().toLowerCase() === codeLower) ||
      (p.alias && String(p.alias).trim().toLowerCase() === codeLower) ||
      (p.name && String(p.name).trim().toLowerCase() === codeLower)
    );

    if (!matchedProd) {
      toast.error(`Barcode / SKU "${rawCode}" not found in catalog.`);
      setBarcodeInput('');
      return;
    }

    const newGroups = [...groupedItems];

    // Check if already in current line items -> increment quantity
    for (let g = 0; g < newGroups.length; g++) {
      for (let i = 0; i < newGroups[g].items.length; i++) {
        const it = newGroups[g].items[i];
        if (it.product_id === matchedProd.id) {
          const newQty = (Number(it.quantity) || 0) + 1;
          it.quantity = newQty;
          setGroupedItems(newGroups);
          toast.success(`Incremented ${matchedProd.name} (Qty: ${newQty})`);
          setBarcodeInput('');
          return;
        }
      }
    }

    // Determine rate: past party rate strictly for brand or catalog selling price
    const pastRateInfo = resolvePartyRateForBrand(partyRates, matchedProd.id, matchedProd.name, matchedProd.brand);
    const catalogMrp = parseFloat(matchedProd.selling_price) || 0;
    const purchaseCost = parseFloat(matchedProd.purchase_price) > 0 
      ? parseFloat(matchedProd.purchase_price) 
      : (pastRateInfo?.purchase_cost ?? 0);
    const rate = (pastRateInfo && Number(pastRateInfo.rate) > 0) ? Number(pastRateInfo.rate) : catalogMrp;

    const newItem = {
      product_name: matchedProd.name,
      product_id: matchedProd.id,
      brand: matchedProd.brand || '',
      unit: matchedProd.unit || 'PCS',
      stock_quantity: matchedProd.stock_quantity ?? 0,
      quantity: 1,
      rate: rate,
      mrp: catalogMrp,
      purchase_cost: purchaseCost,
      discount_percent: currentPartyDiscount > 0 ? currentPartyDiscount : 0,
      last_party_rate: pastRateInfo ? Number(pastRateInfo.rate) : null,
      last_party_date: pastRateInfo ? pastRateInfo.voucher_date : null,
      last_party_vnum: pastRateInfo ? pastRateInfo.voucher_number : null,
    };

    const targetCatId = matchedProd.category_id;
    let targetGroupIdx = newGroups.findIndex((g: any) => g.category_id === targetCatId);

    if (targetGroupIdx === -1 && newGroups.length === 1 && !newGroups[0].items[0]?.product_id && !newGroups[0].items[0]?.product_name) {
      targetGroupIdx = 0;
      if (targetCatId) {
        newGroups[0].category_id = targetCatId;
        const cat = categories.find(c => c.id === targetCatId);
        if (cat) {
          newGroups[0].hsn_code = cat.hsn_code || '';
          newGroups[0].gst_rate = Number(cat.gst_rate) || 18;
        }
      }
      newGroups[0].items[0] = newItem;
    } else if (targetGroupIdx !== -1) {
      if (newGroups[targetGroupIdx].items.length === 1 && !newGroups[targetGroupIdx].items[0]?.product_id && !newGroups[targetGroupIdx].items[0]?.product_name) {
        newGroups[targetGroupIdx].items[0] = newItem;
      } else {
        newGroups[targetGroupIdx].items.push(newItem);
      }
    } else {
      const cat = categories.find(c => c.id === targetCatId);
      newGroups.push({
        category_id: targetCatId || '',
        hsn_code: cat?.hsn_code || '',
        gst_rate: Number(cat?.gst_rate) || 18,
        items: [newItem]
      });
    }

    setGroupedItems(newGroups);
    toast.success(`Added ${matchedProd.name}`);
    setBarcodeInput('');
  };
  
  const removeCategoryGroup = (gIndex: number) => {
    if (groupedItems.length === 1) return;
    setGroupedItems(groupedItems.filter((_: any, i: number) => i !== gIndex));
  };

  // Flatten for calculations
  const allItems = groupedItems.flatMap((g: any) => g.items.map((i: any) => ({...i, gst_rate: g.gst_rate})));

  // Calculate Subtotals
  const grossTotal = allItems.reduce((sum, item) => sum + (Number(item.quantity) * Number(item.rate)), 0);
  const totalItemDiscount = allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const disc = gross * ((Number(item.discount_percent) || 0) / 100);
    return sum + disc;
  }, 0);
  const taxableSubtotal = Math.max(0, grossTotal - totalItemDiscount);
  const totalTax = allItems.reduce((sum, item) => {
      const gross = Number(item.quantity) * Number(item.rate);
      const discount = gross * ((Number(item.discount_percent) || 0) / 100);
      const taxable = gross - discount;
      return sum + (taxable * (Number(item.gst_rate) / 100));
  }, 0);
  const cartageVal = Number(cartageAmount) || 0;
  const additionalDiscVal = Number(additionalDiscount) || 0;
  const unroundedGrandTotal = Math.max(0, allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const discount = gross * (Number(item.discount_percent)/100);
    const taxable = gross - discount;
    return sum + taxable + (taxable * (Number(item.gst_rate)/100));
  }, 0) + cartageVal - additionalDiscVal);

  let grandTotal = 0;
  let roundOff = 0;
  if (unroundedGrandTotal > 0) {
    const integerPart = Math.floor(unroundedGrandTotal);
    const decimalPart = Math.round((unroundedGrandTotal - integerPart) * 100) / 100;
    grandTotal = decimalPart < 0.5 ? integerPart : integerPart + 1;
    roundOff = Math.round((grandTotal - unroundedGrandTotal) * 100) / 100;
  }

  const isInterState = Boolean(selectedParty?.state_code && companyStateCode && selectedParty.state_code !== companyStateCode);

  if (loading) return <DashboardLayout><div className="flex items-center justify-center h-full text-muted-foreground">Loading invoice form...</div></DashboardLayout>;

  interface MissingProfileField {
    key: string;
    label: string;
    requirement: string;
    instruction: string;
    example?: string;
  }

  const missingProfileFields: MissingProfileField[] = [];

  if (company) {
    if (!company.name?.trim()) {
      missingProfileFields.push({
        key: 'name',
        label: 'Firm / Business Name',
        requirement: 'Seller Identification',
        instruction: 'Enter your registered trade or business legal name (as printed on your GST certificate or PAN).',
        example: 'e.g. Ramesh Trading Co. or ABC Enterprises LLP'
      });
    }

    if (!company.proprietor_name?.trim()) {
      missingProfileFields.push({
        key: 'proprietor_name',
        label: 'Proprietor / Authorized Signatory Name',
        requirement: 'Statutory Invoice Signature (GST Rule 46)',
        instruction: 'Enter the full legal name of the owner, director, or authorized person who signs commercial invoices.',
        example: 'e.g. Rajesh Sharma'
      });
    }

    if (!company.proprietor_phone?.trim() && !company.phone?.trim()) {
      missingProfileFields.push({
        key: 'proprietor_phone',
        label: 'Contact Phone Number',
        requirement: 'Invoice Header Communication',
        instruction: 'Enter a valid primary mobile or business phone number for buyer inquiries and delivery dispatches.',
        example: 'e.g. +91 98765 43210'
      });
    }

    if (!company.address?.trim()) {
      missingProfileFields.push({
        key: 'address',
        label: 'Registered Business Address',
        requirement: 'Place of Dispatch / Seller Address',
        instruction: 'Enter the registered office or warehouse address from where goods/services are supplied.',
        example: 'e.g. Shop 14, Main Market, Sector 18, Noida, UP - 201301'
      });
    }

    if (!company.state_code?.trim()) {
      missingProfileFields.push({
        key: 'state_code',
        label: 'State & State Code',
        requirement: 'GST Place of Supply (Tax Determination)',
        instruction: 'Select your state or union territory so Vouch can automatically calculate Intra-State (CGST+SGST) vs Inter-State (IGST) tax.',
        example: 'e.g. 07 - Delhi or 09 - Uttar Pradesh'
      });
    }
  } else {
    // If no company record loaded
    return (
      <DashboardLayout>
        <div className="max-w-2xl mx-auto mt-20 p-8 bg-card border border-border/60 rounded-2xl shadow-xl text-center space-y-4">
          <div className="w-12 h-12 rounded-xl bg-amber-500/15 text-amber-500 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-foreground">No Company Profile Found</h2>
          <p className="text-sm text-muted-foreground">
            Please create or select an active company profile before creating sales invoices.
          </p>
          <Link
            href="/settings"
            className="inline-flex items-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 px-6 py-2.5 rounded-xl font-bold text-sm shadow transition-colors"
          >
            <span>Go to Profile Settings</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </DashboardLayout>
    );
  }

  if (missingProfileFields.length > 0) {
    return (
      <DashboardLayout>
        <div className="max-w-3xl mx-auto my-12 p-6 sm:p-8 bg-card border border-border/60 rounded-2xl shadow-xl space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/15 text-amber-500 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h2 className="text-xl sm:text-2xl font-bold text-foreground">
                Complete Your Firm Profile to Generate Sales Invoices
              </h2>
              <p className="text-sm text-muted-foreground">
                Under statutory invoicing standards (GST Rule 46), tax invoices require seller details.
                Please complete the following missing detail{missingProfileFields.length > 1 ? 's' : ''} in your profile:
              </p>
            </div>
          </div>

          {/* Missing fields itemized list */}
          <div className="space-y-3">
            {missingProfileFields.map((field, idx) => (
              <div 
                key={field.key} 
                className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/5 flex flex-col sm:flex-row sm:items-start justify-between gap-3"
              >
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-bold flex items-center justify-center font-mono">
                      {idx + 1}
                    </span>
                    <span className="font-semibold text-foreground text-sm">{field.label}</span>
                    <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400">
                      Required
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-7">
                    {field.instruction}
                  </p>
                  {field.example && (
                    <div className="text-[11px] text-muted-foreground/80 font-mono pl-7">
                      Format: <span className="text-foreground/90">{field.example}</span>
                    </div>
                  )}
                </div>
                <div className="sm:text-right pl-7 sm:pl-0 shrink-0">
                  <span className="text-[11px] font-medium text-amber-600 dark:text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-md">
                    {field.requirement}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Digital Signature clarification callout */}
          <div className="bg-muted/40 border border-border/40 rounded-xl p-4 flex items-start gap-3">
            <div className="w-6 h-6 rounded-full bg-emerald-500/15 text-emerald-500 flex items-center justify-center shrink-0 mt-0.5">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div className="text-xs space-y-1">
              <div className="font-semibold text-foreground">
                Digital Signature is strictly optional
              </div>
              <p className="text-muted-foreground leading-relaxed">
                You do <strong>not</strong> need a digital signature image to create or post sales bills.
                Tax invoices can be physically signed or stamped after printing. If you want your signature to automatically print on invoice PDFs, you can optionally upload a signature image anytime in Settings.
              </p>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-border/40">
            <Link
              href="/sales"
              className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors order-2 sm:order-1"
            >
              ← Back to Sales Vouchers
            </Link>
            <Link
              href="/settings"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 px-6 py-2.5 rounded-xl font-bold text-sm shadow-md shadow-primary/20 transition-colors order-1 sm:order-2"
            >
              <span>Go to Profile Settings & Complete Details</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // Helper to render Autocomplete dropdown (shared between mobile cards & desktop table)
  const renderProductAutocomplete = (gIndex: number, iIndex: number, item: any, group: any, isMobile: boolean = false) => {
    const query = String(item.product_name || '').trim().toLowerCase();
    const queryAlpha = query.replace(/[\s\-_/.]/g, '');
    const filteredProds = products.filter((p: any) => {
      if (group.category_id && p.category_id !== group.category_id) return false;
      if (!query) return true;
      const pName = (p.name || '').toLowerCase();
      const pAlpha = pName.replace(/[\s\-_/.]/g, '');
      const pBrand = (p.brand || '').toLowerCase();
      const pAlias = (p.alias || '').toLowerCase();
      const pSku = (p.sku || '').toLowerCase();
      const pDesc = (p.description || '').toLowerCase();
      return (
        pName.includes(query) ||
        pAlpha.includes(queryAlpha) ||
        pBrand.includes(query) ||
        pAlias.includes(query) ||
        pSku.includes(query) ||
        pDesc.includes(query)
      );
    });

    const sizeMatch = queryAlpha.match(/([a-z]{0,3}\d{2,5}[a-z]{0,2})/);
    const coreSizeToken = sizeMatch ? sizeMatch[0] : (queryAlpha.length >= 2 ? queryAlpha : '');
    const crossBrandEquivalents = coreSizeToken.length >= 2 ? products.filter((p: any) => {
      const pAlpha = (p.name || '').toLowerCase().replace(/[\s\-_/.]/g, '');
      const aAlpha = (p.alias || '').toLowerCase().replace(/[\s\-_/.]/g, '');
      const dAlpha = (p.description || '').toLowerCase().replace(/[\s\-_/.]/g, '');
      return pAlpha.includes(coreSizeToken) || aAlpha.includes(coreSizeToken) || dAlpha.includes(coreSizeToken);
    }) : [];

    return (
      <div 
        className={`absolute top-full mt-1.5 z-50 bg-card border border-border rounded-xl shadow-2xl overflow-hidden max-h-80 sm:max-h-96 overflow-y-auto ${
          isMobile 
            ? 'left-0 right-0 w-full max-w-full' 
            : 'left-0 w-full min-w-full sm:min-w-[420px] max-w-[calc(100vw-2rem)] sm:max-w-[620px]'
        }`}
        onMouseDown={(e) => e.preventDefault()}
      >
        {filteredProds.length === 0 && crossBrandEquivalents.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground italic">
            No catalog product found. Enter details manually.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {/* Cross-Brand Equivalents Bar */}
            {crossBrandEquivalents.length > 1 && (
              <div className="bg-gradient-to-r from-blue-50/90 via-indigo-50/80 to-blue-50/90 dark:from-blue-950/60 dark:via-indigo-950/40 dark:to-blue-950/60 border-b border-blue-100 dark:border-blue-800/40 p-2.5 sm:p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-blue-800 dark:text-blue-300">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin-slow text-blue-600 dark:text-blue-400" />
                    <span className="truncate">Cross-Brand ({crossBrandEquivalents.length} in &quot;{coreSizeToken.toUpperCase()}&quot;)</span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveSearch(null);
                      setBrandSearchQuery('');
                      setBrandModalTarget({ gIndex, iIndex });
                    }}
                    className="text-[11px] font-bold text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-600/50 dark:hover:bg-blue-600/70 dark:text-blue-100 border border-blue-600 dark:border-blue-500/40 px-2 py-0.5 sm:px-2.5 sm:py-1 rounded-lg cursor-pointer transition-colors flex items-center gap-1 shadow-xs shrink-0"
                    title="Open unified brand selector modal"
                  >
                    <Tag className="w-3 h-3" />
                    <span>View All Brands</span>
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {crossBrandEquivalents.map((altProd: any) => {
                    const altStock = Number(altProd.stock_quantity ?? 0);
                    const isAltStocked = altStock > 0;
                    const altMrp = parseFloat(altProd.selling_price) || 0;
                    const altPast = resolvePartyRateForBrand(partyRates, altProd.id, altProd.name, altProd.brand);
                    return (
                      <button
                        key={altProd.id}
                        type="button"
                        onClick={() => {
                          selectProduct(gIndex, iIndex, altProd);
                          setActiveSearch(null);
                        }}
                        className={`p-2 sm:p-2.5 rounded-xl border text-left text-xs transition-all cursor-pointer flex flex-col justify-between gap-1.5 ${
                          isAltStocked 
                            ? 'bg-card hover:bg-emerald-50/60 dark:bg-emerald-950/20 dark:hover:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/50 shadow-2xs' 
                            : 'bg-muted/30 hover:bg-muted/60 border-border/80 opacity-80'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-bold text-xs text-blue-700 dark:text-blue-400">
                              {altProd.brand || 'Unbranded'}
                            </div>
                            <div className="text-[11px] font-mono text-foreground truncate font-semibold">
                              {altProd.name}
                            </div>
                          </div>
                          <span className={`text-[10px] font-bold px-1.5 sm:px-2 py-0.5 rounded-full shrink-0 ${
                            isAltStocked
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30'
                              : 'bg-muted text-muted-foreground border border-border'
                          }`}>
                            {isAltStocked ? `${altStock} in Stock` : 'Out of stock'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] pt-1 border-t border-border/40">
                          {altPast && Number(altPast.rate) > 0 ? (
                            <div className="text-blue-700 dark:text-blue-400 font-bold">
                              Last: ₹{Number(altPast.rate).toFixed(2)}
                            </div>
                          ) : altMrp > 0 ? (
                            <div className="text-foreground/80 font-medium">
                              MRP: ₹{altMrp.toFixed(2)}
                            </div>
                          ) : (
                            <span className="text-muted-foreground italic text-[10px]">No price set</span>
                          )}
                          {Number(altProd.purchase_price) > 0 && (
                            <span className="text-[10px] text-muted-foreground">
                              Cost: ₹{Number(altProd.purchase_price).toFixed(2)}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="bg-muted/40 px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex justify-between border-b border-border">
              <span>Matching Catalog SKUs</span>
              <span>{filteredProds.length} result{filteredProds.length > 1 ? 's' : ''}</span>
            </div>
            {filteredProds.map((p: any) => {
              const mrp = parseFloat(p.selling_price) || 0;
              const stock = Number(p.stock_quantity ?? 0);
              const isSelected = item.product_id === p.id;
              const pPast = resolvePartyRateForBrand(partyRates, p.id, p.name, p.brand);
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    selectProduct(gIndex, iIndex, p);
                    setActiveSearch(null);
                  }}
                  className={`w-full text-left p-2.5 sm:p-3 hover:bg-muted/60 flex items-center justify-between gap-3 cursor-pointer transition-colors border-b border-border/60 last:border-b-0 ${
                    isSelected ? 'bg-blue-50/80 dark:bg-blue-600/15 border-l-4 border-l-blue-600 dark:border-l-blue-500' : ''
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                      <span className="font-semibold text-foreground text-sm truncate">{p.name}</span>
                      {p.brand ? (
                        <span className="text-[10px] px-1.5 sm:px-2 py-0.5 rounded-md font-bold uppercase bg-blue-100 text-blue-800 border border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30">
                          {p.brand}
                        </span>
                      ) : (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md font-medium text-muted-foreground bg-muted border border-border">
                          Unbranded
                        </span>
                      )}
                      {pPast && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-md font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/40">
                          Party: ₹{Number(pPast.rate).toFixed(2)}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {p.category} {p.sku ? `• SKU: ${p.sku}` : ''} {p.description ? `• ${p.description}` : ''}
                    </div>
                  </div>
                  <div className="text-right whitespace-nowrap pl-2">
                    <div className="text-xs font-mono font-bold text-foreground">
                      {mrp > 0 ? `MRP: ₹${mrp.toFixed(2)}` : 'No MRP'}
                    </div>
                    {pPast && (
                      <div className="text-[11px] font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        Party: ₹{Number(pPast.rate).toFixed(2)}
                      </div>
                    )}
                    <div className={`text-[10px] font-mono font-medium ${stock > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                      Avail: {stock} {p.unit || 'PCS'}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // Helper to render HUD badges & pill buttons for an item
  const renderItemBadges = (gIndex: number, iIndex: number, item: any, group: any) => {
    if (!item.product_name) return null;

    const cleanName = String(item.product_name || '').trim().toLowerCase();
    const alphaVal = cleanName.replace(/[\s\-_/.]/g, '');
    const matched = products.find((p: any) => 
      (item.product_id && p.id === item.product_id) || 
      (p.name.toLowerCase() === cleanName && 
       (!item.brand || (p.brand || '').toLowerCase() === item.brand.toLowerCase()))
    );
    const sameNameProducts = products.filter((p: any) => 
      (!group.category_id || p.category_id === group.category_id) &&
      (p.name.toLowerCase() === cleanName || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
    );

    // Strict brand-specific party rate
    const pastInfo = resolvePartyRateForBrand(
      partyRates, 
      item.product_id || matched?.id, 
      item.product_name, 
      item.brand || matched?.brand
    );
    
    const pastRate = item.last_party_rate ?? (pastInfo ? Number(pastInfo.rate) : null);
    const purchaseCost = Number(
      (matched?.purchase_price && parseFloat(matched.purchase_price) > 0)
        ? matched.purchase_price
        : (item.purchase_cost || pastInfo?.purchase_cost || 0)
    );
    const catalogMrp = parseFloat(matched?.selling_price || item.mrp || 0);
    const currentRate = Number(item.rate || 0);
    
    const vNum = item.last_party_vnum || pastInfo?.voucher_number;
    const vDate = item.last_party_date || pastInfo?.voucher_date;
    const partyName = ledgers.find(l => l.id === partyLedgerId)?.name || 'Customer';

    const isBelowCost = currentRate > 0 && purchaseCost > 0 && currentRate < purchaseCost;
    const marginPercent = currentRate > 0 && purchaseCost > 0 
      ? ((currentRate - purchaseCost) / currentRate) * 100 
      : null;
    const availStock = Number(matched?.stock_quantity ?? item.stock_quantity ?? 0);

    return (
      <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
        {/* 1. Unified Brand Pill Button */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setBrandSearchQuery('');
            setBrandModalTarget({ gIndex, iIndex });
          }}
          className={`text-[10px] px-2.5 py-1 rounded-lg border font-semibold flex items-center gap-1.5 cursor-pointer transition-all ${
            item.brand
              ? 'bg-blue-50 hover:bg-blue-100/80 text-blue-800 border-blue-200 dark:bg-blue-500/15 dark:hover:bg-blue-500/25 dark:text-blue-300 dark:border-blue-500/40 shadow-2xs'
              : 'bg-amber-50 hover:bg-amber-100/80 text-amber-900 border-amber-200 dark:bg-amber-500/10 dark:hover:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30'
          }`}
          title="Click to select or switch brand variant"
        >
          <Tag className="w-3 h-3 text-blue-600 dark:text-blue-400" />
          <span>Brand: <strong className="text-foreground">{item.brand || 'Select Brand'}</strong></span>
          {sameNameProducts.length > 1 && (
            <span className="text-[9px] bg-blue-600 text-white rounded-full px-1.5 font-mono font-bold">
              {sameNameProducts.length}
            </span>
          )}
          <ChevronDown className="w-3 h-3 text-blue-600 dark:text-blue-400" />
        </button>

        {/* 2. Stock Pill */}
        {matched && (
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border font-medium flex items-center gap-1 ${
            availStock > 0 
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/30' 
              : 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-500/15 dark:text-rose-400 dark:border-rose-500/30'
          }`}>
            <span>● Stock:</span>
            <strong>{availStock} {matched.unit || 'PCS'}</strong>
          </span>
        )}

        {/* 3. Brand-Specific Last Billed HUD Card */}
        {pastRate && pastRate > 0 ? (
          <div 
            className="text-[10px] font-mono inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-900 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-500/30 px-2 py-0.5 rounded-md shadow-2xs"
            title={`Last billed to ${partyName} on ${vDate || 'past invoice'} @ ₹${pastRate.toFixed(2)}${vNum ? ` (${vNum})` : ''}`}
          >
            <span className="text-emerald-700 dark:text-emerald-400 font-sans font-semibold">Last Sold{item.brand ? ` (${item.brand})` : ''}:</span>
            <strong className="text-emerald-950 dark:text-emerald-200 font-bold">₹{pastRate.toFixed(2)}</strong>
            {vDate && <span className="text-emerald-600 dark:text-emerald-400/70 text-[9px]">({vDate})</span>}
            {Number(item.rate) !== pastRate && (
              <button
                type="button"
                onClick={() => updateItem(gIndex, iIndex, 'rate', pastRate)}
                className="text-[9px] bg-emerald-600 hover:bg-emerald-700 text-white dark:bg-emerald-500/25 dark:hover:bg-emerald-500/40 dark:text-emerald-100 px-1.5 py-0.5 rounded font-sans cursor-pointer transition-colors shadow-xs"
                title="Apply party's last billed rate"
              >
                Apply
              </button>
            )}
          </div>
        ) : (
          partyLedgerId && (
            <span className="text-[10px] font-sans text-muted-foreground/80 bg-muted/40 px-2 py-0.5 rounded border border-border/60">
              No prior bill{item.brand ? ` (${item.brand})` : ''}
            </span>
          )
        )}

        {/* 4. Purchase Cost HUD Card */}
        {purchaseCost > 0 && (
          <div 
            className="text-[10px] font-mono inline-flex items-center gap-1.5 bg-slate-100 text-slate-800 border border-slate-200 dark:bg-slate-800/70 dark:text-slate-300 dark:border-slate-700 px-2 py-0.5 rounded-md"
            title={`Latest purchase cost: ₹${purchaseCost.toFixed(2)}. Click '+25%' to apply standard 25% wholesale margin.`}
          >
            <span className="text-slate-600 dark:text-slate-400 font-sans font-semibold">Cost:</span>
            <strong className="text-slate-900 dark:text-slate-200 font-bold">₹{purchaseCost.toFixed(2)}</strong>
            <button
              type="button"
              onClick={() => updateItem(gIndex, iIndex, 'rate', Math.round(purchaseCost * 1.25 * 100) / 100)}
              className="text-[9px] bg-blue-600 hover:bg-blue-700 text-white dark:bg-blue-500/20 dark:hover:bg-blue-500/30 dark:text-blue-300 px-1.5 py-0.5 rounded font-sans cursor-pointer transition-colors shadow-xs font-semibold"
              title="Set rate to Cost + 25% margin"
            >
              +25%
            </button>
          </div>
        )}

        {/* 5. Live Margin / Loss Badge */}
        {currentRate > 0 && purchaseCost > 0 && (
          <div 
            className={`text-[10px] font-mono inline-flex items-center gap-1 px-2 py-0.5 rounded-md border font-semibold ${
              isBelowCost 
                ? 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/50' 
                : marginPercent! >= 20
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                : 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30'
            }`}
            title={isBelowCost ? `⚠️ Selling below cost (-₹${(purchaseCost - currentRate).toFixed(2)} loss/unit)!` : `Current gross margin on this line: ${marginPercent!.toFixed(1)}%`}
          >
            <span className="font-sans">
              {isBelowCost ? '⚠️ Loss:' : 'Margin:'}
            </span>
            <span>{marginPercent!.toFixed(1)}%</span>
          </div>
        )}

        {/* 6. Master MRP (Catalog price) */}
        {catalogMrp > 0 && Number(item.rate) !== catalogMrp && (
          <button
            type="button"
            onClick={() => updateItem(gIndex, iIndex, 'rate', catalogMrp)}
            className="text-[10px] font-mono inline-flex items-center gap-1 bg-slate-100 hover:bg-slate-200 text-slate-700 hover:text-slate-900 border border-slate-200 dark:bg-muted/60 dark:hover:bg-muted dark:text-muted-foreground dark:hover:text-foreground dark:border-border px-1.5 py-0.5 rounded cursor-pointer transition-colors"
            title="Click to apply catalog MRP"
          >
            <span>MRP: ₹{catalogMrp.toFixed(2)} [Use]</span>
          </button>
        )}
      </div>
    );
  };

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto space-y-6 pb-20">
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div className="flex items-center gap-3 sm:gap-4">
            <Link href="/sales" className="text-muted-foreground hover:text-foreground transition-colors p-1">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">New Sales Invoice</h1>
              {isMounted && activeFY && (
                <div className="text-xs text-muted-foreground mt-0.5">
                  Financial Year: <span className="font-semibold text-foreground">{activeFY.name}</span> ({activeFY.start_date} ~ {activeFY.end_date})
                </div>
              )}
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || isReadOnly}
            className={`w-full sm:w-auto justify-center px-6 py-2.5 rounded-lg shadow-lg font-medium transition-colors flex items-center gap-2 cursor-pointer ${
              isReadOnly
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30 cursor-not-allowed opacity-80'
                : 'bg-blue-600 hover:bg-blue-700 text-foreground disabled:opacity-50'
            }`}
          >
            {saving ? 'Posting...' : isReadOnly ? 'Period Closed (Read-Only)' : 'Post Invoice'}
          </button>
        </div>
        
        {/* Billing Details Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <h2 className="text-lg font-semibold text-foreground">Billing Details</h2>
            {isMounted && seqPreview && (
              <span className={`text-xs font-mono font-bold px-2.5 py-1 rounded-lg border flex items-center gap-1.5 w-fit ${
                enableManualInvoice 
                  ? 'bg-amber-500/15 text-amber-500 border-amber-500/30' 
                  : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
              }`}>
                <span>{enableManualInvoice ? 'Manual Sequence Override' : `Next Serial: ${seqPreview}`}</span>
                <span className="text-[10px] font-sans font-normal opacity-80">(GST Rule 46b)</span>
              </span>
            )}
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6 pb-6 border-b border-border">
            {/* Invoice Numbering (Auto vs Manual like Tally) */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Hash className="w-4 h-4 text-primary" />
                  <span>Invoice Number</span>
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${
                    enableManualInvoice 
                      ? 'bg-amber-500/15 text-amber-500 border-amber-500/30' 
                      : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                  }`}>
                    {enableManualInvoice ? 'MANUAL' : 'AUTO'}
                  </span>
                </label>

                {/* Tally-style Toggle Switch */}
                <div className="inline-flex items-center bg-muted/60 p-0.5 rounded-lg border border-border/50 text-xs shadow-xs">
                  <button
                    type="button"
                    onClick={() => handleToggleManualInvoice(false)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${
                      !enableManualInvoice
                        ? 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                    title="Switch to Auto-sequencing (Tally Default)"
                  >
                    Auto
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleManualInvoice(true)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer ${
                      enableManualInvoice
                        ? 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                    title="Switch to Manual custom invoice numbering"
                  >
                    Manual
                  </button>
                </div>
              </div>

              {enableManualInvoice ? (
                <div className="space-y-1">
                  <input
                    type="text"
                    value={invoiceNumber}
                    onChange={e => setInvoiceNumber(e.target.value)}
                    placeholder={seqPreview || "e.g. INV-001"}
                    className="w-full bg-muted/50 border border-amber-500/50 text-foreground p-3 rounded-lg focus:ring-2 focus:ring-primary outline-none transition-all font-mono font-semibold"
                    autoFocus
                  />
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>Manual custom numbering active.</span>
                    <button
                      type="button"
                      onClick={() => handleToggleManualInvoice(false)}
                      className="text-primary hover:underline font-medium cursor-pointer"
                    >
                      Revert to Auto
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="w-full bg-muted/30 border border-border/60 text-foreground p-3 rounded-lg flex items-center justify-between font-mono">
                    <span className="font-semibold text-foreground">
                      {seqPreview ? seqPreview : "Auto-Generated upon Post"}
                    </span>
                    <span className="text-[11px] text-muted-foreground font-sans">
                      (Sequential)
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>Sequential number generated on posting.</span>
                    <button
                      type="button"
                      onClick={() => handleToggleManualInvoice(true)}
                      className="text-primary hover:underline font-medium cursor-pointer"
                    >
                      Override with Manual #
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Invoice Date */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium text-muted-foreground">
                  Invoice Date {isMounted && activeFY && <span className="text-muted-foreground font-normal font-mono">({activeFY.code})</span>}
                </label>
                {isMounted && activeFY && (
                  <span className="text-[11px] text-muted-foreground font-mono">
                    FY: {activeFY.start_date} ~ {activeFY.end_date}
                  </span>
                )}
              </div>
              <input
                type="date"
                value={invoiceDate}
                min={activeFY?.start_date}
                max={activeFY?.end_date}
                onChange={e => setInvoiceDate(e.target.value)}
                className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-primary outline-none transition-all font-mono"
              />
              <p className="text-[11px] text-muted-foreground mt-1">
                Voucher accounting date within selected financial period.
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-sm font-medium text-muted-foreground">Party (Customer)</label>
                <Link href="/sales/customers/new" className="text-xs text-blue-500 hover:text-blue-400">+ Add New Customer</Link>
              </div>
              <select
                value={partyLedgerId}
                onChange={e => handlePartyChange(e.target.value)}
                className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              >
                <option value="">-- Select Customer / Cash / Bank --</option>
                {ledgers.filter(l => 
                  l.group?.includes('Debtor') || 
                  l.group?.includes('Cash') || 
                  l.group?.includes('Bank') || 
                  l.ledger_type === 'CUSTOMER' || 
                  l.ledger_type === 'CASH' || 
                  l.ledger_type === 'BANK' ||
                  l.name?.toLowerCase().includes('cash')
                ).map(l => (
                  <option key={l.id} value={l.id}>
                    {l.name} {l.group ? `[${l.group}]` : ''} {Number(l.discount_percent || 0) > 0 ? `(${Number(l.discount_percent)}% Disc)` : ''}
                  </option>
                ))}
              </select>
              {selectedParty && Number(selectedParty.discount_percent || 0) > 0 && (
                <div className="mt-2 text-xs flex items-center justify-between text-blue-300 bg-blue-500/10 border border-blue-500/20 px-3 py-1.5 rounded-lg">
                  <div className="flex items-center gap-1.5 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse"></span>
                    <span>Customer Discount: <strong className="text-foreground font-mono">{Number(selectedParty.discount_percent)}%</strong></span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">Applied automatically • Editable below</span>
                </div>
              )}
              {selectedParty && Number(selectedParty.credit_limit || 0) > 0 && (Number(selectedParty.current_balance || 0) + grandTotal) > Number(selectedParty.credit_limit) && (
                <div className="mt-2 text-xs flex items-center justify-between text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 px-3 py-2 rounded-lg">
                  <div className="flex items-center gap-1.5 font-medium">
                    <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                    <span>
                      ⚠️ Credit Limit of ₹{Number(selectedParty.credit_limit).toLocaleString("en-IN")} exceeded by ₹{((Number(selectedParty.current_balance || 0) + grandTotal) - Number(selectedParty.credit_limit)).toLocaleString("en-IN")}.
                    </span>
                  </div>
                  <span className="text-[10px] text-amber-600 dark:text-amber-400 font-bold uppercase tracking-wider">Invoicing Permitted</span>
                </div>
              )}
            </div>
            {enableLedgerMapping && (
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1.5">Sales Ledger</label>
                <select value={salesLedgerId} onChange={e => setSalesLedgerId(e.target.value)} className="w-full bg-muted/50 border border-input text-foreground p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                  <option value="">-- Select Sales Ledger --</option>
                  {ledgers.filter(l => l.group.includes('Income') || l.name.includes('Sales')).map(l => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Line Items Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 sm:p-6 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-foreground">Line Items by Category</h2>
                    <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 dark:text-blue-300 dark:bg-blue-400/10 dark:border-blue-400/20 px-2 py-0.5 rounded font-medium">Auto-Creates & Inherits Tax</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">Rapid billing for retail and wholesale</p>
                </div>
                
                {/* Header Controls: Brand Toggle & Barcode Scanner */}
                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    type="button"
                    onClick={() => {
                      const next = !showBrandInInvoice;
                      setShowBrandInInvoice(next);
                      if (typeof window !== 'undefined') {
                        localStorage.setItem('vouch_show_brand_in_sales_invoice', String(next));
                      }
                      toast.info(next ? 'Brand will be shown on printed invoice & receipts' : 'Brand hidden on printed invoice & receipts');
                    }}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition-all ${
                      showBrandInInvoice
                        ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 dark:bg-blue-600/15 dark:text-blue-400 dark:border-blue-500/40 shadow-2xs'
                        : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
                    }`}
                    title="Toggle whether Brand names are printed under product names on invoices & receipts"
                  >
                    <Tag className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                    <span>Brand on Bill: <strong className={showBrandInInvoice ? 'text-blue-900 dark:text-blue-300 font-bold' : 'text-muted-foreground'}>{showBrandInInvoice ? 'YES' : 'NO'}</strong></span>
                  </button>

                  {/* Barcode Quick-Scan Input (P1-5) */}
                  <div className="flex items-center gap-2 w-full sm:w-72">
                    <div className="relative w-full">
                      <ScanBarcode className="w-4 h-4 text-primary absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                      <input
                        ref={barcodeInputRef}
                        type="text"
                        value={barcodeInput}
                        onChange={(e) => setBarcodeInput(e.target.value)}
                        onKeyDown={handleBarcodeScan}
                        placeholder="Scan Barcode / SKU (Press Enter)..."
                        className="w-full pl-9 pr-3 py-1.5 bg-muted/60 border border-input rounded-lg text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:bg-background transition-all font-mono"
                      />
                    </div>
                  </div>
                </div>
            </div>
            
            <div className="p-2 sm:p-4 space-y-6">
                {groupedItems.map((group, gIndex) => (
                    <div key={gIndex} className="border border-border rounded-xl bg-card shadow-sm overflow-hidden">
                        <div className="p-3 sm:p-4 bg-muted/40 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="flex-1 max-w-md flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                                <label className="text-sm font-medium text-muted-foreground whitespace-nowrap">Category:</label>
                                <select 
                                    value={group.category_id} 
                                    onChange={(e) => updateGroup(gIndex, 'category_id', e.target.value)}
                                    className="w-full bg-muted border border-input text-foreground p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                                >
                                    <option value="">-- Select Category --</option>
                                    {categories.map(c => (
                                         <option key={c.id} value={c.id}>{c.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2 sm:gap-4 text-sm text-muted-foreground">
                                <span className="text-xs sm:text-sm">Default HSN: <strong className="text-foreground/80">{group.hsn_code || 'N/A'}</strong></span>
                                {isInterState ? (
                                    <span className="bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 px-2 py-0.5 rounded border border-blue-200 dark:border-blue-500/20 text-xs font-semibold">
                                        IGST: {group.gst_rate}%
                                    </span>
                                ) : (
                                    <div className="flex gap-2">
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">CGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">SGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                    </div>
                                )}
                                <button onClick={() => removeCategoryGroup(gIndex)} className="text-red-500 hover:text-red-400 p-1.5 rounded-lg hover:bg-red-500/10 cursor-pointer ml-auto sm:ml-4 transition-colors" title="Delete category group">
                                    <Trash2 className="w-4.5 h-4.5" />
                                </button>
                            </div>
                        </div>
                        
                        {/* 1. Mobile Item Cards (sm:hidden) */}
                        <div className="sm:hidden divide-y divide-border/60">
                            {group.items.map((item: any, iIndex: number) => {
                                const gross = Number(item.quantity) * Number(item.rate);
                                const discount = gross * (Number(item.discount_percent)/100);
                                const taxable = gross - discount;
                                const cost = Number(item.purchase_cost || 0);
                                const rate = Number(item.rate || 0);
                                const isBelowCost = cost > 0 && rate > 0 && rate < cost;
                                const cleanName = String(item.product_name || '').trim().toLowerCase();
                                const matched = products.find((p: any) => 
                                    (item.product_id && p.id === item.product_id) || 
                                    p.name.toLowerCase() === cleanName
                                );

                                return (
                                    <div 
                                        key={iIndex} 
                                        className={`p-3 space-y-2.5 transition-colors ${
                                            activeRow?.gIndex === gIndex && activeRow?.iIndex === iIndex 
                                                ? 'bg-muted/40' 
                                                : 'bg-card'
                                        }`}
                                        onClick={() => setActiveRow({ gIndex, iIndex })}
                                    >
                                        {/* Card Header: Item # and Delete + Line Taxable */}
                                        <div className="flex items-center justify-between gap-2 pb-1.5 border-b border-border/40">
                                            <div className="flex items-center gap-2 min-w-0">
                                                <span className="text-xs font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-md font-mono shrink-0">
                                                    #{iIndex + 1}
                                                </span>
                                                {item.product_name ? (
                                                    <span className="text-xs font-semibold text-foreground truncate">
                                                        {item.product_name}
                                                    </span>
                                                ) : (
                                                    <span className="text-xs text-muted-foreground italic">
                                                        New Item
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <div className="text-right">
                                                    <span className="text-[10px] text-muted-foreground uppercase tracking-wider block font-medium leading-none mb-0.5">Taxable</span>
                                                    <span className="text-sm font-bold font-mono text-foreground tabular-nums leading-none">
                                                        ₹{taxable.toFixed(2)}
                                                    </span>
                                                </div>
                                                <button 
                                                    type="button"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        removeRow(gIndex, iIndex);
                                                    }} 
                                                    className="text-muted-foreground hover:text-destructive active:scale-95 transition-all p-1.5 rounded-lg hover:bg-destructive/10 min-w-[32px] min-h-[32px] flex items-center justify-center cursor-pointer ml-1" 
                                                    title="Remove line item"
                                                >
                                                    <Trash2 className="w-4 h-4 text-red-500/80" />
                                                </button>
                                            </div>
                                        </div>

                                        {/* Product Name Search */}
                                        <div className="relative">
                                            <div className="relative">
                                                <input 
                                                    type="text" 
                                                    placeholder="e.g. Item Name, Size, or Brand" 
                                                    value={item.product_name} 
                                                    onChange={e => {
                                                        updateItem(gIndex, iIndex, 'product_name', e.target.value);
                                                        setActiveSearch(`${gIndex}-${iIndex}`);
                                                    }} 
                                                    onFocus={() => {
                                                        setActiveSearch(`${gIndex}-${iIndex}`);
                                                        setActiveRow({ gIndex, iIndex });
                                                    }} 
                                                    onBlur={() => setTimeout(() => setActiveSearch(null), 250)}
                                                    className="w-full min-h-[38px] bg-background border border-border/80 hover:border-input focus:border-primary focus:bg-background rounded-lg px-3 py-2 outline-none text-foreground transition-all text-sm font-medium" 
                                                />
                                            </div>
                                            {activeSearch === `${gIndex}-${iIndex}` && renderProductAutocomplete(gIndex, iIndex, item, group, true)}
                                        </div>

                                        {/* Product Badges (Brand, Stock, Last Sold, Cost, Margin, MRP) */}
                                        {renderItemBadges(gIndex, iIndex, item, group)}

                                        {/* Numerical Inputs Grid: Qty, Rate, Disc% */}
                                        <div className="grid grid-cols-3 gap-2 pt-1">
                                            <div>
                                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                                                    Qty
                                                </label>
                                                <input 
                                                    type="number" 
                                                    step="1"
                                                    min="1" 
                                                    value={item.quantity} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'quantity', e.target.value)} 
                                                    onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                    className="w-full min-h-[38px] bg-background border border-border/80 hover:border-input focus:border-primary focus:bg-background rounded-lg px-2.5 py-1.5 outline-none text-foreground transition-all text-center text-sm font-mono tabular-nums font-semibold" 
                                                />
                                                {matched && Number(matched.stock_quantity ?? 0) < Number(item.quantity) && (
                                                    <div className="text-[10px] text-amber-500 font-mono tabular-nums text-center font-medium mt-1">
                                                        Avail: {matched.stock_quantity ?? 0}
                                                    </div>
                                                )}
                                            </div>

                                            <div>
                                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                                                    Rate (₹)
                                                </label>
                                                <input 
                                                    type="number" 
                                                    step="0.01" 
                                                    min="0" 
                                                    placeholder="0.00" 
                                                    value={item.rate === 0 && !item.product_name ? '' : item.rate} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'rate', e.target.value)} 
                                                    onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                    className={`w-full min-h-[38px] rounded-lg px-2.5 py-1.5 outline-none transition-all text-right text-sm font-mono tabular-nums font-semibold ${
                                                        isBelowCost 
                                                            ? 'bg-rose-500/10 border-rose-500 text-rose-300 focus:border-rose-400 ring-2 ring-rose-500/30' 
                                                            : 'bg-background border border-border/80 hover:border-input focus:border-primary focus:bg-background text-foreground'
                                                    }`} 
                                                />
                                                {isBelowCost && (
                                                    <div className="text-[10px] text-rose-400 font-mono tabular-nums text-right font-semibold mt-1">
                                                        ⚠️ Below Cost
                                                    </div>
                                                )}
                                            </div>

                                            <div>
                                                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
                                                    Disc %
                                                </label>
                                                <input 
                                                    type="number" 
                                                    step="0.01" 
                                                    min="0" 
                                                    max="100" 
                                                    value={item.discount_percent} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'discount_percent', e.target.value)} 
                                                    onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                    className="w-full min-h-[38px] bg-background border border-border/80 hover:border-input focus:border-primary focus:bg-background rounded-lg px-2.5 py-1.5 outline-none text-foreground transition-all text-center text-sm font-mono tabular-nums font-semibold" 
                                                />
                                                {currentPartyDiscount > 0 && (
                                                    <div className="text-[10px] text-primary font-mono text-center mt-1">
                                                        {currentPartyDiscount}% party
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        {/* 2. Desktop Table (hidden sm:block) */}
                        <div className="hidden sm:block overflow-x-auto">
                            <table className="w-full min-w-[700px] text-left border-collapse">
                                <thead className="bg-muted/60 text-muted-foreground text-xs uppercase tracking-wider">
                                    <tr>
                                        <th className="p-3 font-semibold">
                                            <div className="flex items-center justify-between gap-2">
                                                <span>Product Name</span>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        const next = !showBrandInInvoice;
                                                        setShowBrandInInvoice(next);
                                                        if (typeof window !== 'undefined') {
                                                            localStorage.setItem('vouch_show_brand_in_sales_invoice', String(next));
                                                        }
                                                    }}
                                                    className={`text-[10px] px-2 py-0.5 rounded-md border cursor-pointer inline-flex items-center gap-1 font-mono transition-colors ${
                                                        showBrandInInvoice
                                                            ? 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/40 font-semibold'
                                                            : 'bg-muted text-muted-foreground border-border'
                                                    }`}
                                                    title="Toggle Brand display on printed invoice"
                                                >
                                                    <Tag className="w-2.5 h-2.5 text-blue-600 dark:text-blue-400" />
                                                    <span>Brand: <strong className={showBrandInInvoice ? 'text-blue-800 dark:text-blue-300 font-bold' : ''}>{showBrandInInvoice ? 'ON' : 'OFF'}</strong></span>
                                                </button>
                                            </div>
                                        </th>
                                        <th className="p-3 font-semibold w-24 text-center">Qty</th>
                                        <th className="p-3 font-semibold w-36 text-right">
                                            <span>Sales Rate (₹)</span>
                                            <span className="block text-xs text-muted-foreground lowercase font-normal">
                                                {loadingPartyRates ? 'fetching rates...' : 'party rate or MRP'}
                                            </span>
                                        </th>
                                        <th className="p-3 font-semibold w-28 text-center">
                                            <span>Disc %</span>
                                            {currentPartyDiscount > 0 && (
                                                <span className="block text-xs text-primary lowercase font-normal">({currentPartyDiscount}% party)</span>
                                            )}
                                        </th>
                                        <th className="p-3 font-semibold w-32 text-right">Amount</th>
                                        <th className="p-3 w-12"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border/60">
                                    {group.items.map((item: any, iIndex: number) => {
                                        const gross = Number(item.quantity) * Number(item.rate);
                                        const discount = gross * (Number(item.discount_percent)/100);
                                        const taxable = gross - discount;
                                        
                                        return (
                                        <tr 
                                          key={iIndex} 
                                          className={`transition-colors relative ${
                                            activeSearch === `${gIndex}-${iIndex}` 
                                              ? 'z-40 bg-muted/70' 
                                              : activeRow?.gIndex === gIndex && activeRow?.iIndex === iIndex 
                                              ? 'z-10 bg-muted/60' 
                                              : 'z-0 hover:bg-muted/40'
                                          }`}
                                          onClick={() => setActiveRow({ gIndex, iIndex })}
                                        >
                                            <td className={`p-2 align-top ${activeSearch === `${gIndex}-${iIndex}` ? 'relative z-40' : 'relative z-auto'}`}>
                                                <div className={`relative ${activeSearch === `${gIndex}-${iIndex}` ? 'z-50' : 'z-auto'}`}>
                                                    <input 
                                                        type="text" 
                                                        placeholder="e.g. Item Name, Size, or Brand" 
                                                        value={item.product_name} 
                                                        onChange={e => {
                                                            updateItem(gIndex, iIndex, 'product_name', e.target.value);
                                                            setActiveSearch(`${gIndex}-${iIndex}`);
                                                        }} 
                                                        onFocus={() => {
                                                            setActiveSearch(`${gIndex}-${iIndex}`);
                                                            setActiveRow({ gIndex, iIndex });
                                                        }} 
                                                        onBlur={() => setTimeout(() => setActiveSearch(null), 250)}
                                                        className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-sm font-medium" 
                                                    />

                                                    {/* Autocomplete Dropdown Popover */}
                                                    {activeSearch === `${gIndex}-${iIndex}` && renderProductAutocomplete(gIndex, iIndex, item, group, false)}
                                                </div>

                                                {renderItemBadges(gIndex, iIndex, item, group)}
                                            </td>
                                            <td className="p-2">
                                                <input 
                                                    type="number" 
                                                    step="1"
                                                    min="1" 
                                                    value={item.quantity} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'quantity', e.target.value)} 
                                                    onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                    className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-center text-sm font-mono tabular-nums font-semibold" 
                                                />
                                                {(() => {
                                                    const cleanName = String(item.product_name || '').trim().toLowerCase();
                                                    const matched = products.find((p: any) => 
                                                        (item.product_id && p.id === item.product_id) || 
                                                        p.name.toLowerCase() === cleanName
                                                    );
                                                    if (matched && Number(matched.stock_quantity ?? 0) < Number(item.quantity)) {
                                                        return (
                                                            <div className="text-xs text-amber-500 font-mono tabular-nums text-center font-medium mt-0.5" title={`Available warehouse inventory: ${matched.stock_quantity ?? 0} ${matched.unit || 'PCS'}. Billing into negative stock permitted.`}>
                                                                Avail: {matched.stock_quantity ?? 0}
                                                            </div>
                                                        );
                                                    }
                                                    return null;
                                                })()}
                                            </td>
                                            <td className="p-2">
                                                {(() => {
                                                    const cost = Number(item.purchase_cost || 0);
                                                    const rate = Number(item.rate || 0);
                                                    const isBelowCost = cost > 0 && rate > 0 && rate < cost;
                                                    return (
                                                        <div className="relative">
                                                            <input 
                                                                type="number" 
                                                                step="0.01" 
                                                                min="0" 
                                                                placeholder="0.00" 
                                                                value={item.rate === 0 && !item.product_name ? '' : item.rate} 
                                                                onChange={e => updateItem(gIndex, iIndex, 'rate', e.target.value)} 
                                                                onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                                className={`w-full min-h-[34px] rounded-md px-2.5 py-1.5 outline-none transition-all text-right text-sm font-mono tabular-nums font-semibold ${
                                                                    isBelowCost 
                                                                        ? 'bg-rose-500/10 border-rose-500 text-rose-300 focus:border-rose-400 ring-2 ring-rose-500/30' 
                                                                        : 'bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background text-foreground'
                                                                }`} 
                                                            />
                                                            {isBelowCost && (
                                                                <div 
                                                                    className="text-[10px] text-rose-400 font-mono tabular-nums text-right font-semibold mt-0.5"
                                                                    title={`Selling below purchase cost (₹${cost.toFixed(2)})!`}
                                                                >
                                                                    ⚠️ Below Cost (-₹{(cost - rate).toFixed(2)})
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })()}
                                            </td>
                                            <td className="p-2">
                                                <input 
                                                    type="number" 
                                                    step="0.01" 
                                                    min="0" 
                                                    max="100" 
                                                    value={item.discount_percent} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'discount_percent', e.target.value)} 
                                                    onFocus={() => setActiveRow({ gIndex, iIndex })}
                                                    className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-center text-sm font-mono tabular-nums font-semibold" 
                                                />
                                            </td>
                                            <td className="p-2 text-right font-bold text-foreground font-mono tabular-nums text-sm">
                                                ₹{taxable.toFixed(2)}
                                            </td>
                                            <td className="p-2 text-center">
                                                <button 
                                                    type="button"
                                                    onClick={() => removeRow(gIndex, iIndex)} 
                                                    className="text-muted-foreground hover:text-destructive transition-colors p-1.5 rounded hover:bg-destructive/10 min-w-[32px] min-h-[32px] inline-flex items-center justify-center cursor-pointer" 
                                                    title="Remove line item (Alt + D)"
                                                >
                                                    <Trash2 className="w-4 h-4 text-red-500/80" />
                                                </button>
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                        <div className="p-3 bg-muted/20 border-t border-border/60">
                            <button onClick={() => addRow(gIndex)} className="text-sm text-primary hover:text-primary/80 font-semibold flex items-center gap-1.5 transition-colors cursor-pointer">
                                <Plus className="w-4 h-4" />
                                <span>Add item in {categories.find(c=>c.id===group.category_id)?.name || 'this category'}</span>
                            </button>
                        </div>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t border-border bg-muted/20 flex items-center">
                <button onClick={addCategoryGroup} className="text-sm text-foreground bg-card hover:bg-accent border border-border hover:border-input px-4 py-2.5 rounded-xl shadow-xs transition-colors font-semibold flex items-center justify-center gap-2 cursor-pointer w-full sm:w-auto">
                    <Plus className="w-4 h-4 text-primary" />
                    <span>Add Another Category Block</span>
                </button>
            </div>
        </div>

        {/* ========================================================= */}
        {/* Progressive Disclosure: Additional & Statutory Invoicing */}
        {/* ========================================================= */}
        <div className="bg-card border border-border/80 rounded-xl shadow-xs overflow-hidden">
          <div className="p-4 bg-muted/30 border-b border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                <Sliders className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground">Advanced Invoicing Options</h3>
                <p className="text-xs text-muted-foreground">Click to add transport, bank QR, notes, or walk-in info</p>
              </div>
            </div>
            <div className="text-xs text-muted-foreground font-medium">
              Optional statutory & commercial fields
            </div>
          </div>

          <div className="divide-y divide-border/50">
            
            {/* Accordion 1: Walk-in / Cash Counter Buyer Details */}
            <div className="transition-colors">
              <button
                type="button"
                onClick={() => setActiveAccordion(activeAccordion === 'buyer' ? null : 'buyer')}
                className="w-full p-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <User className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <span>Walk-in Buyer Details</span>
                      {buyerName && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                          ✓ {buyerName}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">Print buyer name & phone on bill without creating a ledger</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium hidden sm:inline">
                    {activeAccordion === 'buyer' ? 'Collapse' : 'Expand'}
                  </span>
                  {activeAccordion === 'buyer' ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </div>
              </button>

              {activeAccordion === 'buyer' && (
                <div className="p-4 bg-muted/15 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-in fade-in-50 duration-150">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Buyer Name</label>
                    <input
                      type="text"
                      value={buyerName}
                      onChange={e => setBuyerName(e.target.value)}
                      placeholder="e.g. Ramesh Kumar"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Mobile / Phone</label>
                    <input
                      type="text"
                      value={buyerPhone}
                      onChange={e => setBuyerPhone(e.target.value)}
                      placeholder="e.g. 9876543210"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">GSTIN (Optional)</label>
                    <input
                      type="text"
                      value={buyerGstin}
                      onChange={e => setBuyerGstin(e.target.value.toUpperCase())}
                      placeholder="15-character GSTIN"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none uppercase font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Address / City</label>
                    <input
                      type="text"
                      value={buyerAddress}
                      onChange={e => setBuyerAddress(e.target.value)}
                      placeholder="City, State"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Accordion 2: Transportation & E-Way Bill */}
            <div className="transition-colors">
              <button
                type="button"
                onClick={() => setActiveAccordion(activeAccordion === 'transport' ? null : 'transport')}
                className="w-full p-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
                    <Truck className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <span>Transport & E-Way Bill</span>
                      {vehicleNumber && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 font-mono">
                          ✓ {vehicleNumber}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">Transporter details, vehicle number, and dispatch mode (Rule 138)</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium hidden sm:inline">
                    {activeAccordion === 'transport' ? 'Collapse' : 'Expand'}
                  </span>
                  {activeAccordion === 'transport' ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </div>
              </button>

              {activeAccordion === 'transport' && (
                <div className="p-4 bg-muted/15 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 animate-in fade-in-50 duration-150">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Vehicle Number</label>
                    <input
                      type="text"
                      value={vehicleNumber}
                      onChange={e => setVehicleNumber(e.target.value.toUpperCase())}
                      placeholder="e.g. MH04AB1234"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none uppercase font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Transporter Name</label>
                    <input
                      type="text"
                      value={transporterName}
                      onChange={e => setTransporterName(e.target.value)}
                      placeholder="e.g. VRL Logistics"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Transporter ID (GSTIN)</label>
                    <input
                      type="text"
                      value={transporterId}
                      onChange={e => setTransporterId(e.target.value.toUpperCase())}
                      placeholder="15-character GSTIN"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none uppercase font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Transport Doc / LR No.</label>
                    <input
                      type="text"
                      value={transportDocNo}
                      onChange={e => setTransportDocNo(e.target.value)}
                      placeholder="e.g. LR-98214"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">LR Document Date</label>
                    <input
                      type="date"
                      value={transportDocDate}
                      onChange={e => setTransportDocDate(e.target.value)}
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Transport Mode</label>
                    <select
                      value={transportMode}
                      onChange={e => setTransportMode(e.target.value)}
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    >
                      <option value="ROAD">Road</option>
                      <option value="RAIL">Rail</option>
                      <option value="AIR">Air</option>
                      <option value="SHIP">Ship</option>
                    </select>
                  </div>
                </div>
              )}
            </div>

            {/* Accordion 3: Freight Outward & Additional Discount */}
            <div className="transition-colors">
              <button
                type="button"
                onClick={() => setActiveAccordion(activeAccordion === 'charges' ? null : 'charges')}
                className="w-full p-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    <DollarSign className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <span>Freight & Cash Discount</span>
                      {(Number(cartageAmount) > 0 || Number(additionalDiscount) > 0) && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-mono">
                          {Number(cartageAmount) > 0 ? `+₹${cartageAmount} Cartage ` : ''}
                          {Number(additionalDiscount) > 0 ? `-₹${additionalDiscount} Disc` : ''}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">Cartage outward additions and special cash discounts</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium hidden sm:inline">
                    {activeAccordion === 'charges' ? 'Collapse' : 'Expand'}
                  </span>
                  {activeAccordion === 'charges' ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </div>
              </button>

              {activeAccordion === 'charges' && (
                <div className="p-4 bg-muted/15 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in-50 duration-150">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Cartage / Freight Outward (₹)
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={cartageAmount}
                      onChange={e => setCartageAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Added to invoice total as freight charges.
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Special Cash Discount / Rebate (₹)
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={additionalDiscount}
                      onChange={e => setAdditionalDiscount(e.target.value)}
                      placeholder="0.00"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Subtracted from invoice grand total.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Accordion 4: Bank Details & Instant UPI QR Code */}
            <div className="transition-colors">
              <button
                type="button"
                onClick={() => setActiveAccordion(activeAccordion === 'bank' ? null : 'bank')}
                className="w-full p-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400">
                    <QrCode className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <span>Bank Details & UPI Dynamic QR Code</span>
                      {(selectedBankLedgerId || upiId) && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                          ✓ Linked
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">Print bank accounts and NPCI-compliant UPI QR for instant invoice collections</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium hidden sm:inline">
                    {activeAccordion === 'bank' ? 'Collapse' : 'Expand'}
                  </span>
                  {activeAccordion === 'bank' ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </div>
              </button>

              {activeAccordion === 'bank' && (
                <div className="p-4 bg-muted/15 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in-50 duration-150">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Select Bank Account
                    </label>
                    <select
                      value={selectedBankLedgerId}
                      onChange={e => {
                        const chosenId = e.target.value;
                        setSelectedBankLedgerId(chosenId);
                        if (chosenId) {
                          const chosenLedger = ledgers.find(l => l.id === chosenId);
                          if (chosenLedger?.upi_id) {
                            setUpiId(chosenLedger.upi_id);
                          }
                        } else if (company?.upi_id) {
                          setUpiId(company.upi_id);
                        }
                      }}
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    >
                      <option value="">-- Use Default Company Bank --</option>
                      {ledgers
                        .filter(l => l.ledger_type === 'BANK' || l.group?.toLowerCase().includes('bank') || l.name?.toLowerCase().includes('bank'))
                        .map(l => (
                          <option key={l.id} value={l.id}>
                            {l.name}
                          </option>
                        ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      UPI ID / VPA for Dynamic QR
                    </label>
                    <input
                      type="text"
                      value={upiId}
                      onChange={e => setUpiId(e.target.value)}
                      placeholder="e.g. billing@okhdfcbank"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Customer scans QR code to pay exact invoice total instantly.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Accordion 5: Terms, Order Reference & Narration */}
            <div className="transition-colors">
              <button
                type="button"
                onClick={() => setActiveAccordion(activeAccordion === 'terms' ? null : 'terms')}
                className="w-full p-4 flex items-center justify-between hover:bg-muted/30 transition-colors text-left cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-teal-500/10 text-teal-600 dark:text-teal-400">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                      <span>Terms, Order Reference & Narration</span>
                      {(poNumber || narration || dueDate) && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-500/20">
                          ✓ Notes Added
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">Buyer purchase order number, payment terms, and voucher remarks</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium hidden sm:inline">
                    {activeAccordion === 'terms' ? 'Collapse' : 'Expand'}
                  </span>
                  {activeAccordion === 'terms' ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </div>
              </button>

              {activeAccordion === 'terms' && (
                <div className="p-4 bg-muted/15 border-t border-border/40 grid grid-cols-1 sm:grid-cols-3 gap-4 animate-in fade-in-50 duration-150">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Buyer Purchase Order (PO) #
                    </label>
                    <input
                      type="text"
                      value={poNumber}
                      onChange={e => setPoNumber(e.target.value)}
                      placeholder="e.g. PO-2026-881"
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      PO Date
                    </label>
                    <input
                      type="date"
                      value={poDate}
                      onChange={e => setPoDate(e.target.value)}
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Payment Due Date
                    </label>
                    <input
                      type="date"
                      value={dueDate}
                      onChange={e => setDueDate(e.target.value)}
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none font-mono"
                    />
                  </div>
                  <div className="sm:col-span-3">
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Voucher Narration / Terms & Conditions
                    </label>
                    <textarea
                      rows={2}
                      value={narration}
                      onChange={e => setNarration(e.target.value)}
                      placeholder="Special instructions, delivery terms, or voucher narration..."
                      className="w-full bg-background border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>
                </div>
              )}
            </div>

          </div>
        </div>

        {/* Totals Section */}
        <div className="flex justify-end">
            <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-3">
                {totalItemDiscount > 0 ? (
                  <>
                    <div className="flex justify-between text-muted-foreground text-sm">
                        <span>Gross Subtotal</span>
                        <span className="font-mono tabular-nums font-semibold text-foreground">₹{grossTotal.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-emerald-600 dark:text-emerald-400 text-sm font-medium">
                        <span>Total Item Discount</span>
                        <span className="font-mono tabular-nums font-semibold">-₹{totalItemDiscount.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-foreground text-sm font-semibold border-t border-dashed border-border/80 pt-1.5 pb-0.5">
                        <span>Taxable Subtotal (Discounted)</span>
                        <span className="font-mono tabular-nums font-bold text-foreground">₹{taxableSubtotal.toFixed(2)}</span>
                    </div>
                  </>
                ) : (
                  <div className="flex justify-between text-muted-foreground text-sm">
                      <span>Subtotal (Taxable)</span>
                      <span className="font-mono tabular-nums font-semibold text-foreground">₹{grossTotal.toFixed(2)}</span>
                  </div>
                )}
                {isInterState ? (
                    <div className="flex justify-between text-primary text-sm font-medium">
                        <span>IGST</span>
                        <span className="font-mono tabular-nums font-semibold">₹{totalTax.toFixed(2)}</span>
                    </div>
                ) : (
                    <>
                        <div className="flex justify-between text-muted-foreground text-sm">
                            <span>CGST</span>
                            <span className="font-mono tabular-nums font-semibold text-foreground">₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-muted-foreground text-sm">
                            <span>SGST</span>
                            <span className="font-mono tabular-nums font-semibold text-foreground">₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                    </>
                )}
                {Number(cartageAmount) > 0 && (
                  <div className="flex justify-between items-center text-muted-foreground text-sm">
                      <span>Cartage / Freight Outward</span>
                      <span className="font-mono tabular-nums font-semibold text-foreground">+₹{Number(cartageAmount).toFixed(2)}</span>
                  </div>
                )}
                {Number(additionalDiscount) > 0 && (
                  <div className="flex justify-between items-center text-emerald-600 dark:text-emerald-400 text-sm">
                      <span>Special Cash Discount</span>
                      <span className="font-mono tabular-nums font-semibold">-₹{Number(additionalDiscount).toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-muted-foreground text-sm">
                    <span>Round Off</span>
                    <span className={roundOff < 0 ? "text-emerald-500 font-mono tabular-nums font-semibold" : roundOff > 0 ? "text-amber-500 font-mono tabular-nums font-semibold" : "text-muted-foreground font-mono tabular-nums"}>
                        {roundOff > 0 ? `+₹${roundOff.toFixed(2)}` : roundOff < 0 ? `-₹${Math.abs(roundOff).toFixed(2)}` : `₹0.00`}
                    </span>
                </div>
                <div className="border-t border-border pt-4 flex justify-between text-xl font-bold text-foreground">
                    <span>Grand Total</span>
                    <span className="font-mono tabular-nums text-2xl text-primary font-black">₹{grandTotal.toFixed(2)}</span>
                </div>
            </div>
        </div>

        {/* Double-Entry Posting Impact Accordion (Progressive Disclosure) */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setIsPostingImpactOpen(!isPostingImpactOpen)}
            className="w-full px-5 py-3.5 flex items-center justify-between text-xs font-bold text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <Scale className="w-4 h-4 text-primary" />
              <span>Accounting Details & Double-Entry Impact</span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground font-mono text-[11px]">
              <span>Balanced: ₹{grandTotal.toFixed(2)} Dr = ₹{grandTotal.toFixed(2)} Cr</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isPostingImpactOpen ? "rotate-180" : ""}`} />
            </div>
          </button>

          {isPostingImpactOpen && (
            <div className="px-5 pb-4 pt-1 border-t border-border/50 space-y-2.5 text-xs">
              <p className="text-[11px] text-muted-foreground">
                Automatic double-entry ledger impact calculated for this sales invoice:
              </p>
              <div className="rounded-lg border border-border/60 overflow-hidden font-mono text-[11px]">
                <div className="grid grid-cols-12 bg-muted/70 px-3 py-1.5 font-bold text-muted-foreground uppercase text-[10px]">
                  <span className="col-span-1">Type</span>
                  <span className="col-span-7">Ledger Account</span>
                  <span className="col-span-2 text-right">Debit (Dr)</span>
                  <span className="col-span-2 text-right">Credit (Cr)</span>
                </div>
                {/* 1. Debit Party Ledger */}
                <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                  <span className="col-span-1 font-bold text-blue-500">Dr</span>
                  <span className="col-span-7 font-sans truncate font-medium text-foreground">
                    {ledgers.find((l) => l.id === partyLedgerId)?.name || "Customer Account (Sundry Debtors)"}
                  </span>
                  <span className="col-span-2 text-right font-bold text-foreground">₹{grandTotal.toFixed(2)}</span>
                  <span className="col-span-2 text-right text-muted-foreground">-</span>
                </div>
                {/* 2. Credit Sales Ledger */}
                <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                  <span className="col-span-1 font-bold text-emerald-500">Cr</span>
                  <span className="col-span-7 font-sans truncate font-medium text-foreground">
                    {ledgers.find((l) => l.id === salesLedgerId)?.name || "Domestic Sales Account"}
                  </span>
                  <span className="col-span-2 text-right text-muted-foreground">-</span>
                  <span className="col-span-2 text-right font-bold text-foreground">₹{grossTotal.toFixed(2)}</span>
                </div>
                {/* 3. Taxes */}
                {isInterState ? (
                  Number(totalTax) > 0 && (
                    <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                      <span className="col-span-1 font-bold text-emerald-500">Cr</span>
                      <span className="col-span-7 font-sans truncate font-medium text-foreground">Output IGST Payable</span>
                      <span className="col-span-2 text-right text-muted-foreground">-</span>
                      <span className="col-span-2 text-right font-bold text-foreground">₹{totalTax.toFixed(2)}</span>
                    </div>
                  )
                ) : (
                  Number(totalTax) > 0 && (
                    <>
                      <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                        <span className="col-span-1 font-bold text-emerald-500">Cr</span>
                        <span className="col-span-7 font-sans truncate font-medium text-foreground">Output CGST Payable</span>
                        <span className="col-span-2 text-right text-muted-foreground">-</span>
                        <span className="col-span-2 text-right font-bold text-foreground">₹{(totalTax / 2).toFixed(2)}</span>
                      </div>
                      <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                        <span className="col-span-1 font-bold text-emerald-500">Cr</span>
                        <span className="col-span-7 font-sans truncate font-medium text-foreground">Output SGST Payable</span>
                        <span className="col-span-2 text-right text-muted-foreground">-</span>
                        <span className="col-span-2 text-right font-bold text-foreground">₹{(totalTax / 2).toFixed(2)}</span>
                      </div>
                    </>
                  )
                )}
                {/* 4. Round Off */}
                {roundOff !== 0 && (
                  <div className="grid grid-cols-12 px-3 py-1.5 border-t border-border/40 bg-card items-center">
                    <span className="col-span-1 font-bold text-amber-500">{roundOff < 0 ? "Dr" : "Cr"}</span>
                    <span className="col-span-7 font-sans truncate font-medium text-foreground">Round Off Account</span>
                    <span className="col-span-2 text-right font-bold text-foreground">{roundOff < 0 ? `₹${Math.abs(roundOff).toFixed(2)}` : "-"}</span>
                    <span className="col-span-2 text-right font-bold text-foreground">{roundOff > 0 ? `₹${roundOff.toFixed(2)}` : "-"}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Bottom Save Action for Mobile PWA */}
        <div className="flex sm:hidden justify-end pt-2 pb-6">
          <button
            onClick={handleSave}
            disabled={saving || isReadOnly}
            className={`w-full justify-center px-6 py-3.5 rounded-xl shadow-lg font-bold text-base transition-all flex items-center gap-2 cursor-pointer ${
              isReadOnly
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30 cursor-not-allowed opacity-80'
                : 'bg-blue-600 hover:bg-blue-700 active:scale-[0.98] text-white disabled:opacity-50'
            }`}
          >
            {saving ? 'Posting Invoice...' : isReadOnly ? 'Period Closed (Read-Only)' : 'Post Invoice'}
          </button>
        </div>

      </div>

      {/* Unified Brand Selection Modal */}
      {brandModalTarget && (() => {
        const gIdx = brandModalTarget.gIndex;
        const iIdx = brandModalTarget.iIndex;
        const currentItem = groupedItems[gIdx]?.items[iIdx];
        if (!currentItem) return null;

        const currentBrand = (currentItem.brand || '').trim();
        const rawQuery = (currentItem.product_name || '').toLowerCase();
        const queryAlpha = rawQuery.replace(/[\s\-_/.]/g, '');
        const sizeMatch = queryAlpha.match(/([a-z]{0,3}\d{2,5}[a-z]{0,2})/);
        const coreSizeToken = sizeMatch ? sizeMatch[0] : (queryAlpha.length >= 2 ? queryAlpha : '');

        // Cross-brand catalog products matching the core size/name
        const matchingProds = coreSizeToken.length >= 2 ? products.filter((p: any) => {
          const pAlpha = (p.name || '').toLowerCase().replace(/[\s\-_/.]/g, '');
          const aAlpha = (p.alias || '').toLowerCase().replace(/[\s\-_/.]/g, '');
          const dAlpha = (p.description || '').toLowerCase().replace(/[\s\-_/.]/g, '');
          return pAlpha.includes(coreSizeToken) || aAlpha.includes(coreSizeToken) || dAlpha.includes(coreSizeToken);
        }) : [];

        const filteredMatchingProds = matchingProds.filter((p: any) => {
          if (!brandSearchQuery.trim()) return true;
          const q = brandSearchQuery.toLowerCase();
          return (p.brand || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q);
        });

        // Unique catalog brands across all products
        const allCatalogBrands = Array.from(new Set(products.map((p: any) => (p.brand || '').trim()).filter(Boolean))).sort();
        const filteredCatalogBrands = allCatalogBrands.filter((b: string) =>
          !brandSearchQuery.trim() || b.toLowerCase().includes(brandSearchQuery.toLowerCase())
        );

        return (
          <div 
            className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-4 animate-in fade-in duration-150"
            onClick={() => setBrandModalTarget(null)}
          >
            <div 
              className="bg-card text-card-foreground border border-slate-200 dark:border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-muted/40">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-blue-50 text-blue-700 border border-blue-200 dark:bg-primary/10 dark:border-primary/20 dark:text-primary flex items-center justify-center font-bold">
                    <Tag className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-base text-foreground flex items-center gap-2">
                      Select Brand
                      {currentBrand && (
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200 dark:bg-primary/15 dark:text-primary dark:border-primary/30 font-semibold">
                          Current: {currentBrand}
                        </span>
                      )}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate max-w-md">
                      Item: <span className="font-semibold text-foreground">{currentItem.product_name || 'New Item'}</span>
                      {coreSizeToken && <span className="ml-1.5 opacity-75 font-mono">(Size key: {coreSizeToken.toUpperCase()})</span>}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setBrandModalTarget(null)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Search & Actions Bar */}
              <div className="p-4 border-b border-border bg-background flex flex-col gap-2.5">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    autoFocus
                    value={brandSearchQuery}
                    onChange={(e) => setBrandSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && brandSearchQuery.trim()) {
                        selectBrand(gIdx, iIdx, brandSearchQuery.trim());
                        setBrandModalTarget(null);
                      }
                    }}
                    placeholder="Search brand name, or type a new brand and press Enter..."
                    className="w-full pl-9 pr-28 py-2 text-sm bg-slate-50 dark:bg-muted/40 border border-slate-200 dark:border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-600 transition-all text-slate-900 dark:text-foreground placeholder:text-slate-400 dark:placeholder:text-muted-foreground font-medium"
                  />
                  {brandSearchQuery.trim() && (
                    <button
                      type="button"
                      onClick={() => {
                        selectBrand(gIdx, iIdx, brandSearchQuery.trim());
                        setBrandModalTarget(null);
                      }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-semibold px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-all cursor-pointer shadow-xs"
                    >
                      Apply &quot;{brandSearchQuery.trim()}&quot;
                    </button>
                  )}
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">
                    {filteredMatchingProds.length > 0
                      ? `${filteredMatchingProds.length} direct product equivalent(s) found in size ${coreSizeToken.toUpperCase()}`
                      : `${filteredCatalogBrands.length} brand(s) in catalog`}
                  </span>
                  {currentBrand && (
                    <button
                      type="button"
                      onClick={() => {
                        selectBrand(gIdx, iIdx, '');
                        setBrandModalTarget(null);
                      }}
                      className="text-slate-500 hover:text-rose-600 dark:text-muted-foreground dark:hover:text-destructive font-medium underline transition-colors cursor-pointer"
                    >
                      Clear Brand (Set Unbranded)
                    </button>
                  )}
                </div>
              </div>

              {/* Content Body */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Section 1: Direct Cross-Brand Equivalents (with Stock & Party Rates) */}
                {filteredMatchingProds.length > 0 && (
                  <div>
                    <div className="flex items-center gap-1.5 text-xs font-bold text-foreground uppercase tracking-wider mb-2.5">
                      <Layers className="w-3.5 h-3.5 text-blue-600 dark:text-primary" />
                      <span>Available Equivalents in Size &quot;{coreSizeToken.toUpperCase()}&quot;</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {filteredMatchingProds.map((altProd: any) => {
                        const isCurrent = altProd.brand?.toLowerCase() === currentBrand.toLowerCase();
                        const stock = Number(altProd.stock_quantity ?? 0);
                        const isStocked = stock > 0;
                        const mrp = parseFloat(altProd.selling_price) || 0;
                        const cost = parseFloat(altProd.purchase_price) || 0;
                        const altPast = resolvePartyRateForBrand(partyRates, altProd.id, altProd.name, altProd.brand);

                        return (
                          <button
                            key={altProd.id}
                            type="button"
                            onClick={() => {
                              selectProduct(gIdx, iIdx, altProd);
                              setBrandModalTarget(null);
                            }}
                            className={`text-left p-3 rounded-xl border transition-all cursor-pointer relative group flex flex-col justify-between gap-2 ${
                              isCurrent
                                ? 'border-blue-600 bg-blue-50/70 dark:bg-primary/10 dark:border-primary shadow-sm ring-1 ring-blue-600 dark:ring-primary/30'
                                : isStocked
                                ? 'border-emerald-200 bg-white hover:bg-emerald-50/50 dark:border-emerald-500/30 dark:bg-emerald-500/5 dark:hover:bg-emerald-500/10 shadow-xs'
                                : 'border-slate-200 bg-slate-50/70 hover:bg-slate-100 dark:border-border/80 dark:bg-muted/30 dark:hover:bg-muted/60 opacity-80'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <div className="flex items-center gap-1.5">
                                  <span className="font-bold text-sm text-blue-700 dark:text-blue-400">
                                    {altProd.brand || 'Unbranded'}
                                  </span>
                                  {isCurrent && (
                                    <span className="text-[10px] bg-blue-600 text-white dark:bg-primary dark:text-primary-foreground font-semibold px-2 py-0.5 rounded-full flex items-center gap-0.5">
                                      <Check className="w-2.5 h-2.5" /> Selected
                                    </span>
                                  )}
                                </div>
                                <div className="text-xs text-slate-800 dark:text-slate-200 truncate font-mono font-semibold">
                                  {altProd.name}
                                </div>
                              </div>
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0 ${
                                  isStocked
                                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30'
                                    : 'bg-slate-100 text-slate-600 border border-slate-200 dark:bg-muted dark:text-muted-foreground dark:border-border font-medium'
                                }`}
                              >
                                {isStocked ? `${stock} ${altProd.unit || 'PCS'} in Stock` : 'Out of stock'}
                              </span>
                            </div>

                            {/* Pricing Bar */}
                            <div className="pt-2 border-t border-slate-100 dark:border-border/40 flex items-center justify-between text-[11px]">
                              {altPast && Number(altPast.rate) > 0 ? (
                                <div className="text-blue-700 dark:text-blue-400 font-bold flex items-center gap-1">
                                  <span>Last Sold:</span>
                                  <span className="font-bold">₹{Number(altPast.rate).toFixed(2)}</span>
                                </div>
                              ) : mrp > 0 ? (
                                <div className="text-slate-900 dark:text-foreground font-semibold flex items-center gap-1">
                                  <span>MRP:</span>
                                  <span>₹{mrp.toFixed(2)}</span>
                                </div>
                              ) : (
                                <span className="text-muted-foreground italic text-[10px]">No price set</span>
                              )}

                              {cost > 0 && (
                                <span className="text-[10px] text-muted-foreground">
                                  Cost: ₹{cost.toFixed(2)}
                                </span>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Section 2: Catalog Brands Grid */}
                <div>
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="text-xs font-bold text-foreground uppercase tracking-wider">
                      {filteredMatchingProds.length > 0 ? 'Other Catalog Brands' : 'Catalog Brands'}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Click brand to assign to this line
                    </span>
                  </div>
                  {filteredCatalogBrands.length > 0 ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                      {filteredCatalogBrands.map((bName: string) => {
                        const isCurrent = bName.toLowerCase() === currentBrand.toLowerCase();
                        return (
                          <button
                            key={bName}
                            type="button"
                            onClick={() => {
                              selectBrand(gIdx, iIdx, bName);
                              setBrandModalTarget(null);
                            }}
                            className={`px-3 py-2 rounded-xl text-xs font-medium border text-left flex items-center justify-between gap-1 transition-all cursor-pointer ${
                              isCurrent
                                ? 'bg-blue-600 text-white border-blue-600 font-bold shadow-xs dark:bg-primary dark:text-primary-foreground dark:border-primary'
                                : 'bg-slate-50 hover:bg-slate-100 text-slate-800 border-slate-200 hover:border-slate-300 dark:bg-muted/40 dark:hover:bg-muted dark:text-foreground dark:border-border/70 dark:hover:border-border'
                            }`}
                          >
                            <span className="truncate">{bName}</span>
                            {isCurrent && <Check className="w-3.5 h-3.5 shrink-0" />}
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="p-4 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
                      No catalog brand matches &quot;{brandSearchQuery}&quot;. Press Enter above to apply as a custom brand.
                    </div>
                  )}
                </div>
              </div>

              {/* Modal Footer */}
              <div className="px-5 py-3 border-t border-border bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
                <span>Tip: Press <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border font-mono text-[10px]">Esc</kbd> to close</span>
                <button
                  type="button"
                  onClick={() => setBrandModalTarget(null)}
                  className="px-4 py-1.5 rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 font-medium cursor-pointer transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </DashboardLayout>
  );
}
