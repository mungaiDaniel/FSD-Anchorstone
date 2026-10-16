import { useAuth } from "@/context/AuthContext";
import type { UserRole } from "@/lib/types";

interface RoleGateProps {
  /** Roles allowed to see this content */
  allowedRoles: UserRole[];
  /** Content to render if role matches */
  children: React.ReactNode;
  /** Optional fallback if role doesn't match (defaults to null) */
  fallback?: React.ReactNode;
}

/**
 * Conditionally renders children based on the current user's role.
 * This is COSMETIC — it hides UI elements, not a security boundary.
 * Flask enforces roles on every API call server-side.
 */
export function RoleGate({ allowedRoles, children, fallback = null }: RoleGateProps) {
  const { role } = useAuth();

  if (!role || !allowedRoles.includes(role)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
