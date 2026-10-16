import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { AuthLayout } from "@/components/brand/AuthLayout";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

export default function LoginPage() {
  const { login, loading, error, clearError, isAuthenticated, mustChangePassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname || ROUTES.OVERVIEW;

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  if (isAuthenticated) return <Navigate to={mustChangePassword ? ROUTES.CHANGE_PASSWORD : ROUTES.OVERVIEW} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    const res = await login(email.trim(), password);
    if (res.ok) navigate(res.mustChangePassword ? ROUTES.CHANGE_PASSWORD : from, { replace: true });
  };

  return (
    <AuthLayout>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--color-brand-400)", margin: "0 0 4px" }}>Sign in</h1>
      <p style={{ fontSize: 14, color: "var(--color-text-secondary)", margin: "0 0 24px" }}>Use the account your administrator set up for you.</p>

      {error && (
        <div className="alert alert-danger py-2" role="alert">{error}</div>
      )}

      <form onSubmit={submit} noValidate>
        <label className="form-label mb-3">
          Email
          <input type="email" className="form-control" autoComplete="username" autoFocus required
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="form-label mb-4">
          Password
          <div className="position-relative">
            <input type={showPassword ? "text" : "password"} className="form-control pe-5" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)} />
            <button type="button" className="btn btn-link position-absolute top-50 end-0 translate-middle-y px-3 py-0"
              onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Hide password" : "Show password"}
              style={{ color: "var(--color-text-tertiary)" }}>
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </label>
        <button type="submit" className="btn btn-primary w-100 py-2" disabled={loading || !email.trim() || !password}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p style={{ fontSize: 12.5, color: "var(--color-text-tertiary)", margin: "20px 0 0", textAlign: "center" }}>
        Forgotten your password? Ask an administrator to reset it.
      </p>
    </AuthLayout>
  );
}
