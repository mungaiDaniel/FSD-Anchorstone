import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

/**
 * Wraps every signed-in page. No session → sign-in. An account still on a
 * temporary password → the mandatory change-password screen, until it's done.
 * (The API enforces the same rule; this just keeps the UI in step.)
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, mustChangePassword } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) return <Navigate to={ROUTES.LOGIN} state={{ from: location }} replace />;
  if (mustChangePassword) return <Navigate to={ROUTES.CHANGE_PASSWORD} replace />;
  return <>{children}</>;
}
