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
  const isSuper = Boolean(user?.is_superuser);
  const isStaff = Boolean(user?.is_staff);

  const isAdmin = isSuper || isStaff || rawRole === "ADMIN";
  const isOwner = rawRole === "OWNER" || isAdmin;
  const isCA = rawRole === "CA";
  const isEmployee = rawRole === "EMPLOYEE";
  const isViewer = !isAdmin && rawRole === "VIEWER";

  const canManageSettings = isAdmin || rawRole === "OWNER";
  const canManageUsers = isAdmin || rawRole === "OWNER";
  const canManageAccounting = isAdmin || rawRole === "OWNER" || isCA;
  const canCreateTransactions = isAdmin || rawRole === "OWNER" || isCA || isEmployee;
  const isReadOnly = isViewer;

  const hasRole = (allowedRoles: string[]): boolean => {
    if (isAdmin) return true;
    const normalized = allowedRoles.map((r) => r.toUpperCase());
    return normalized.includes(rawRole);
  };

  return {
    user,
    role: isAdmin ? "ADMIN" : rawRole,
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
