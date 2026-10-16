import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { DatabaseBackup, Loader2 } from "lucide-react";
import { Card, EmptyState, LoadingRow, PageHeader, Stat } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { backupService } from "@/services";
import type { BackupLogEntry, BackupStatus } from "@/lib/types";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const BACKUP_STATUS: Record<BackupLogEntry["status"], string> = { success: "sent", failed: "failed", running: "queued" };

export default function BackupsPage() {
  const [backups, setBackups] = useState<BackupLogEntry[] | null>(null);
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, st] = await Promise.all([backupService.getAll(), backupService.getStatus()]);
      setBackups(list);
      setStatus(st);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't load backups."));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runNow = async () => {
    setRunning(true);
    try {
      await backupService.runNow();
      toast.success("Backup started. It appears below when it finishes uploading to OneDrive.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start the backup."));
    } finally {
      setRunning(false);
      load();
    }
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Backups"
        subtitle="Daily automatic database backup to OneDrive, plus on-demand backups."
        actions={
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={runNow} disabled={running}>
            {running ? <Loader2 size={14} className="app-spin" /> : <DatabaseBackup size={14} />}
            {running ? "Starting…" : "Run backup now"}
          </button>
        }
      />

      <div className="card mb-3 app-tint">
        <div className="card-body">
          <div className="row g-3">
            <div className="col-sm-4">
              <Stat label="Automatic daily backup" value={status ? (status.enabled ? "Enabled" : "Not configured") : "—"} />
            </div>
            <div className="col-sm-4"><Stat label="Next scheduled run" value={formatDateTime(status?.next_run_at)} /></div>
            <div className="col-sm-4">
              <Stat label="Last backup" value={status?.last_backup ? formatDateTime(status.last_backup.started_at) : "Never"} />
            </div>
          </div>
        </div>
      </div>

      {status && !status.enabled && (
        <div className="alert alert-warning">
          Automatic backups are off. Set <code>DB_BACKUP_ENABLED=true</code> and the OneDrive settings (<code>AZURE_TENANT_ID</code>,{" "}
          <code>AZURE_CLIENT_ID</code>, <code>AZURE_CLIENT_SECRET</code>, <code>ONEDRIVE_USER_ID</code>) in <code>backend/.env</code>, then
          restart the backend. "Run backup now" needs the same settings.
        </div>
      )}

      <Card title="Backup history">
        <div className="app-table-scroll">
          <table className="table app-table align-middle">
            <thead>
              <tr><th>Started</th><th>File</th><th>Trigger</th><th className="text-end">Size</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {!backups && <LoadingRow colSpan={6} />}
              {backups?.map((b) => (
                <tr key={b.id}>
                  <td className="text-nowrap" style={{ fontSize: 13 }}>{formatDateTime(b.started_at)}</td>
                  <td style={{ fontSize: 13 }}>{b.filename}</td>
                  <td style={{ textTransform: "capitalize" }}>{b.triggered_by}</td>
                  <td className="text-end font-tabular">{formatSize(b.file_size_bytes)}</td>
                  <td>
                    <StatusBadge status={BACKUP_STATUS[b.status]} label={b.status} />
                    {b.error_message && <div style={{ fontSize: 12, color: "var(--color-destructive)" }}>{b.error_message}</div>}
                  </td>
                  <td className="text-end">
                    {b.onedrive_web_url && <a href={b.onedrive_web_url} target="_blank" rel="noreferrer">Open in OneDrive</a>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {backups && backups.length === 0 && <EmptyState message="No backups yet." />}
      </Card>
    </div>
  );
}
