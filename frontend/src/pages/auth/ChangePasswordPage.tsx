import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AuthLayout } from "@/components/brand/AuthLayout";
import { PasswordRules, passwordChecks } from "@/components/forms/PasswordRules";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

/**
 * Mandatory first-sign-in step for accounts created (or reset) by an admin.
 * Nothing else in the app is reachable until this is done — the API enforces
 * the same rule, so it can't be skipped by typing another URL.
 */
export default function ChangePasswordPage() {
  const { isAuthenticated, mustChangePassword, changePassword, loading, error, clearError, logout, userName } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  if (!isAuthenticated) return <Navigate to={ROUTES.LOGIN} replace />;
  if (!mustChangePassword) return <Navigate to={ROUTES.OVERVIEW} replace />;

  const valid = passwordChecks(next, confirm).every((c) => c.ok) && current.length > 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    if (await changePassword(current, next)) {
      toast.success("Password set. Welcome to Anchorstone.");
      navigate(ROUTES.OVERVIEW, { replace: true });
    }
  };

  return (
    <AuthLayout>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--color-brand-400)", margin: "0 0 4px" }}>Set your password</h1>
      <p style={{ fontSize: 14, color: "var(--color-text-secondary)", margin: "0 0 22px" }}>
        {userName ? `Welcome, ${userName.split(" ")[0]}. ` : ""}You're signed in with a temporary password. Choose your own to continue.
      </p>

      {error && <div className="alert alert-danger py-2" role="alert">{error}</div>}

      <form onSubmit={submit} noValidate>
        <label className="form-label mb-3">
          Temporary password
          <input type="password" className="form-control" autoComplete="current-password" autoFocus
            value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="form-label mb-3">
          New password
          <input type="password" className="form-control" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="form-label mb-2">
          Confirm new password
          <input type="password" className="form-control" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
        <PasswordRules password={next} confirm={confirm} />
        <button type="submit" className="btn btn-primary w-100 py-2" disabled={loading || !valid}>
          {loading ? "Saving…" : "Set password and continue"}
        </button>
      </form>

      <button type="button" className="btn btn-link w-100 mt-3" style={{ fontSize: 13 }}
        onClick={() => { logout(); navigate(ROUTES.LOGIN, { replace: true }); }}>
        Sign out
      </button>
    </AuthLayout>
  );
}
