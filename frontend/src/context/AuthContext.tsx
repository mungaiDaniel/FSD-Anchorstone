import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import type { UserRole } from "@/lib/types";
import {
  clearTokens,
  getAccessToken,
  getMustChangePassword,
  getUserEmail,
  getUserName,
  getUserRole,
  setMustChangePassword,
  setSession,
} from "@/lib/auth";
import { authService } from "@/services";
import { apiErrorMessage } from "@/lib/utils";

interface AuthContextValue {
  role: UserRole | null;
  userName: string | null;
  userEmail: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  /** True while the account is on a temporary password — only /change-password is reachable. */
  mustChangePassword: boolean;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<{ ok: boolean; mustChangePassword: boolean }>;
  changePassword: (current: string, next: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole | null>(getUserRole());
  const [userName, setUserName] = useState<string | null>(getUserName());
  const [userEmail, setUserEmail] = useState<string | null>(getUserEmail());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getAccessToken());
  const [mustChange, setMustChange] = useState<boolean>(getMustChangePassword());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await authService.login(email, password);
      setSession(res.access_token, res.role, res.name, res.email, res.must_change_password);
      setRole(res.role);
      setUserName(res.name);
      setUserEmail(res.email);
      setMustChange(res.must_change_password);
      setIsAuthenticated(true);
      return { ok: true, mustChangePassword: res.must_change_password };
    } catch (err) {
      setError(apiErrorMessage(err, "Sign-in failed. Please check your details."));
      return { ok: false, mustChangePassword: false };
    } finally {
      setLoading(false);
    }
  }, []);

  const changePassword = useCallback(async (current: string, next: string) => {
    setLoading(true);
    setError(null);
    try {
      await authService.changePassword(current, next);
      setMustChangePassword(false);
      setMustChange(false);
      return true;
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't change the password."));
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setRole(null);
    setUserName(null);
    setUserEmail(null);
    setMustChange(false);
    setIsAuthenticated(false);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return (
    <AuthContext.Provider
      value={{
        role,
        userName,
        userEmail,
        isAuthenticated,
        isAdmin: role === "admin" || role === "super_admin",
        isSuperAdmin: role === "super_admin",
        mustChangePassword: mustChange,
        loading,
        error,
        login,
        changePassword,
        logout,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
