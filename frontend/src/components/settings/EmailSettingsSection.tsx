import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { Card, Field } from "@/components/ui/Page";
import { settingsService } from "@/services";
import type { EmailSettingsData, EmailQueueSettingsData } from "@/lib/types";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";

/**
 * Settings → Email sending / Email queue. Super admin only (SettingsPage gates
 * it, and the API enforces it). Changes apply immediately — no restart.
 */
export default function EmailSettingsSection() {
  const [email, setEmail] = useState<EmailSettingsData | null>(null);
  const [server, setServer] = useState("");
  const [port, setPort] = useState("");
  const [useTls, setUseTls] = useState(true);
  const [useSsl, setUseSsl] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sender, setSender] = useState("");
  const [bcc, setBcc] = useState("");
  const [testTo, setTestTo] = useState("");

  const [queue, setQueue] = useState<EmailQueueSettingsData | null>(null);
  const [batchSize, setBatchSize] = useState("");
  const [interval, setIntervalMinutes] = useState("");
  const [busy, setBusy] = useState<"email" | "test" | "queue" | null>(null);

  const loadEmail = async () => {
    try {
      const data = await settingsService.getEmailSettings();
      setEmail(data);
      setServer(data.mail_server ?? "");
      setPort(data.mail_port != null ? String(data.mail_port) : "");
      setUseTls(!!data.mail_use_tls);
      setUseSsl(!!data.mail_use_ssl);
      setUsername(data.mail_username ?? "");
      setSender(data.mail_default_sender ?? "");
      setBcc(data.mail_bcc ?? "");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't load email settings."));
    }
  };

  const loadQueue = async () => {
    try {
      const data = await settingsService.getEmailQueueSettings();
      setQueue(data);
      setBatchSize(String(data.batch_size));
      setIntervalMinutes(String(data.interval_minutes));
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't load queue settings."));
    }
  };

  useEffect(() => {
    loadEmail();
    loadQueue();
  }, []);

  const act = async (kind: "email" | "test" | "queue", fn: () => Promise<{ message: string }>, after?: () => void) => {
    setBusy(kind);
    try {
      toast.success((await fn()).message);
      after?.();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const saveEmail = () =>
    act("email", () => settingsService.updateEmailSettings({
      mail_server: server.trim(),
      mail_port: port ? Number(port) : undefined,
      mail_use_tls: useTls,
      mail_use_ssl: useSsl,
      mail_username: username.trim(),
      ...(password.trim() ? { mail_password: password.trim() } : {}),
      mail_default_sender: sender.trim(),
      mail_bcc: bcc.trim(),
    }), () => { setPassword(""); loadEmail(); });

  return (
    <>
      <Card title="Email sending" className="mb-3">
        {!email ? <p style={{ fontSize: 13, color: "var(--color-text-tertiary)" }}>Loading…</p> : (
          <>
            <p style={{ fontSize: 13, color: "var(--color-text-tertiary)" }}>
              The mailbox investor emails are sent from. Changes apply immediately.
            </p>
            <div className="row g-2">
              <div className="col-md-8"><Field label="SMTP server"><input className="form-control" value={server} onChange={(e) => setServer(e.target.value)} placeholder="smtp.office365.com" /></Field></div>
              <div className="col-md-4"><Field label="Port"><input className="form-control" type="number" value={port} onChange={(e) => setPort(e.target.value)} placeholder="587" /></Field></div>
            </div>
            <div className="d-flex gap-4 mb-3" style={{ fontSize: 13.5 }}>
              <label className="d-flex align-items-center gap-2"><input type="checkbox" className="form-check-input m-0" checked={useTls} onChange={(e) => setUseTls(e.target.checked)} /> Use TLS</label>
              <label className="d-flex align-items-center gap-2"><input type="checkbox" className="form-check-input m-0" checked={useSsl} onChange={(e) => setUseSsl(e.target.checked)} /> Use SSL</label>
            </div>
            <div className="row g-2">
              <div className="col-md-6"><Field label="Username"><input className="form-control" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="statements@yourdomain.com" /></Field></div>
              <div className="col-md-6">
                <Field label="Password" hint={email.has_password ? "Leave blank to keep the saved password." : undefined}>
                  <input className="form-control" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={email.has_password ? "••••••••" : ""} />
                </Field>
              </div>
              <div className="col-md-6"><Field label="From address"><input className="form-control" value={sender} onChange={(e) => setSender(e.target.value)} placeholder="statements@yourdomain.com" /></Field></div>
              <div className="col-md-6"><Field label="BCC every email to (optional)"><input className="form-control" value={bcc} onChange={(e) => setBcc(e.target.value)} /></Field></div>
            </div>
            <button className="btn btn-primary btn-sm" onClick={saveEmail} disabled={busy === "email"}>{busy === "email" ? "Saving…" : "Save"}</button>

            <hr style={{ borderColor: "var(--color-border-default)", opacity: 1 }} />
            <Field label="Send a test email to check these settings">
              <div className="d-flex gap-2">
                <input className="form-control" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="you@example.com" />
                <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1 flex-shrink-0" disabled={!testTo.trim() || busy === "test"}
                  onClick={() => act("test", () => settingsService.sendTestEmail(testTo.trim()))}>
                  <Send size={14} /> {busy === "test" ? "Sending…" : "Send test"}
                </button>
              </div>
            </Field>
          </>
        )}
      </Card>

      <Card title="Email queue" className="mb-3">
        {!queue ? <p style={{ fontSize: 13, color: "var(--color-text-tertiary)" }}>Loading…</p> : (
          <>
            <p style={{ fontSize: 13, color: "var(--color-text-tertiary)" }}>
              How many queued emails go out per run, and how often. Keeps large statement runs under the mail provider's limits.
            </p>
            <div className="row g-2">
              <div className="col-6"><Field label="Emails per run"><input className="form-control" type="number" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} /></Field></div>
              <div className="col-6"><Field label="Every (minutes)"><input className="form-control" type="number" value={interval} onChange={(e) => setIntervalMinutes(e.target.value)} /></Field></div>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--color-text-tertiary)" }}>Next run: {formatDateTime(queue.next_run_at)}</p>
            <button className="btn btn-primary btn-sm" disabled={busy === "queue"}
              onClick={() => act("queue", () => settingsService.updateEmailQueueSettings(Number(batchSize), Number(interval)), loadQueue)}>
              {busy === "queue" ? "Saving…" : "Save"}
            </button>
          </>
        )}
      </Card>
    </>
  );
}
