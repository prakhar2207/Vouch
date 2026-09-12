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
import { useToast } from '@/context/ToastContext';
import { ChevronDown, ScanBarcode, AlertTriangle, CheckCircle2, ArrowRight, Hash } from 'lucide-react';
import { queueOfflineVoucher } from '@/lib/sync/sync-worker';
import { offlineDb } from '@/lib/db/offlineDb';

export default function SalesPage() {
  const router = useRouter();
  const { toast } = useToast();
  const { workingDate, registerSaveHandler, registerAltCCallback } = useShortcuts();
  const { activeFY, isReadOnly } = useFinancialYear();
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
  
  // Ad-hoc Walk-in / Cash Customer Details
  const [buyerName, setBuyerName] = useState('');
  const [buyerPhone, setBuyerPhone] = useState('');
  const [buyerAddress, setBuyerAddress] = useState('');
  const [buyerGstin, setBuyerGstin] = useState('');
  const [buyerStateCode, setBuyerStateCode] = useState('');
  const [showBuyerDetails, setShowBuyerDetails] = useState(false);
  
  // Cartage / Freight Outward
  const [cartageAmount, setCartageAmount] = useState<number | string>('');
  
  const [categories, setCategories] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [activeSearch, setActiveSearch] = useState<string | null>(null);
  const [openBrandDropdown, setOpenBrandDropdown] = useState<string | null>(null);
  const [partyRates, setPartyRates] = useState<Record<string, any>>({});
  const [loadingPartyRates, setLoadingPartyRates] = useState(false);
  const [groupedItems, setGroupedItems] = useState<any[]>([
    { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', product_id: '', brand: '', unit: 'PCS', quantity: 1, rate: 0, discount_percent: 0 } ] }
  ]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const barcodeInputRef = React.useRef<HTMLInputElement>(null);

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
    const handleGlobalClick = () => {
      setOpenBrandDropdown(null);
    };
    window.addEventListener('click', handleGlobalClick);
    return () => window.removeEventListener('click', handleGlobalClick);
  }, []);

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
    fetchBaseData();
  }, [router]);

  const fetchBaseData = async () => {
    try {
      // First, attempt to load cached masters from offline IndexedDB immediately
      try {
        const cachedComp = await offlineDb.masters.get('company');
        const cachedLedgers = await offlineDb.masters.get('ledgers');
        const cachedCats = await offlineDb.masters.get('categories');
        const cachedProds = await offlineDb.masters.get('products');

        if (cachedComp?.data) {
          setCompany(cachedComp.data);
          setCompanyId(cachedComp.data.id);
          setCompanyStateCode(cachedComp.data.state_code || '');
          setEnableLedgerMapping(cachedComp.data.settings?.enable_ledger_mapping || false);
          setEnableManualInvoice(cachedComp.data.settings?.enable_manual_invoice_number || false);
        }
        if (cachedLedgers?.data?.length) {
          setLedgers(cachedLedgers.data);
          applyDefaultLedgers(cachedLedgers.data, cachedComp?.data?.settings?.enable_ledger_mapping || false, cachedComp?.data?.id);
        }
        if (cachedCats?.data?.length) setCategories(cachedCats.data);
        if (cachedProds?.data?.length) setProducts(cachedProds.data);
      } catch (cacheErr) {
        console.warn('Could not read from local offline cache', cacheErr);
      }

      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      const compRes = await axios.get(`${API_BASE_URL}/api/v1/companies/`, { headers });
      const comp = compRes.data.data[0];
      const cId = comp?.id;
      if (!cId) return;
      setCompany(comp);
      setCompanyId(cId);
      setCompanyStateCode(comp.state_code || '');
      
      const isMappingEnabled = comp.settings?.enable_ledger_mapping || false;
      setEnableLedgerMapping(isMappingEnabled);
      setEnableManualInvoice(comp.settings?.enable_manual_invoice_number || false);

      // Cache company
      offlineDb.masters.put({ key: 'company', data: comp, updatedAt: Date.now() }).catch(() => {});

      const [ledgersRes, catsRes, prodsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cId}/`, { headers }).catch(() => ({ data: { data: [] } }))
      ]);
      const ledgerList = ledgersRes.data.data || [];
      const catList = catsRes.data.data || [];
      const prodList = prodsRes.data?.data || [];

      setLedgers(ledgerList);
      setCategories(catList);
      setProducts(prodList);
      
      // Save freshly fetched data to local offline DB for offline use
      offlineDb.masters.put({ key: 'ledgers', data: ledgerList, updatedAt: Date.now() }).catch(() => {});
      offlineDb.masters.put({ key: 'categories', data: catList, updatedAt: Date.now() }).catch(() => {});
      offlineDb.masters.put({ key: 'products', data: prodList, updatedAt: Date.now() }).catch(() => {});

      applyDefaultLedgers(ledgerList, isMappingEnabled, cId);
    } catch (err) {
      console.error('Network fetch failed, continuing with offline cache if available:', err);
    } finally {
      setLoading(false);
    }
  };

  const applyDefaultLedgers = (ledgerList: any[], isMappingEnabled: boolean, cId?: string) => {
    const party = ledgerList.find((l:any) => l.name.includes('Customer') || l.group.includes('Debtors'));
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
            const cleanName = String(item.product_name).trim().toLowerCase();
            const cleanBrand = String(item.brand || '').trim().toLowerCase();
            const keyId = item.product_id;
            const keyBrand = `${cleanName}|${cleanBrand}`;
            const pastRateInfo = (keyId && rates[keyId]) || rates[keyBrand] || rates[cleanName];
            if (pastRateInfo && Number(pastRateInfo.rate) > 0) {
              return {
                ...item,
                rate: Number(pastRateInfo.rate),
                last_party_rate: Number(pastRateInfo.rate),
                last_party_date: pastRateInfo.voucher_date,
                last_party_vnum: pastRateInfo.voucher_number
              };
            }
            return {
              ...item,
              last_party_rate: null,
              last_party_date: null,
              last_party_vnum: null
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
      setShowBuyerDetails(true);
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
        offlineDb.masters.put({ key: 'company', data: updatedComp, updatedAt: Date.now() }).catch(() => {});
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
        post_immediately: true
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
      
      try {
        const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/sales-invoice/`, payload, { headers, timeout: 8000 });
        toast.success(`Sales Invoice generated!`, `Voucher: ${res.data.voucher_number}`);
        router.push('/sales');
        router.refresh();
      } catch (postErr: any) {
        // If offline or network error, store in local IndexedDB outbox!
        const isNetworkErr = !navigator.onLine || postErr.code === 'ERR_NETWORK' || !postErr.response;
        if (isNetworkErr) {
          const offlineRes = await queueOfflineVoucher('SALES', payload, invoiceDate);
          toast.success(
            "⚡ Saved Offline to Local Database!",
            `Stored securely on device (${offlineRes.localId}). Will sync to Neon cloud automatically.`
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
    
    // Look up remembered sales rate for this party
    const keyId = prod.id;
    const cleanName = String(prod.name || '').trim().toLowerCase();
    const cleanBrand = String(prod.brand || '').trim().toLowerCase();
    const keyBrand = `${cleanName}|${cleanBrand}`;
    const pastRateInfo = (keyId && partyRates[keyId]) || partyRates[keyBrand] || partyRates[cleanName];

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

        // Look up remembered sales rate for this brand
        const keyId = match.id;
        const cleanName = String(match.name || '').trim().toLowerCase();
        const cleanBrand = String(match.brand || brandName).trim().toLowerCase();
        const keyBrand = `${cleanName}|${cleanBrand}`;
        const pastRateInfo = (keyId && partyRates[keyId]) || partyRates[keyBrand];

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

          const keyId = match.id;
          const cleanName = String(match.name || '').trim().toLowerCase();
          const cleanBrand = String(match.brand || item.brand || '').trim().toLowerCase();
          const keyBrand = `${cleanName}|${cleanBrand}`;
          const pastRateInfo = (keyId && partyRates[keyId]) || partyRates[keyBrand] || partyRates[cleanName];

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
      discount_percent: currentPartyDiscount 
    });
    setGroupedItems(newGroups);
  };

  const removeRow = (gIndex: number, iIndex: number) => {
    const newGroups = [...groupedItems];
    if (newGroups[gIndex].items.length === 1) return;
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

    // Determine rate: past party rate or catalog selling price
    const keyId = matchedProd.id;
    const cleanName = String(matchedProd.name || '').trim().toLowerCase();
    const cleanBrand = String(matchedProd.brand || '').trim().toLowerCase();
    const keyBrand = `${cleanName}|${cleanBrand}`;
    const pastRateInfo = (keyId && partyRates[keyId]) || partyRates[keyBrand] || partyRates[cleanName];
    const catalogMrp = parseFloat(matchedProd.selling_price) || 0;
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
  const totalTax = allItems.reduce((sum, item) => {
      const gross = Number(item.quantity) * Number(item.rate);
      const discount = gross * (Number(item.discount_percent)/100);
      const taxable = gross - discount;
      return sum + (taxable * (Number(item.gst_rate)/100));
  }, 0);
  const cartageVal = Number(cartageAmount) || 0;
  const unroundedGrandTotal = allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const discount = gross * (Number(item.discount_percent)/100);
    const taxable = gross - discount;
    return sum + taxable + (taxable * (Number(item.gst_rate)/100));
  }, 0) + cartageVal;

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
              {activeFY && (
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
            {seqPreview && (
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
                  Invoice Date {activeFY && <span className="text-muted-foreground font-normal font-mono">({activeFY.code})</span>}
                </label>
                {activeFY && (
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
                  <span className="text-[11px] text-zinc-400">Applied automatically • Editable below</span>
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

          {/* Ad-hoc Buyer Details Subform for Cash / Walk-in Customers */}
          <div className="mt-5 pt-4 border-t border-border">
            <div 
              className="flex items-center justify-between cursor-pointer select-none bg-zinc-900/40 hover:bg-zinc-900/80 p-3 rounded-lg border border-border/80 transition-all"
              onClick={() => setShowBuyerDetails(!showBuyerDetails)}
            >
              <div className="flex items-center gap-2.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                <span className="text-sm font-semibold text-zinc-200">Buyer Details (Optional — Cash / Counter Walk-in)</span>
                <span className="text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded font-mono">
                  Prints on bill without creating a Debtor
                </span>
              </div>
              <span className="text-xs text-zinc-400 hover:text-foreground font-medium">
                {showBuyerDetails ? '▲ Hide Details' : '▼ Enter Walk-in Details'}
              </span>
            </div>

            {showBuyerDetails && (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-zinc-900/40 border border-border/60 rounded-xl">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Walk-in Buyer Name</label>
                  <input
                    type="text"
                    value={buyerName}
                    onChange={e => setBuyerName(e.target.value)}
                    placeholder="e.g. Ramesh Kumar"
                    className="w-full bg-muted/50 border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Mobile / Phone</label>
                  <input
                    type="text"
                    value={buyerPhone}
                    onChange={e => setBuyerPhone(e.target.value)}
                    placeholder="e.g. 9876543210"
                    className="w-full bg-muted/50 border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">GSTIN (Optional)</label>
                  <input
                    type="text"
                    value={buyerGstin}
                    onChange={e => setBuyerGstin(e.target.value.toUpperCase())}
                    placeholder="Unregistered or 15-digit GSTIN"
                    className="w-full bg-muted/50 border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none uppercase font-mono placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Billing Address / City</label>
                  <input
                    type="text"
                    value={buyerAddress}
                    onChange={e => setBuyerAddress(e.target.value)}
                    placeholder="City, State"
                    className="w-full bg-muted/50 border border-input text-foreground text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
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
                    <span className="text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded border border-blue-400/20">Auto-Creates & Inherits Tax</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">Rapid billing for retail and wholesale</p>
                </div>
                
                {/* Barcode Quick-Scan Input (P1-5) */}
                <div className="flex items-center gap-2 w-full md:w-80">
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
            
            <div className="p-2 space-y-6">
                {groupedItems.map((group, gIndex) => (
                    <div key={gIndex} className="border border-border rounded-xl overflow-hidden bg-card shadow-sm">
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
                                    <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20 text-xs font-medium">
                                        IGST: {group.gst_rate}%
                                    </span>
                                ) : (
                                    <div className="flex gap-2">
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">CGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                        <span className="bg-muted text-foreground/80 px-2 py-0.5 rounded border border-input text-xs font-medium">SGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                    </div>
                                )}
                                <button onClick={() => removeCategoryGroup(gIndex)} className="text-red-500 hover:text-red-400 ml-auto sm:ml-4 p-1" title="Delete category group">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                            </div>
                        </div>
                        
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[550px] text-left border-collapse">
                                <thead className="bg-muted/60 text-muted-foreground text-xs uppercase tracking-wider">
                                    <tr>
                                        <th className="p-3 font-semibold">Product Name</th>
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
                                        <tr key={iIndex} className="hover:bg-zinc-800/40 transition-colors">
                                            <td className="p-2 relative">
                                                <div className="relative">
                                                    <input 
                                                        type="text" 
                                                        placeholder="e.g. Item Name or Size" 
                                                        value={item.product_name} 
                                                        onChange={e => {
                                                            updateItem(gIndex, iIndex, 'product_name', e.target.value);
                                                            setActiveSearch(`${gIndex}-${iIndex}`);
                                                        }} 
                                                        onFocus={() => setActiveSearch(`${gIndex}-${iIndex}`)}
                                                        onBlur={() => setTimeout(() => setActiveSearch(null), 250)}
                                                        className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-sm font-medium" 
                                                    />

                                                    {/* Autocomplete Dropdown Popover */}
                                                    {activeSearch === `${gIndex}-${iIndex}` && (
                                                        <div 
                                                            className="absolute left-0 top-full mt-1 z-50 w-full min-w-[340px] max-w-[480px] bg-card border border-border rounded-xl shadow-2xl overflow-hidden max-h-64 overflow-y-auto"
                                                            onMouseDown={(e) => e.preventDefault()}
                                                        >
                                                            {(() => {
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
                                                                    return (
                                                                        pName.includes(query) ||
                                                                        pAlpha.includes(queryAlpha) ||
                                                                        pBrand.includes(query) ||
                                                                        pAlias.includes(query) ||
                                                                        pSku.includes(query)
                                                                    );
                                                                });

                                                                if (filteredProds.length === 0) {
                                                                    return (
                                                                        <div className="p-3 text-xs text-zinc-500 italic">
                                                                            No catalog product found. Enter details manually.
                                                                        </div>
                                                                    );
                                                                }

                                                                return (
                                                                    <div className="divide-y divide-zinc-800/70">
                                                                        <div className="bg-zinc-900/90 px-3 py-1.5 text-[10px] font-semibold text-zinc-400 uppercase tracking-wider flex justify-between">
                                                                            <span>Catalog SKUs</span>
                                                                            <span>{filteredProds.length} match{filteredProds.length > 1 ? 'es' : ''}</span>
                                                                        </div>
                                                                        {filteredProds.map((p: any) => {
                                                                            const mrp = parseFloat(p.selling_price) || 0;
                                                                            const stock = Number(p.stock_quantity ?? 0);
                                                                            const isSelected = item.product_id === p.id;
                                                                            const keyBrand = `${(p.name || '').trim().toLowerCase()}|${(p.brand || '').trim().toLowerCase()}`;
                                                                            const pPast = (p.id && partyRates[p.id]) || partyRates[keyBrand] || partyRates[(p.name || '').trim().toLowerCase()];
                                                                            return (
                                                                                <button
                                                                                    key={p.id}
                                                                                    type="button"
                                                                                    onClick={() => {
                                                                                        selectProduct(gIndex, iIndex, p);
                                                                                        setActiveSearch(null);
                                                                                    }}
                                                                                    className={`w-full text-left p-2.5 hover:bg-zinc-800/90 flex items-center justify-between gap-3 cursor-pointer transition-colors ${
                                                                                        isSelected ? 'bg-blue-600/15 border-l-2 border-blue-500' : ''
                                                                                    }`}
                                                                                >
                                                                                    <div className="flex-1 min-w-0">
                                                                                        <div className="flex items-center gap-2 flex-wrap">
                                                                                            <span className="font-semibold text-foreground text-sm truncate">{p.name}</span>
                                                                                            {p.brand ? (
                                                                                                <span className="text-[10px] px-1.5 py-0.2 rounded font-bold uppercase bg-blue-500/20 text-blue-300 border border-blue-500/30">
                                                                                                    {p.brand}
                                                                                                </span>
                                                                                            ) : (
                                                                                                <span className="text-[10px] px-1.5 py-0.2 rounded font-medium text-zinc-500 bg-muted/50 border border-border">
                                                                                                    Unbranded
                                                                                                </span>
                                                                                            )}
                                                                                            {pPast && (
                                                                                                <span className="text-[10px] px-1.5 py-0.2 rounded font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" title={`Last invoiced to this party at ₹${Number(pPast.rate).toFixed(2)} on ${pPast.voucher_date || 'past bill'}`}>
                                                                                                    Party Rate: ₹{Number(pPast.rate).toFixed(2)}
                                                                                                </span>
                                                                                            )}
                                                                                        </div>
                                                                                        <div className="text-[11px] text-zinc-400 truncate mt-0.5">
                                                                                            {p.category} {p.sku ? `• SKU: ${p.sku}` : ''}
                                                                                        </div>
                                                                                    </div>
                                                                                    <div className="text-right whitespace-nowrap pl-2">
                                                                                        <div className="text-xs font-mono font-bold text-zinc-300">
                                                                                            {mrp > 0 ? `MRP: ₹${mrp.toFixed(2)}` : 'No MRP'}
                                                                                        </div>
                                                                                        {pPast && (
                                                                                            <div className="text-[11px] font-mono font-bold text-emerald-400">
                                                                                                Party: ₹{Number(pPast.rate).toFixed(2)}
                                                                                            </div>
                                                                                        )}
                                                                                        <div className={`text-[10px] font-mono font-medium ${stock > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                                                            Avail: {stock} {p.unit || 'PCS'}
                                                                                        </div>
                                                                                    </div>
                                                                                </button>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                );
                                                            })()}
                                                        </div>
                                                    )}
                                                </div>

                                                {item.product_name && (
                                                    <div className="flex items-center gap-2 mt-0.5 px-1.5 flex-wrap">
                                                        {/* Master MRP (Catalog price - protected from invoice overrides) */}
                                                        {(() => {
                                                            const matched = products.find((p: any) => 
                                                                (item.product_id && p.id === item.product_id) || 
                                                                (p.name.toLowerCase() === String(item.product_name || '').trim().toLowerCase() && 
                                                                 (!item.brand || (p.brand || '').toLowerCase() === item.brand.toLowerCase()))
                                                            );
                                                            const catalogMrp = parseFloat(matched?.selling_price || item.mrp || 0);
                                                            
                                                            if (catalogMrp > 0) {
                                                                return (
                                                                    <span className="text-[11px] font-mono flex items-center gap-1 bg-zinc-900/90 text-zinc-400 border border-border px-2 py-0.5 rounded">
                                                                        <span className="text-zinc-500 font-sans">MRP:</span>
                                                                        <strong className="text-zinc-200">₹{catalogMrp.toFixed(2)}</strong>
                                                                        {Number(item.rate) !== catalogMrp && (
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => updateItem(gIndex, iIndex, 'rate', catalogMrp)}
                                                                                className="text-[10px] text-blue-400 hover:text-blue-300 ml-1 underline cursor-pointer"
                                                                                title="Click to apply master catalog MRP to this line"
                                                                            >
                                                                                Use MRP
                                                                            </button>
                                                                        )}
                                                                    </span>
                                                                );
                                                            }
                                                            return <span className="text-[11px] text-zinc-500 italic">No MRP stored</span>;
                                                        })()}

                                                        {/* Party's Remembered Past Sales Rate */}
                                                        {(() => {
                                                            const matched = products.find((p: any) => 
                                                                (item.product_id && p.id === item.product_id) || 
                                                                (p.name.toLowerCase() === String(item.product_name || '').trim().toLowerCase() && 
                                                                 (!item.brand || (p.brand || '').toLowerCase() === item.brand.toLowerCase()))
                                                            );
                                                            const cleanName = String(item.product_name || '').trim().toLowerCase();
                                                            const cleanBrand = String(item.brand || '').trim().toLowerCase();
                                                            const keyId = item.product_id || matched?.id;
                                                            const keyBrand = `${cleanName}|${cleanBrand}`;
                                                            const pastInfo = (keyId && partyRates[keyId]) || partyRates[keyBrand] || partyRates[cleanName];
                                                            const pastRate = item.last_party_rate ?? (pastInfo ? Number(pastInfo.rate) : null);

                                                            if (pastRate && pastRate > 0) {
                                                                const partyName = ledgers.find(l => l.id === partyLedgerId)?.name || 'this customer';
                                                                const vNum = item.last_party_vnum || pastInfo?.voucher_number;
                                                                const vDate = item.last_party_date || pastInfo?.voucher_date;
                                                                return (
                                                                    <span 
                                                                        className="text-[11px] font-mono flex items-center gap-1 bg-emerald-950/40 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded shadow-sm"
                                                                        title={`Last sold to ${partyName} at ₹${pastRate.toFixed(2)} on ${vDate || 'past invoice'}${vNum ? ` (#${vNum})` : ''}`}
                                                                    >
                                                                        <span className="text-emerald-500 font-sans text-[10px]">Party Rate:</span>
                                                                        <strong className="text-emerald-300">₹{pastRate.toFixed(2)}</strong>
                                                                        {Number(item.rate) !== pastRate && (
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => updateItem(gIndex, iIndex, 'rate', pastRate)}
                                                                                className="text-[10px] text-emerald-400 hover:text-emerald-300 ml-1 underline cursor-pointer"
                                                                                title="Click to reset to party's past sales rate"
                                                                            >
                                                                                Use Past
                                                                            </button>
                                                                        )}
                                                                    </span>
                                                                );
                                                            }
                                                            return null;
                                                        })()}

                                                        {/* Interactive Brand Switcher Dropdown */}
                                                        {(() => {
                                                            const cleanName = String(item.product_name || '').trim().toLowerCase();
                                                            const alphaVal = cleanName.replace(/[\s\-_/.]/g, '');
                                                            const sameNameProducts = products.filter((p: any) => 
                                                                (!group.category_id || p.category_id === group.category_id) &&
                                                                (p.name.toLowerCase() === cleanName || p.name.toLowerCase().replace(/[\s\-_/.]/g, '') === alphaVal)
                                                            );
                                                            const allCategoryBrands = Array.from(new Set(products
                                                                .filter((p: any) => !group.category_id || p.category_id === group.category_id)
                                                                .map((p: any) => p.brand)
                                                                .filter(Boolean)
                                                            ));
                                                            const isBrandOpen = openBrandDropdown === `${gIndex}-${iIndex}`;

                                                            return (
                                                                <div className="relative inline-block">
                                                                    <button
                                                                        type="button"
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            setOpenBrandDropdown(isBrandOpen ? null : `${gIndex}-${iIndex}`);
                                                                        }}
                                                                        className={`text-[10px] px-2 py-0.5 rounded border font-medium flex items-center gap-1 cursor-pointer transition-all ${
                                                                            sameNameProducts.length > 1
                                                                                ? 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 border-blue-500/50 shadow-sm shadow-blue-500/10'
                                                                                : item.brand
                                                                                ? 'bg-muted hover:bg-zinc-700 text-zinc-200 border-input'
                                                                                : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/30'
                                                                        }`}
                                                                        title="Click to select or change brand"
                                                                    >
                                                                        <span>Brand: <strong className="text-foreground">{item.brand || 'Select Brand'}</strong></span>
                                                                        {sameNameProducts.length > 1 && (
                                                                            <span className="text-[9px] bg-blue-500 text-foreground rounded-full px-1 font-mono">
                                                                                {sameNameProducts.length}
                                                                            </span>
                                                                        )}
                                                                        <ChevronDown className="w-3 h-3 text-blue-400" />
                                                                    </button>

                                                                    {isBrandOpen && (
                                                                        <div 
                                                                            className="absolute left-0 top-full mt-1 z-50 bg-zinc-950 border border-input rounded-xl shadow-2xl p-2 min-w-[240px] max-h-64 overflow-y-auto"
                                                                            onClick={(e) => e.stopPropagation()}
                                                                        >
                                                                            <div className="text-[10px] uppercase font-bold text-zinc-400 px-2 py-1 border-b border-border mb-1 flex items-center justify-between">
                                                                                <span>Brand for "{item.product_name}"</span>
                                                                                <span className="text-[9px] text-zinc-500">Auto-links Rate & Stock</span>
                                                                            </div>

                                                                            {sameNameProducts.length > 0 && (
                                                                                <div className="space-y-1 mb-2">
                                                                                    <div className="text-[9px] font-semibold text-blue-400 px-2 uppercase">Brand SKUs:</div>
                                                                                    {sameNameProducts.map((snp: any) => {
                                                                                        const snpMrp = parseFloat(snp.selling_price || 0);
                                                                                        const snpStock = Number(snp.stock_quantity ?? 0);
                                                                                        const isCurrent = (item.product_id && item.product_id === snp.id) || 
                                                                                                          (!item.product_id && item.brand?.toLowerCase() === snp.brand?.toLowerCase());
                                                                                        return (
                                                                                            <button
                                                                                                key={snp.id}
                                                                                                type="button"
                                                                                                onClick={() => {
                                                                                                    selectProduct(gIndex, iIndex, snp);
                                                                                                    setOpenBrandDropdown(null);
                                                                                                }}
                                                                                                className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between gap-2 hover:bg-zinc-800/90 cursor-pointer transition-colors ${
                                                                                                    isCurrent ? 'bg-blue-600/20 text-blue-300 font-bold border border-blue-500/40' : 'text-zinc-200'
                                                                                                }`}
                                                                                            >
                                                                                                <div className="flex items-center gap-1.5">
                                                                                                    <span className="font-semibold">{snp.brand || 'Unbranded'}</span>
                                                                                                    {isCurrent && <span className="text-[9px] bg-blue-500 text-foreground px-1 rounded">Active</span>}
                                                                                                </div>
                                                                                                <div className="text-[10px] text-right text-zinc-400">
                                                                                                    <div>MRP: ₹{snpMrp.toFixed(2)}</div>
                                                                                                    {(() => {
                                                                                                        const snpKeyBrand = `${(snp.name || '').trim().toLowerCase()}|${(snp.brand || '').trim().toLowerCase()}`;
                                                                                                        const snpPast = (snp.id && partyRates[snp.id]) || partyRates[snpKeyBrand];
                                                                                                        if (snpPast) {
                                                                                                            return <div className="text-emerald-400 font-bold">Party: ₹{Number(snpPast.rate).toFixed(2)}</div>;
                                                                                                        }
                                                                                                        return null;
                                                                                                    })()}
                                                                                                    <div className={snpStock > 0 ? 'text-emerald-400 font-mono' : 'text-rose-400 font-mono'}>
                                                                                                        {snpStock} {snp.unit || 'PCS'}
                                                                                                    </div>
                                                                                                </div>
                                                                                            </button>
                                                                                        );
                                                                                    })}
                                                                                </div>
                                                                            )}

                                                                            {/* All other catalog brands */}
                                                                            {allCategoryBrands.filter(b => !sameNameProducts.some((snp: any) => snp.brand?.toLowerCase() === b.toLowerCase())).length > 0 && (
                                                                                <div className="pt-1 border-t border-border/80 mb-2">
                                                                                    <div className="text-[9px] font-semibold text-zinc-500 px-2 mb-1 uppercase">Other Brands:</div>
                                                                                    <div className="flex flex-wrap gap-1 px-1">
                                                                                        {allCategoryBrands
                                                                                            .filter(b => !sameNameProducts.some((snp: any) => snp.brand?.toLowerCase() === b.toLowerCase()))
                                                                                            .map(b => (
                                                                                                <button
                                                                                                    key={b}
                                                                                                    type="button"
                                                                                                    onClick={() => {
                                                                                                        selectBrand(gIndex, iIndex, b);
                                                                                                        setOpenBrandDropdown(null);
                                                                                                    }}
                                                                                                    className="text-[10px] px-2 py-0.5 bg-muted/50 hover:bg-muted text-zinc-300 rounded border border-border hover:border-input cursor-pointer"
                                                                                                >
                                                                                                    {b}
                                                                                                </button>
                                                                                            ))}
                                                                                    </div>
                                                                                </div>
                                                                            )}

                                                                            {/* Custom Brand input */}
                                                                            <div className="pt-1.5 border-t border-border">
                                                                                <div className="text-[9px] font-semibold text-zinc-500 px-1 mb-1 uppercase">Custom Brand:</div>
                                                                                <div className="flex gap-1">
                                                                                    <input
                                                                                        type="text"
                                                                                        placeholder="Type brand name..."
                                                                                        defaultValue={item.brand}
                                                                                        onKeyDown={(e) => {
                                                                                            if (e.key === 'Enter') {
                                                                                                e.preventDefault();
                                                                                                selectBrand(gIndex, iIndex, (e.target as HTMLInputElement).value.trim());
                                                                                                setOpenBrandDropdown(null);
                                                                                            }
                                                                                        }}
                                                                                        className="w-full bg-muted/50 border border-input rounded px-2 py-1 text-xs text-foreground outline-none focus:border-blue-500"
                                                                                        id={`custom-brand-input-${gIndex}-${iIndex}`}
                                                                                    />
                                                                                    <button
                                                                                        type="button"
                                                                                        onClick={() => {
                                                                                            const el = document.getElementById(`custom-brand-input-${gIndex}-${iIndex}`) as HTMLInputElement;
                                                                                            if (el) {
                                                                                                selectBrand(gIndex, iIndex, el.value.trim());
                                                                                                setOpenBrandDropdown(null);
                                                                                            }
                                                                                        }}
                                                                                        className="bg-blue-600 hover:bg-blue-500 text-foreground text-[10px] px-2 py-1 rounded font-medium cursor-pointer"
                                                                                    >
                                                                                        Apply
                                                                                    </button>
                                                                                </div>
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })()}

                                                        {/* Available Stock Badge */}
                                                        {(() => {
                                                            const matched = products.find((p: any) => 
                                                                (item.product_id && p.id === item.product_id) || 
                                                                (p.name.toLowerCase() === String(item.product_name || '').trim().toLowerCase() && 
                                                                 (!item.brand || (p.brand || '').toLowerCase() === item.brand.toLowerCase()))
                                                            );
                                                            if (!matched) return null;
                                                            const availStock = Number(matched.stock_quantity ?? 0);
                                                            const isPositive = availStock > 0;
                                                            return (
                                                                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border font-medium flex items-center gap-1 ${
                                                                    isPositive 
                                                                        ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' 
                                                                        : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                                                                }`}>
                                                                    <span>Avail:</span>
                                                                    <strong>{availStock} {matched.unit || 'PCS'}</strong>
                                                                </span>
                                                            );
                                                        })()}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="p-2">
                                                <input 
                                                    type="number" 
                                                    step="1"
                                                    min="1" 
                                                    value={item.quantity} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'quantity', e.target.value)} 
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
                                                            <div className="text-xs text-amber-500 font-mono tabular-nums text-center font-medium mt-0.5" title={`Available stock: ${matched.stock_quantity ?? 0} ${matched.unit || 'PCS'}`}>
                                                                Max: {matched.stock_quantity ?? 0}
                                                            </div>
                                                        );
                                                    }
                                                    return null;
                                                })()}
                                            </td>
                                            <td className="p-2">
                                                <input 
                                                    type="number" 
                                                    step="0.01"
                                                    min="0" 
                                                    placeholder="0.00"
                                                    value={item.rate === 0 && !item.product_name ? '' : item.rate} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'rate', e.target.value)} 
                                                    className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-right text-sm font-mono tabular-nums font-semibold" 
                                                />
                                            </td>
                                            <td className="p-2">
                                                <input 
                                                    type="number" 
                                                    step="0.01"
                                                    min="0" 
                                                    max="100" 
                                                    value={item.discount_percent} 
                                                    onChange={e => updateItem(gIndex, iIndex, 'discount_percent', e.target.value)} 
                                                    className="w-full min-h-[34px] bg-background/50 border border-border/60 hover:border-input focus:border-primary focus:bg-background rounded-md px-2.5 py-1.5 outline-none text-foreground transition-all text-center text-sm font-mono tabular-nums font-semibold" 
                                                />
                                            </td>
                                            <td className="p-2 text-right font-bold text-foreground font-mono tabular-nums text-sm">
                                                ₹{taxable.toFixed(2)}
                                            </td>
                                            <td className="p-2 text-center">
                                                <button onClick={() => removeRow(gIndex, iIndex)} className="text-muted-foreground hover:text-destructive transition-colors p-1.5 rounded hover:bg-destructive/10 min-w-[32px] min-h-[32px] inline-flex items-center justify-center" title="Remove line item">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                                </button>
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                        <div className="p-3 bg-zinc-900/30 border-t border-border">
                            <button onClick={() => addRow(gIndex)} className="text-sm text-blue-500 hover:text-blue-400 font-medium flex items-center gap-1">
                                + Add item in {categories.find(c=>c.id===group.category_id)?.name || 'this category'}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t border-border bg-zinc-900/20">
                <button onClick={addCategoryGroup} className="text-sm text-foreground bg-muted hover:bg-zinc-700 border border-input px-4 py-2 rounded shadow transition-colors font-medium">
                    + Add Another Category Block
                </button>
            </div>
        </div>

        {/* Totals Section */}
        <div className="flex justify-end">
            <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-3">
                <div className="flex justify-between text-muted-foreground text-sm">
                    <span>Gross Total</span>
                    <span className="font-mono tabular-nums font-semibold text-foreground">₹{grossTotal.toFixed(2)}</span>
                </div>
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
                <div className="flex justify-between items-center text-muted-foreground text-sm">
                    <span>Cartage / Freight Outward</span>
                    <div className="flex items-center gap-1.5">
                        <span className="text-muted-foreground font-mono text-sm">₹</span>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={cartageAmount}
                            onChange={(e) => setCartageAmount(e.target.value)}
                            placeholder="0.00"
                            className="w-32 bg-background border border-border text-foreground text-right px-3 py-1.5 rounded-lg font-mono tabular-nums font-semibold text-sm focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                        />
                    </div>
                </div>
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

      </div>
    </DashboardLayout>
  );
}
