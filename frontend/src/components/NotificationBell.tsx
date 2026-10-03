"use client";

import { useState, useEffect, useRef } from "react";
import { Bell, CheckCircle2, AlertCircle } from "lucide-react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import { useToast } from "@/context/ToastContext";

const urlBase64ToUint8Array = (base64String: string) => {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
};

export function NotificationBell() {
  const { toast } = useToast();
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || "";

  useEffect(() => {
    fetchNotifications();
    checkPushSubscription();
    
    // Refresh notifications every minute
    const interval = setInterval(fetchNotifications, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchNotifications = async () => {
    try {
      const token = localStorage.getItem("access_token");
      if (!token) return;
      const res = await axios.get(`${API_BASE_URL}/api/v1/notifications/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setNotifications(res.data);
      setUnreadCount(res.data.filter((n: any) => !n.is_read).length);
    } catch (e) {
      console.error(e);
    }
  };

  const markAllRead = async () => {
    try {
      const token = localStorage.getItem("access_token");
      await axios.post(`${API_BASE_URL}/api/v1/notifications/mark-read/`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const markRead = async (id: number) => {
    try {
      const token = localStorage.getItem("access_token");
      await axios.post(`${API_BASE_URL}/api/v1/notifications/${id}/mark-read/`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const checkPushSubscription = async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) setPushEnabled(true);
  };

  const subscribeToPush = async () => {
    if (!("serviceWorker" in navigator)) return;
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });

      const token = localStorage.getItem("access_token");
      await axios.post(`${API_BASE_URL}/api/v1/notifications/subscribe/`, subscription.toJSON(), {
        headers: { Authorization: `Bearer ${token}` },
      });
      setPushEnabled(true);
      toast.success("Push notifications enabled!");
    } catch (e) {
      console.error("Failed to subscribe:", e);
      toast.error("Failed to enable notifications. Please check browser permissions.");
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        className="relative p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-muted/60 transition-colors cursor-pointer min-h-[44px] min-w-[44px] items-center justify-center flex"
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full ring-2 ring-background"></span>
        )}
      </button>

      {isOpen && (
        <div
          role="region"
          aria-label="Notifications"
          className="absolute right-0 mt-2 w-80 sm:w-96 bg-card border border-border shadow-2xl rounded-2xl z-50 overflow-hidden"
        >
          <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
            <h3 className="font-bold text-sm text-foreground">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Mark all read
              </button>
            )}
          </div>
          
          {!pushEnabled && (
            <div className="p-3 bg-blue-500/10 border-b border-blue-500/20 text-xs text-blue-400 flex flex-col gap-2">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>Enable push notifications to receive real-time updates when the app is closed.</span>
              </div>
              <button 
                onClick={subscribeToPush}
                className="self-end px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded shadow-sm font-semibold transition-colors cursor-pointer"
              >
                Enable Notifications
              </button>
            </div>
          )}

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-xs">
                No notifications yet.
              </div>
            ) : (
              <div className="divide-y divide-border/60">
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    onClick={() => {
                      if (!n.is_read) markRead(n.id);
                      if (n.link) window.location.href = n.link;
                    }}
                    className={`p-4 hover:bg-muted/40 transition-colors cursor-pointer ${
                      !n.is_read ? "bg-muted/10 border-l-2 border-l-blue-500" : ""
                    }`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <h4 className={`text-xs ${!n.is_read ? "font-bold text-foreground" : "font-medium text-foreground/80"}`}>
                        {n.title}
                      </h4>
                      <span className="text-[10px] text-muted-foreground whitespace-nowrap ml-2">
                        {new Date(n.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className={`text-xs ${!n.is_read ? "text-foreground/90" : "text-muted-foreground"}`}>
                      {n.message}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
