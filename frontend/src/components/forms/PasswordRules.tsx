import { Check, Circle } from "lucide-react";

/** Mirrors the API's rules in backend/app/Admin/route.py (validate_new_password). */
export const MIN_PASSWORD_LENGTH = 10;

export function passwordChecks(password: string, confirm: string) {
  return [
    { label: `At least ${MIN_PASSWORD_LENGTH} characters`, ok: password.length >= MIN_PASSWORD_LENGTH },
    { label: "Letters and numbers", ok: /[A-Za-z]/.test(password) && /\d/.test(password) },
    { label: "Both entries match", ok: password.length > 0 && password === confirm },
  ];
}

export function PasswordRules({ password, confirm }: { password: string; confirm: string }) {
  return (
    <ul className="list-unstyled mb-3" style={{ fontSize: 12.5 }}>
      {passwordChecks(password, confirm).map((c) => (
        <li key={c.label} className="d-flex align-items-center gap-2 mb-1"
          style={{ color: c.ok ? "var(--color-success)" : "var(--color-text-tertiary)" }}>
          {c.ok ? <Check size={14} strokeWidth={2.5} /> : <Circle size={12} />}
          {c.label}
        </li>
      ))}
    </ul>
  );
}
