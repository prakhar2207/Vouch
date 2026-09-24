"use client";

import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API_BASE_URL } from "@/utils/api";
import {
  getAccessToken,
  isAuthenticated,
  getUser,
  setUser,
  AuthUser,
} from "@/utils/auth";

export interface RolePermissions {
  user: AuthUser | null;
  role: string;
  loading: boolean;
  isAdmin: boolean;
  isOwner: boolean;
  isCA: boolean;
  isEmployee: boolean;
  isViewer: boolean;
  canManageSettings: boolean;
  canManageUsers: boolean;
  canManageAccounting: boolean;
  canCreateTransactions: boolean;
  isReadOnly: boolean;
  hasRole: (allowedRoles: string[]) => boolean;
  refreshUser: () => Promise<AuthUser | null>;
}

export function useRole(): RolePermissions {
  const [user, setUserState] = useState<AuthUser | null>(() => getUser());
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async (): Promise<AuthUser | null> => {
    if (!isAuthenticated()) {
      setUserState(null);
      setLoading(false);
      return null;
    }

    try {
      const token = getAccessToken();
      const res = await axios.get(`${API_BASE_URL}/api/v1/auth/me/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const userData = res.data?.data;
      if (userData) {
        setUser(userData);
        setUserState(userData);
        setLoading(false);
        return userData;
      }
    } catch {
      // Fallback to local storage or JWT decoded data
      const localUser = getUser();
      setUserState(localUser);
    } finally {
      setLoading(false);
    }
    return null;
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const rawRole = (user?.role || "VIEWER").toUpperCase();

  const isOwner = rawRole === "OWNER";
  const isAdmin = rawRole === "ADMIN";
  const isCA = rawRole === "CA";
  const isEmployee = rawRole === "EMPLOYEE";
  const isViewer = rawRole === "VIEWER";

  const canManageSettings = isOwner || isAdmin;
  const canManageUsers = isOwner || isAdmin;
  const canManageAccounting = isOwner || isAdmin || isCA;
  const canCreateTransactions = isOwner || isAdmin || isCA || isEmployee;
  const isReadOnly = isViewer;

  const hasRole = (allowedRoles: string[]): boolean => {
    if (isOwner) return true;
    const normalized = allowedRoles.map((r) => r.toUpperCase());
    if (isAdmin && (normalized.includes("ADMIN") || normalized.includes("OWNER"))) return true;
    return normalized.includes(rawRole);
  };

  return {
    user,
    role: rawRole,
    loading,
    isAdmin,
    isOwner,
    isCA,
    isEmployee,
    isViewer,
    canManageSettings,
    canManageUsers,
    canManageAccounting,
    canCreateTransactions,
    isReadOnly,
    hasRole,
    refreshUser,
  };
}
