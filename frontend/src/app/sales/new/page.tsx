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
import { ChevronDown } from 'lucide-react';

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
  
  const [categories, setCategories] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [activeSearch, setActiveSearch] = useState<string | null>(null);
  const [openBrandDropdown, setOpenBrandDropdown] = useState<string | null>(null);
  const [groupedItems, setGroupedItems] = useState<any[]>([
    { category_id: '', hsn_code: '', gst_rate: 18, items: [ { product_name: '', product_id: '', brand: '', unit: 'PCS', quantity: 1, rate: 0, discount_percent: 0 } ] }
  ]);

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

      const [ledgersRes, catsRes, prodsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/v1/ledgers/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/categories/${cId}/`, { headers }),
        axios.get(`${API_BASE_URL}/api/v1/inventory/products/${cId}/`, { headers }).catch(() => ({ data: { data: [] } }))
      ]);
      const ledgerList = ledgersRes.data.data || [];
      setLedgers(ledgerList);
      setCategories(catsRes.data.data || []);
      setProducts(prodsRes.data?.data || []);
      
      const party = ledgerList.find((l:any) => l.name.includes('Customer') || l.group.includes('Debtors'));
      
      // Default to generic 'Sales Account' if mapping is disabled
      const genericSales = ledgerList.find((l:any) => l.name === 'Sales Account' || l.name === 'Local Sales') || ledgerList.find((l:any) => l.name.toLowerCase().includes('sales'));
      const sales = isMappingEnabled 
          ? ledgerList.find((l:any) => l.name.toLowerCase().includes('sales')) 
          : genericSales;
          
      const cgst = ledgerList.find((l:any) => l.name === 'CGST' || l.name === 'Output CGST' || l.name.toLowerCase().includes('cgst'));
      const sgst = ledgerList.find((l:any) => l.name === 'SGST' || l.name === 'Output SGST' || l.name.toLowerCase().includes('sgst'));
      const igst = ledgerList.find((l:any) => l.name === 'IGST' || l.name === 'Output IGST' || l.name.toLowerCase().includes('igst'));
      
      if (party) {
        setPartyLedgerId(party.id);
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
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePartyChange = (selectedId: string) => {
    setPartyLedgerId(selectedId);
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

  const handleSave = async () => {
    if (!partyLedgerId || !salesLedgerId) {
      toast.warning("Please select Party and Sales ledgers!");
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
        voucher_number: enableManualInvoice ? invoiceNumber : undefined,
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
      
      const res = await axios.post(`${API_BASE_URL}/api/v1/accounting/sales-invoice/`, payload, { headers });
      toast.success(`Sales Invoice generated!`, `Voucher: ${res.data.voucher_number}`);
      router.push('/sales');
      router.refresh();
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
    
    const mrp = parseFloat(prod.selling_price) || 0;
    if (mrp > 0) {
      item.rate = mrp;
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
        const mrp = parseFloat(match.selling_price) || 0;
        if (mrp > 0) {
          item.rate = mrp;
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
          const mrp = parseFloat(match.selling_price) || 0;
          if (mrp > 0) {
            item.rate = mrp;
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
  const unroundedGrandTotal = allItems.reduce((sum, item) => {
    const gross = Number(item.quantity) * Number(item.rate);
    const discount = gross * (Number(item.discount_percent)/100);
    const taxable = gross - discount;
    return sum + taxable + (taxable * (Number(item.gst_rate)/100));
  }, 0);

  let grandTotal = 0;
  let roundOff = 0;
  if (unroundedGrandTotal > 0) {
    const integerPart = Math.floor(unroundedGrandTotal);
    const decimalPart = Math.round((unroundedGrandTotal - integerPart) * 100) / 100;
    grandTotal = decimalPart < 0.5 ? integerPart : integerPart + 1;
    roundOff = Math.round((grandTotal - unroundedGrandTotal) * 100) / 100;
  }

  const isInterState = Boolean(selectedParty?.state_code && companyStateCode && selectedParty.state_code !== companyStateCode);

  if (loading) return <DashboardLayout><div className="flex items-center justify-center h-full text-gray-500">Loading invoice form...</div></DashboardLayout>;

  let missingFields = [];
  if (company) {
    if (!company.proprietor_name) missingFields.push("Proprietor Name");
    if (!company.proprietor_phone) missingFields.push("Proprietor Phone");
    if (!company.proprietor_signature) missingFields.push("Digital Signature");
  }

  if (missingFields.length > 0) {
    return (
      <DashboardLayout>
        <div className="max-w-2xl mx-auto mt-20 p-8 bg-card border border-border rounded-xl shadow-lg text-center">
          <div className="w-16 h-16 bg-amber-500/10 text-amber-500 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Proprietor Details Required</h2>
          <p className="text-gray-400 mb-4">
            You must complete your firm's profile before you can generate invoices. The following details are missing:
          </p>
          <ul className="text-amber-500 font-medium mb-8 flex flex-col items-center gap-1">
            {missingFields.map(f => <li key={f}>• {f}</li>)}
          </ul>
          <Link href="/settings" className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-bold shadow-lg transition-colors">
            Go to Profile Settings
          </Link>
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
            <Link href="/sales" className="text-gray-400 hover:text-white transition-colors p-1">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            </Link>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">New Sales Invoice</h1>
              {activeFY && (
                <div className="text-xs text-gray-400 mt-0.5">
                  Financial Year: <span className="font-semibold text-white">{activeFY.name}</span> ({activeFY.start_date} ~ {activeFY.end_date})
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
                : 'bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50'
            }`}
          >
            {saving ? 'Posting...' : isReadOnly ? 'Period Closed (Read-Only)' : 'Post Invoice'}
          </button>
        </div>
        
        {/* Billing Details Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-200">Billing Details</h2>
            {seqPreview && (
              <span className="text-xs font-mono font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30 px-2.5 py-1 rounded-lg">
                Next Serial: {seqPreview} (GST Rule 46b)
              </span>
            )}
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6 pb-6 border-b border-zinc-800">
            {enableManualInvoice && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Invoice Number</label>
                <input
                  type="text"
                  value={invoiceNumber}
                  onChange={e => setInvoiceNumber(e.target.value)}
                  placeholder={seqPreview ? `Auto: ${seqPreview}` : "e.g. INV-001"}
                  className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all font-mono"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                Invoice Date {activeFY && <span className="text-zinc-500 font-normal font-mono">({activeFY.code})</span>}
              </label>
              <input
                type="date"
                value={invoiceDate}
                min={activeFY?.start_date}
                max={activeFY?.end_date}
                onChange={e => setInvoiceDate(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all font-mono"
              />
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-sm font-medium text-gray-400">Party (Customer)</label>
                <Link href="/sales/customers/new" className="text-xs text-blue-500 hover:text-blue-400">+ Add New Customer</Link>
              </div>
              <select
                value={partyLedgerId}
                onChange={e => handlePartyChange(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
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
                    <span>Customer Discount: <strong className="text-white font-mono">{Number(selectedParty.discount_percent)}%</strong></span>
                  </div>
                  <span className="text-[11px] text-zinc-400">Applied automatically • Editable below</span>
                </div>
              )}
            </div>
            {enableLedgerMapping && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Sales Ledger</label>
                <select value={salesLedgerId} onChange={e => setSalesLedgerId(e.target.value)} className="w-full bg-zinc-900 border border-zinc-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                  <option value="">-- Select Sales Ledger --</option>
                  {ledgers.filter(l => l.group.includes('Income') || l.name.includes('Sales')).map(l => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Ad-hoc Buyer Details Subform for Cash / Walk-in Customers */}
          <div className="mt-5 pt-4 border-t border-zinc-800">
            <div 
              className="flex items-center justify-between cursor-pointer select-none bg-zinc-900/40 hover:bg-zinc-900/80 p-3 rounded-lg border border-zinc-800/80 transition-all"
              onClick={() => setShowBuyerDetails(!showBuyerDetails)}
            >
              <div className="flex items-center gap-2.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                <span className="text-sm font-semibold text-zinc-200">Buyer Details (Optional — Cash / Counter Walk-in)</span>
                <span className="text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded font-mono">
                  Prints on bill without creating a Debtor
                </span>
              </div>
              <span className="text-xs text-zinc-400 hover:text-white font-medium">
                {showBuyerDetails ? '▲ Hide Details' : '▼ Enter Walk-in Details'}
              </span>
            </div>

            {showBuyerDetails && (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-zinc-900/40 border border-zinc-800/60 rounded-xl">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Walk-in Buyer Name</label>
                  <input
                    type="text"
                    value={buyerName}
                    onChange={e => setBuyerName(e.target.value)}
                    placeholder="e.g. Ramesh Kumar"
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Mobile / Phone</label>
                  <input
                    type="text"
                    value={buyerPhone}
                    onChange={e => setBuyerPhone(e.target.value)}
                    placeholder="e.g. 9876543210"
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">GSTIN (Optional)</label>
                  <input
                    type="text"
                    value={buyerGstin}
                    onChange={e => setBuyerGstin(e.target.value.toUpperCase())}
                    placeholder="Unregistered or 15-digit GSTIN"
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none uppercase font-mono placeholder:text-zinc-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">Billing Address / City</label>
                  <input
                    type="text"
                    value={buyerAddress}
                    onChange={e => setBuyerAddress(e.target.value)}
                    placeholder="City, State"
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm p-2.5 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none placeholder:text-zinc-600"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Line Items Card */}
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-border flex justify-between items-center">
                <h2 className="text-lg font-semibold text-gray-200">Line Items by Category</h2>
                <span className="text-xs text-blue-400 bg-blue-400/10 px-2 py-1 rounded border border-blue-400/20">Auto-Creates & Inherits Tax</span>
            </div>
            
            <div className="p-2 space-y-6">
                {groupedItems.map((group, gIndex) => (
                    <div key={gIndex} className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/30">
                        <div className="p-3 sm:p-4 bg-zinc-900/80 border-b border-zinc-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="flex-1 max-w-md flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                                <label className="text-sm font-medium text-gray-400 whitespace-nowrap">Category:</label>
                                <select 
                                    value={group.category_id} 
                                    onChange={(e) => updateGroup(gIndex, 'category_id', e.target.value)}
                                    className="w-full bg-zinc-800 border border-zinc-700 text-white p-2 rounded focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                                >
                                    <option value="">-- Select Category --</option>
                                    {categories.map(c => (
                                         <option key={c.id} value={c.id}>{c.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2 sm:gap-4 text-sm text-gray-500">
                                <span className="text-xs sm:text-sm">Default HSN: <strong className="text-gray-300">{group.hsn_code || 'N/A'}</strong></span>
                                {isInterState ? (
                                    <span className="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20 text-xs font-medium">
                                        IGST: {group.gst_rate}%
                                    </span>
                                ) : (
                                    <div className="flex gap-2">
                                        <span className="bg-zinc-800 text-gray-300 px-2 py-0.5 rounded border border-zinc-700 text-xs font-medium">CGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                        <span className="bg-zinc-800 text-gray-300 px-2 py-0.5 rounded border border-zinc-700 text-xs font-medium">SGST: {(Number(group.gst_rate)/2).toFixed(1)}%</span>
                                    </div>
                                )}
                                <button onClick={() => removeCategoryGroup(gIndex)} className="text-red-500 hover:text-red-400 ml-auto sm:ml-4 p-1" title="Delete category group">
                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                </button>
                            </div>
                        </div>
                        
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[550px] text-left border-collapse">
                                <thead className="bg-zinc-900/40 text-gray-400 text-xs uppercase tracking-wider">
                                    <tr>
                                        <th className="p-3 font-medium">Product Name</th>
                                        <th className="p-3 font-medium w-24 text-center">Qty</th>
                                        <th className="p-3 font-medium w-36 text-right">Rate / MRP (₹)</th>
                                        <th className="p-3 font-medium w-28 text-center">
                                            <span>Disc %</span>
                                            {currentPartyDiscount > 0 && (
                                                <span className="block text-[10px] text-blue-400 lowercase font-normal">({currentPartyDiscount}% party)</span>
                                            )}
                                        </th>
                                        <th className="p-3 font-medium w-32 text-right">Amount</th>
                                        <th className="p-3 w-12"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-zinc-800/50">
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
                                                        className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-sm font-medium" 
                                                    />

                                                    {/* Autocomplete Dropdown Popover */}
                                                    {activeSearch === `${gIndex}-${iIndex}` && (
                                                        <div 
                                                            className="absolute left-0 top-full mt-1 z-50 w-full min-w-[340px] max-w-[480px] bg-zinc-950 border border-zinc-700 rounded-xl shadow-2xl overflow-hidden max-h-64 overflow-y-auto"
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
                                                                                            <span className="font-semibold text-white text-sm truncate">{p.name}</span>
                                                                                            {p.brand ? (
                                                                                                <span className="text-[10px] px-1.5 py-0.2 rounded font-bold uppercase bg-blue-500/20 text-blue-300 border border-blue-500/30">
                                                                                                    {p.brand}
                                                                                                </span>
                                                                                            ) : (
                                                                                                <span className="text-[10px] px-1.5 py-0.2 rounded font-medium text-zinc-500 bg-zinc-900 border border-zinc-800">
                                                                                                    Unbranded
                                                                                                </span>
                                                                                            )}
                                                                                        </div>
                                                                                        <div className="text-[11px] text-zinc-400 truncate mt-0.5">
                                                                                            {p.category} {p.sku ? `• SKU: ${p.sku}` : ''}
                                                                                        </div>
                                                                                    </div>
                                                                                    <div className="text-right whitespace-nowrap pl-2">
                                                                                        <div className="text-xs font-mono font-bold text-white">
                                                                                            {mrp > 0 ? `₹${mrp.toFixed(2)}` : 'No MRP'}
                                                                                        </div>
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
                                                        {Number(item.rate) > 0 ? (
                                                            <span className="text-[11px] text-blue-400 font-mono flex items-center gap-1">
                                                                <span>MRP:</span>
                                                                <strong className="text-white">₹{Number(item.rate).toFixed(2)}</strong>
                                                            </span>
                                                        ) : (
                                                            <span className="text-[11px] text-zinc-500 italic">No MRP stored</span>
                                                        )}

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
                                                                                ? 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border-zinc-700'
                                                                                : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/30'
                                                                        }`}
                                                                        title="Click to select or change brand"
                                                                    >
                                                                        <span>Brand: <strong className="text-white">{item.brand || 'Select Brand'}</strong></span>
                                                                        {sameNameProducts.length > 1 && (
                                                                            <span className="text-[9px] bg-blue-500 text-white rounded-full px-1 font-mono">
                                                                                {sameNameProducts.length}
                                                                            </span>
                                                                        )}
                                                                        <ChevronDown className="w-3 h-3 text-blue-400" />
                                                                    </button>

                                                                    {isBrandOpen && (
                                                                        <div 
                                                                            className="absolute left-0 top-full mt-1 z-50 bg-zinc-950 border border-zinc-700 rounded-xl shadow-2xl p-2 min-w-[240px] max-h-64 overflow-y-auto"
                                                                            onClick={(e) => e.stopPropagation()}
                                                                        >
                                                                            <div className="text-[10px] uppercase font-bold text-zinc-400 px-2 py-1 border-b border-zinc-800 mb-1 flex items-center justify-between">
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
                                                                                                    {isCurrent && <span className="text-[9px] bg-blue-500 text-white px-1 rounded">Active</span>}
                                                                                                </div>
                                                                                                <div className="text-[10px] text-right text-zinc-400">
                                                                                                    <div>MRP: ₹{snpMrp.toFixed(2)}</div>
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
                                                                                <div className="pt-1 border-t border-zinc-800/80 mb-2">
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
                                                                                                    className="text-[10px] px-2 py-0.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 rounded border border-zinc-800 hover:border-zinc-700 cursor-pointer"
                                                                                                >
                                                                                                    {b}
                                                                                                </button>
                                                                                            ))}
                                                                                    </div>
                                                                                </div>
                                                                            )}

                                                                            {/* Custom Brand input */}
                                                                            <div className="pt-1.5 border-t border-zinc-800">
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
                                                                                        className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-white outline-none focus:border-blue-500"
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
                                                                                        className="bg-blue-600 hover:bg-blue-500 text-white text-[10px] px-2 py-1 rounded font-medium cursor-pointer"
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
                                                    className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-center text-sm font-medium" 
                                                />
                                                {(() => {
                                                    const cleanName = String(item.product_name || '').trim().toLowerCase();
                                                    const matched = products.find((p: any) => 
                                                        (item.product_id && p.id === item.product_id) || 
                                                        p.name.toLowerCase() === cleanName
                                                    );
                                                    if (matched && Number(matched.stock_quantity ?? 0) < Number(item.quantity)) {
                                                        return (
                                                            <div className="text-[10px] text-amber-400 font-mono text-center font-medium mt-0.5" title={`Available stock: ${matched.stock_quantity ?? 0} ${matched.unit || 'PCS'}`}>
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
                                                    className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-right text-sm font-mono" 
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
                                                    className="w-full bg-transparent border border-transparent hover:border-zinc-700 focus:border-blue-500 rounded p-1.5 outline-none text-white transition-all text-center text-sm font-mono" 
                                                />
                                            </td>
                                            <td className="p-2 text-right font-medium text-gray-200 font-mono">
                                                ₹{taxable.toFixed(2)}
                                            </td>
                                            <td className="p-2 text-center">
                                                <button onClick={() => removeRow(gIndex, iIndex)} className="text-zinc-600 hover:text-red-400 transition-colors p-1" title="Remove line item">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                                                </button>
                                            </td>
                                        </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                        <div className="p-3 bg-zinc-900/30 border-t border-zinc-800">
                            <button onClick={() => addRow(gIndex)} className="text-sm text-blue-500 hover:text-blue-400 font-medium flex items-center gap-1">
                                + Add item in {categories.find(c=>c.id===group.category_id)?.name || 'this category'}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
            
            <div className="p-4 border-t border-border bg-zinc-900/20">
                <button onClick={addCategoryGroup} className="text-sm text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 px-4 py-2 rounded shadow transition-colors font-medium">
                    + Add Another Category Block
                </button>
            </div>
        </div>

        {/* Totals Section */}
        <div className="flex justify-end">
            <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-3">
                <div className="flex justify-between text-gray-400">
                    <span>Gross Total</span>
                    <span>₹{grossTotal.toFixed(2)}</span>
                </div>
                {isInterState ? (
                    <div className="flex justify-between text-blue-400">
                        <span>IGST</span>
                        <span>₹{totalTax.toFixed(2)}</span>
                    </div>
                ) : (
                    <>
                        <div className="flex justify-between text-gray-400">
                            <span>CGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-gray-400">
                            <span>SGST</span>
                            <span>₹{(totalTax / 2).toFixed(2)}</span>
                        </div>
                    </>
                )}
                <div className="flex justify-between text-gray-400">
                    <span>Round Off</span>
                    <span className={roundOff < 0 ? "text-emerald-400 font-mono font-medium" : roundOff > 0 ? "text-amber-400 font-mono font-medium" : "text-gray-400 font-mono"}>
                        {roundOff > 0 ? `+₹${roundOff.toFixed(2)}` : roundOff < 0 ? `-₹${Math.abs(roundOff).toFixed(2)}` : `₹0.00`}
                    </span>
                </div>
                <div className="border-t border-zinc-700 pt-3 flex justify-between text-xl font-bold text-white">
                    <span>Grand Total</span>
                    <span className="font-mono">₹{grandTotal.toFixed(2)}</span>
                </div>
            </div>
        </div>

      </div>
    </DashboardLayout>
  );
}
