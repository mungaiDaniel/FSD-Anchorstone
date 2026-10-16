import type { ReactNode } from "react";
import { Wordmark } from "./Wordmark";

/** Split sign-in layout: navy brand panel + white panel holding a form card. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-split">
      <aside className="auth-brand-panel">
        <Wordmark tone="light" size="lg" />
        <div style={{ width: 56, height: 2, background: "rgba(255,255,255,0.5)", margin: "28px 0 18px" }} />
        <p style={{ margin: 0, fontSize: 16, color: "rgba(255,255,255,0.88)", fontWeight: 500 }}>Investor Statement System</p>
        <p style={{ margin: "6px 0 0", fontSize: 13, color: "rgba(255,255,255,0.65)" }}>Staff access only</p>
      </aside>
      <main className="auth-form-panel">
        <div className="auth-card">{children}</div>
      </main>
    </div>
  );
}
