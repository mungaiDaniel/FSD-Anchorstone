import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

/** Super-admin-only pages. Same checks as ProtectedRoute, plus the role. */
export function SuperAdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isSuperAdmin, mustChangePassword } = useAuth();

  if (!isAuthenticated) return <Navigate to={ROUTES.LOGIN} replace />;
  if (mustChangePassword) return <Navigate to={ROUTES.CHANGE_PASSWORD} replace />;
  if (!isSuperAdmin) return <Navigate to={ROUTES.OVERVIEW} replace />;
  return <>{children}</>;
}
