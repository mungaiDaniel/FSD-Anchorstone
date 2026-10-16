import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

/** Admin and super admin pages. The API enforces the same rule on every call. */
export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isAdmin, mustChangePassword } = useAuth();

  if (!isAuthenticated) return <Navigate to={ROUTES.LOGIN} replace />;
  if (mustChangePassword) return <Navigate to={ROUTES.CHANGE_PASSWORD} replace />;
  if (!isAdmin) return <Navigate to={ROUTES.OVERVIEW} replace />;
  return <>{children}</>;
}
