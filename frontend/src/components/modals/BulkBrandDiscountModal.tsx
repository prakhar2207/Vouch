import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useToast } from '@/context/ToastContext';
import { getAccessToken } from '@/utils/auth';
import { Percent } from 'lucide-react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface BulkBrandDiscountModalProps {
  isOpen: boolean;
  onClose: () => void;
  categoryId: string;
  companyId: string;
  existingBrands: string[];
  onSuccess: () => void;
}

export default function BulkBrandDiscountModal({
  isOpen,
  onClose,
  categoryId,
  companyId,
  existingBrands,
  onSuccess
}: BulkBrandDiscountModalProps) {
  const [selectedBrand, setSelectedBrand] = useState('');
  const [discountPercent, setDiscountPercent] = useState<number>(0);
  const [isUpdating, setIsUpdating] = useState(false);
  const { toast } = useToast();

  // Sync selectedBrand whenever the brands list changes or modal opens
  useEffect(() => {
    if (isOpen && existingBrands.length > 0) {
      setSelectedBrand(prev => prev && existingBrands.includes(prev) ? prev : existingBrands[0]);
    }
  }, [isOpen, existingBrands]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!selectedBrand) {
      toast.error('Please select a brand');
      return;
    }
    
    setIsUpdating(true);
    try {
      const token = getAccessToken();
      const headers = { Authorization: `Bearer ${token}` };
      
      const res = await axios.post(
        `${API_BASE_URL}/api/v1/inventory/brand-discount-update/${companyId}/`,
        {
          category_id: categoryId,
          brand: selectedBrand,
          discount_percent: discountPercent
        },
        { headers }
      );
      
      if (res.data.success) {
        toast.success(res.data.message || 'Brand discount updated successfully!');
        onSuccess();
        onClose();
      } else {
        toast.error('Failed to update', res.data.error);
      }
    } catch (err: any) {
      toast.error('Update failed', err.response?.data?.error || err.message);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200">
      <div 
        className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}
      >
        <div className="p-5 border-b border-border/60 bg-muted/20 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Percent className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-foreground">Bulk Brand Discount</h3>
            <p className="text-xs text-muted-foreground">Update purchase price for a whole brand</p>
          </div>
        </div>
        
        <div className="p-5 space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Select Brand</label>
            <select
              value={selectedBrand}
              onChange={e => setSelectedBrand(e.target.value)}
              className="w-full bg-background border border-border text-foreground rounded-xl px-3 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all cursor-pointer"
            >
              {existingBrands.map(b => (
                <option key={b} value={b} className="bg-card text-foreground">{b}</option>
              ))}
            </select>
          </div>
          
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Discount from MRP (%)</label>
            <div className="relative">
              <input
                type="number"
                step="0.01"
                value={discountPercent}
                onChange={e => setDiscountPercent(parseFloat(e.target.value) || 0)}
                className="w-full bg-background border border-border text-blue-600 dark:text-blue-400 font-bold font-mono rounded-xl pl-3 pr-8 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground font-bold text-xs">%</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Purchase Price = MRP × (1 - {discountPercent}%)
            </p>
          </div>
        </div>
        
        <div className="p-4 bg-muted/30 border-t border-border/60 flex items-center gap-3">
          <button
            onClick={onClose}
            disabled={isUpdating}
            className="flex-1 px-4 py-2.5 rounded-xl text-xs font-semibold text-foreground bg-muted hover:bg-muted/80 border border-border/60 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isUpdating}
            className="flex-1 px-4 py-2.5 rounded-xl text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-600/20 transition-all disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
          >
            {isUpdating ? 'Updating...' : 'Apply Update'}
          </button>
        </div>
      </div>
    </div>
  );
}
