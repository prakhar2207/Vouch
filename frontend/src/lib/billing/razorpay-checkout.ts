"use client";

declare global {
  interface Window {
    Razorpay?: any;
  }
}

export interface RazorpayCheckoutOptions {
  key: string;
  amount: number;
  currency: string;
  orderId: string;
  name?: string;
  description?: string;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  notes?: Record<string, any>;
  onSuccess: (paymentData: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) => void;
  onError?: (err: any) => void;
  onDismiss?: () => void;
}

/**
 * Dynamically loads the official Razorpay Checkout.js script.
 */
export function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve(false);
      return;
    }

    if (window.Razorpay) {
      resolve(true);
      return;
    }

    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => {
      console.error("Failed to load Razorpay Checkout script.");
      resolve(false);
    };
    document.body.appendChild(script);
  });
}

/**
 * Opens Razorpay standard checkout modal.
 */
export async function openRazorpayCheckout(options: RazorpayCheckoutOptions): Promise<void> {
  const loaded = await loadRazorpayScript();
  if (!loaded || !window.Razorpay) {
    if (options.onError) {
      options.onError(new Error("Unable to initialize Razorpay payment checkout."));
    } else {
      alert("Unable to initialize Razorpay payment checkout. Please check your internet connection.");
    }
    return;
  }

  const rzpOptions = {
    key: options.key,
    amount: options.amount,
    currency: options.currency || "INR",
    name: options.name || "SriLekh Accounting",
    description: options.description || "SriLekh Cloud Subscription",
    order_id: options.orderId,
    prefill: {
      name: options.prefill?.name || "",
      email: options.prefill?.email || "",
      contact: options.prefill?.contact || "",
    },
    notes: options.notes || {},
    theme: {
      color: "#162C5B",
    },
    handler: function (response: any) {
      options.onSuccess({
        razorpay_order_id: response.razorpay_order_id,
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_signature: response.razorpay_signature,
      });
    },
    modal: {
      ondismiss: function () {
        if (options.onDismiss) {
          options.onDismiss();
        }
      },
    },
  };

  const razorpayInstance = new window.Razorpay(rzpOptions);
  razorpayInstance.on("payment.failed", function (response: any) {
    if (options.onError) {
      options.onError(response.error);
    }
  });

  razorpayInstance.open();
}
