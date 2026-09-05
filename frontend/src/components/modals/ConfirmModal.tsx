import React from 'react';
import { AlertTriangle, Trash2, Info } from 'lucide-react';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning' | 'info';
}

export default function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger'
}: ConfirmModalProps) {
  if (!isOpen) return null;

  const getVariantStyles = () => {
    switch (variant) {
      case 'danger':
        return {
          icon: <Trash2 className="w-6 h-6 text-rose-500" />,
          iconBg: 'bg-rose-500/10',
          btnClass: 'bg-rose-600 hover:bg-rose-700 text-white'
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="w-6 h-6 text-amber-500" />,
          iconBg: 'bg-amber-500/10',
          btnClass: 'bg-amber-600 hover:bg-amber-700 text-white'
        };
      case 'info':
        return {
          icon: <Info className="w-6 h-6 text-blue-500" />,
          iconBg: 'bg-blue-500/10',
          btnClass: 'bg-blue-600 hover:bg-blue-700 text-white'
        };
    }
  };

  const styles = getVariantStyles();

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className={`w-12 h-12 rounded-full ${styles.iconBg} flex items-center justify-center mb-4`}>
            {styles.icon}
          </div>
          <h3 className="text-xl font-bold text-white mb-2">{title}</h3>
          <p className="text-zinc-400 text-sm leading-relaxed">
            {description}
          </p>
        </div>
        <div className="flex items-center gap-3 p-4 bg-zinc-950 border-t border-zinc-800">
          <button 
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-zinc-300 bg-zinc-800 hover:bg-zinc-700 transition-colors"
          >
            {cancelText}
          </button>
          <button 
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-bold transition-colors ${styles.btnClass}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
