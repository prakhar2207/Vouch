import React from 'react';
import { AlertTriangle, Trash2, Info } from 'lucide-react';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm?: (() => any) | null;
  title: string;
  description: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'info';
  isLoading?: boolean;
}

export default function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger',
  isLoading = false
}: ConfirmModalProps) {
  if (!isOpen) return null;

  const getVariantStyles = () => {
    switch (variant) {
      case 'danger':
        return {
          icon: <Trash2 className="w-6 h-6 text-rose-500" />,
          iconBg: 'bg-rose-500/10 border border-rose-500/20',
          btnClass: 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/20'
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="w-6 h-6 text-amber-500" />,
          iconBg: 'bg-amber-500/10 border border-amber-500/20',
          btnClass: 'bg-amber-600 hover:bg-amber-500 text-white shadow-lg shadow-amber-600/20'
        };
      case 'info':
        return {
          icon: <Info className="w-6 h-6 text-blue-500" />,
          iconBg: 'bg-blue-500/10 border border-blue-500/20',
          btnClass: 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/20'
        };
    }
  };

  const styles = getVariantStyles();

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200">
      <div 
        className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className={`w-12 h-12 rounded-2xl ${styles.iconBg} flex items-center justify-center mb-4`}>
            {styles.icon}
          </div>
          <h3 className="text-lg font-bold text-foreground mb-2 tracking-tight">{title}</h3>
          <div className="text-muted-foreground text-sm leading-relaxed">
            {description}
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 bg-muted/30 border-t border-border/50">
          <button 
            type="button"
            disabled={isLoading}
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl text-xs font-bold text-foreground bg-muted hover:bg-muted/80 border border-border/60 transition-colors cursor-pointer disabled:opacity-50"
          >
            {cancelText}
          </button>
          <button 
            type="button"
            disabled={isLoading}
            onClick={() => onConfirm?.()}
            className={`flex-1 px-4 py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 ${styles.btnClass}`}
          >
            {isLoading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Processing...</span>
              </>
            ) : (
              confirmText
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
