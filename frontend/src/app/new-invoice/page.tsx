"use client"
import { API_BASE_URL } from '@/utils/api';
import { useState, useEffect } from 'react';
import axios from 'axios';
import { useRouter } from 'next/navigation';
import { ThemeToggle } from '@/components/ThemeToggle';
import { useToast } from '@/context/ToastContext';

export default function NewInvoice() {
  const router = useRouter();
  const { toast } = useToast();
  const [companies, setCompanies] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  
  const [invoiceType, setInvoiceType] = useState('Sales');
  const [selectedCompany, setSelectedCompany] = useState('');
  
  // New Company form
  const [showNewCompany, setShowNewCompany] = useState(false);
  const [newCompData, setNewCompData] = useState({ name: '', gstin: '', state_code: '', is_owner: false });
  
  // Invoice Items
  const [items, setItems] = useState<any[]>([]);
  
  // New Product form (modal/inline)
  const [showNewProduct, setShowNewProduct] = useState(false);
  const [newProdData, setNewProdData] = useState({ name: '', sku: '', base_price: '', gst_rate: '', hsn_code: '', stock_quantity: 0 });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [compRes, prodRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/companies/`),
        axios.get(`${API_BASE_URL}/api/products/`)
      ]);
      setCompanies(compRes.data);
      setProducts(prodRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateCompany = async () => {
    try {
      const res = await axios.post(`${API_BASE_URL}/api/companies/`, newCompData);
      setCompanies([...companies, res.data]);
      setSelectedCompany(res.data.id);
      setShowNewCompany(false);
      setNewCompData({ name: '', gstin: '', state_code: '', is_owner: false });
      toast.success('Company created successfully');
    } catch (e: any) {
      console.error(e);
      toast.error('Error creating company', e.response?.data?.error || e.message);
    }
  };

  const handleCreateProduct = async () => {
    try {
      const res = await axios.post(`${API_BASE_URL}/api/products/`, newProdData);
      setProducts([...products, res.data]);
      setShowNewProduct(false);
      setNewProdData({ name: '', sku: '', base_price: '', gst_rate: '', hsn_code: '', stock_quantity: 0 });
      toast.success('Product created successfully');
    } catch (e: any) {
      console.error(e);
      toast.error('Error creating product', e.response?.data?.error || e.message);
    }
  };

  const handleAddItem = () => {
    setItems([...items, { product: '', quantity: 1, unit_price: 0 }]);
  };

  const updateItem = (index: number, field: string, value: any) => {
    const newItems = [...items];
    newItems[index][field] = value;
    if (field === 'product') {
      const prod = products.find(p => p.id == value);
      if (prod) {
        newItems[index].unit_price = prod.base_price;
      }
    }
    setItems(newItems);
  };

  const handleSubmit = async () => {
    if (!selectedCompany || items.length === 0) {
      toast.warning('Incomplete Invoice', 'Please select a company and add items');
      return;
    }
    try {
      const payload = {
        company: selectedCompany,
        type: invoiceType,
        items: items.map(i => ({ product: i.product, quantity: i.quantity, unit_price: i.unit_price }))
      };
      await axios.post(`${API_BASE_URL}/api/invoices/`, payload);
      toast.success('Invoice created successfully!');
      router.push('/');
    } catch (e: any) {
      console.error(e);
      toast.error('Error creating invoice', e.response?.data?.error || e.message);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 bg-background text-foreground transition-colors duration-200">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Create Invoice</h1>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <button onClick={() => router.push('/')} className="text-blue-600 dark:text-blue-400 hover:underline">
            Back to Dashboard
          </button>
        </div>
      </div>

      <div className="bg-card text-card-foreground p-6 rounded-xl shadow-sm border border-border space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">Invoice Type</label>
            <select 
              className="w-full bg-background border border-border p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-shadow" 
              value={invoiceType} 
              onChange={e => setInvoiceType(e.target.value)}
            >
              <option value="Sales">Sales</option>
              <option value="Purchase">Purchase</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">Company / Party</label>
            <div className="flex gap-2">
              <select 
                className="w-full bg-background border border-border p-2.5 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-shadow" 
                value={selectedCompany} 
                onChange={e => setSelectedCompany(e.target.value)}
              >
                <option value="">Select a company...</option>
                {companies.filter(c => !c.is_owner).map(c => (
                  <option key={c.id} value={c.id}>{c.name} ({c.gstin})</option>
                ))}
              </select>
              <button 
                onClick={() => setShowNewCompany(!showNewCompany)} 
                className="bg-blue-50 hover:bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:hover:bg-blue-800/40 dark:text-blue-400 px-4 rounded-lg border border-blue-200 dark:border-blue-800 transition-colors font-medium flex items-center justify-center"
                title="Add New Party"
              >
                +
              </button>
            </div>
          </div>
        </div>

        {showNewCompany && (
          <div className="bg-gray-50 dark:bg-zinc-800/50 p-5 border border-border rounded-lg space-y-3 mt-4 animate-in fade-in slide-in-from-top-2">
            <h3 className="font-bold text-gray-800 dark:text-gray-200">Add New Party</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input placeholder="Name" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newCompData.name} onChange={e => setNewCompData({...newCompData, name: e.target.value})} />
              <input placeholder="GSTIN" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newCompData.gstin} onChange={e => setNewCompData({...newCompData, gstin: e.target.value})} />
              <input placeholder="State Code (e.g. 09)" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newCompData.state_code} onChange={e => setNewCompData({...newCompData, state_code: e.target.value})} />
            </div>
            <button onClick={handleCreateCompany} className="bg-blue-600 text-white hover:bg-blue-700 px-4 py-2 rounded-md text-sm font-medium transition-colors">Save Party</button>
          </div>
        )}
      </div>

      <div className="bg-card text-card-foreground p-6 rounded-xl shadow-sm border border-border space-y-4">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Items</h2>
          <button 
            onClick={() => setShowNewProduct(!showNewProduct)} 
            className="bg-blue-50 hover:bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:hover:bg-blue-800/40 dark:text-blue-400 px-3 py-1.5 rounded-md border border-blue-200 dark:border-blue-800 transition-colors font-medium text-sm"
          >
            + New Product
          </button>
        </div>

        {showNewProduct && (
          <div className="bg-gray-50 dark:bg-zinc-800/50 p-5 border border-border rounded-lg space-y-3 animate-in fade-in slide-in-from-top-2">
            <h3 className="font-bold text-gray-800 dark:text-gray-200">Add New Product</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              <input placeholder="Name" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.name} onChange={e => setNewProdData({...newProdData, name: e.target.value})} />
              <input placeholder="SKU" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.sku} onChange={e => setNewProdData({...newProdData, sku: e.target.value})} />
              <input placeholder="Base Price" type="number" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.base_price} onChange={e => setNewProdData({...newProdData, base_price: e.target.value})} />
              <input placeholder="GST Rate (%)" type="number" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.gst_rate} onChange={e => setNewProdData({...newProdData, gst_rate: e.target.value})} />
              <input placeholder="HSN Code" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.hsn_code} onChange={e => setNewProdData({...newProdData, hsn_code: e.target.value})} />
              <input placeholder="Initial Stock" type="number" className="bg-background border border-border p-2 rounded-md focus:ring-2 focus:ring-blue-500 outline-none" value={newProdData.stock_quantity} onChange={e => setNewProdData({...newProdData, stock_quantity: parseInt(e.target.value)})} />
            </div>
            <button onClick={handleCreateProduct} className="bg-blue-600 text-white hover:bg-blue-700 px-4 py-2 rounded-md text-sm font-medium transition-colors">Save Product</button>
          </div>
        )}

        <div className="space-y-3">
          {items.map((item, idx) => (
            <div key={idx} className="flex flex-col sm:flex-row gap-3 items-center bg-gray-50/50 dark:bg-zinc-800/30 p-3 rounded-lg border border-border/50">
              <select 
                className="bg-background border border-border p-2 rounded-md flex-1 w-full focus:ring-2 focus:ring-blue-500 outline-none" 
                value={item.product} 
                onChange={e => updateItem(idx, 'product', e.target.value)}
              >
                <option value="">Select product...</option>
                {products.map(p => (
                  <option key={p.id} value={p.id}>{p.name} (HSN: {p.hsn_code} - GST: {p.gst_rate}%)</option>
                ))}
              </select>
              <div className="flex gap-3 w-full sm:w-auto">
                <input type="number" placeholder="Qty" className="bg-background border border-border p-2 rounded-md w-24 focus:ring-2 focus:ring-blue-500 outline-none" value={item.quantity} onChange={e => updateItem(idx, 'quantity', e.target.value)} />
                <input type="number" placeholder="Unit Price" className="bg-background border border-border p-2 rounded-md w-32 focus:ring-2 focus:ring-blue-500 outline-none" value={item.unit_price} onChange={e => updateItem(idx, 'unit_price', e.target.value)} />
                <button onClick={() => setItems(items.filter((_, i) => i !== idx))} className="text-red-500 hover:text-red-700 dark:hover:text-red-400 font-bold p-2 bg-red-50 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/40 rounded-md transition-colors">
                  X
                </button>
              </div>
            </div>
          ))}
          {items.length === 0 && (
            <div className="text-center py-6 text-gray-500 dark:text-gray-400 text-sm">
              No items added to the invoice yet.
            </div>
          )}
        </div>
        <button 
          onClick={handleAddItem} 
          className="w-full bg-gray-50 hover:bg-gray-100 dark:bg-zinc-800 dark:hover:bg-zinc-700 border border-dashed border-border text-gray-600 dark:text-gray-300 px-4 py-3 rounded-lg transition-colors font-medium mt-2"
        >
          + Add Line Item
        </button>
      </div>

      <div className="flex justify-end pt-4">
        <button 
          onClick={handleSubmit} 
          className="bg-green-600 text-white px-8 py-3 rounded-lg font-bold shadow hover:bg-green-700 transition-colors"
        >
          Generate Invoice
        </button>
      </div>
    </div>
  );
}
