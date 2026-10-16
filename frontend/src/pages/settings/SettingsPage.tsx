import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check, LogOut, Minus } from "lucide-react";
import { Card, Field, PageHeader } from "@/components/ui/Page";
import { PasswordRules, passwordChecks } from "@/components/forms/PasswordRules";
import EmailSettingsSection from "@/components/settings/EmailSettingsSection";
import ScheduledReportsSection from "@/components/settings/ScheduledReportsSection";
import { useAuth } from "@/context/AuthContext";
import { authService } from "@/services";
import { ROLE_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage } from "@/lib/utils";

export default function SettingsPage() {
  const { role, userName, userEmail, isAdmin, isSuperAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const permissions = [
    { label: "View investors, deposits, withdrawals, interest and emails", has: true },
    { label: "Add investors, record deposits and withdrawal requests", has: true },
    { label: "Approve withdrawals, reverse deposits, set the interest rate", has: isAdmin },
    { label: "Calculate, approve and mark interest paid", has: isAdmin },
    { label: "Manage user accounts, audit log, backups and email settings", has: isSuperAdmin },
  ];

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await authService.changePassword(current, next);
      toast.success(res.message);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader title="Settings" subtitle="Your account and, for super admins, system email settings." />
      <div className="row g-3">
        <div className="col-lg-5">
          <Card title="Your account" className="mb-3">
            <dl className="mb-3" style={{ fontSize: 14 }}>
              {[["Name", userName], ["Email", userEmail], ["Role", role ? ROLE_LABELS[role] : "—"]].map(([k, v]) => (
                <div key={k} className="d-flex py-1">
                  <dt className="fw-normal" style={{ width: 90, color: "var(--color-text-tertiary)" }}>{k}</dt>
                  <dd className="mb-0">{v ?? "—"}</dd>
                </div>
              ))}
            </dl>
            <p className="app-section-label">What you can do</p>
            <ul className="list-unstyled mb-0" style={{ fontSize: 13.5 }}>
              {permissions.map((p) => (
                <li key={p.label} className="d-flex align-items-start gap-2 mb-1"
                  style={{ color: p.has ? "var(--color-text-primary)" : "var(--color-text-disabled)" }}>
                  {p.has ? <Check size={15} className="mt-1 flex-shrink-0" style={{ color: "var(--color-success)" }} />
                    : <Minus size={15} className="mt-1 flex-shrink-0" />}
                  {p.label}
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Change password" className="mb-3">
            <form onSubmit={changePassword} noValidate>
              <Field label="Current password">
                <input type="password" className="form-control" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
              </Field>
              <Field label="New password">
                <input type="password" className="form-control" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
              </Field>
              <Field label="Confirm new password">
                <input type="password" className="form-control" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </Field>
              <PasswordRules password={next} confirm={confirm} />
              <button type="submit" className="btn btn-primary btn-sm"
                disabled={saving || !current || !passwordChecks(next, confirm).every((c) => c.ok)}>
                {saving ? "Saving…" : "Change password"}
              </button>
            </form>
          </Card>

          <button className="btn btn-outline-danger w-100 d-flex align-items-center justify-content-center gap-2"
            onClick={() => { logout(); navigate(ROUTES.LOGIN); }}>
            <LogOut size={15} /> Sign out
          </button>
        </div>

        <div className="col-lg-7">
          {isSuperAdmin && <EmailSettingsSection />}
          {isSuperAdmin && <ScheduledReportsSection />}
          <Card title="About">
            <p className="mb-1" style={{ fontSize: 14 }}>Anchorstone Capital Ltd — Investor Statement System</p>
            <p className="mb-0" style={{ fontSize: 12.5, color: "var(--color-text-tertiary)" }}>Version 1.1.0</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
