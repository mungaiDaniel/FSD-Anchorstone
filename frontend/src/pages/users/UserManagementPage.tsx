import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, KeyRound, UserPlus } from "lucide-react";
import { Card, EmptyState, Field, LoadingRow, PageHeader } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/data/StatusBadge";
import { userService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { User, UserRole } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/constants";
import { apiErrorMessage, formatDate } from "@/lib/utils";

const ROLE_HELP: Record<UserRole, string> = {
  user: "Adds investors, records deposits and withdrawal requests.",
  admin: "Also approves withdrawals and interest, reverses deposits, sets the rate.",
  super_admin: "Also manages user accounts, audit log, backups and email settings.",
};

/** Shown once after creating an account or resetting a password. */
function TemporaryPasswordModal({ result, onClose }: { result: { email: string; password: string; created: boolean } | null; onClose: () => void }) {
  if (!result) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.password);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy — select it and copy manually.");
    }
  };
  return (
    <Modal title={result.created ? "Account created" : "Password reset"} open onClose={onClose}>
      <p style={{ fontSize: 14 }}>
        Give this temporary password to <strong>{result.email}</strong>. They'll be asked to choose their own the first time they sign in.
      </p>
      <div className="d-flex align-items-center gap-2 p-3 mb-3 app-tint" style={{ borderRadius: 8 }}>
        <code className="flex-grow-1" style={{ fontSize: 18, color: "var(--color-brand-400)", letterSpacing: "0.04em" }}>{result.password}</code>
        <button type="button" className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1" onClick={copy}>
          <Copy size={14} /> Copy
        </button>
      </div>
      <p className="mb-0" style={{ fontSize: 12.5, color: "var(--color-text-tertiary)" }}>
        This is the only time it's shown. If it's lost, reset the password again.
      </p>
    </Modal>
  );
}

export default function UserManagementPage() {
  const { userEmail } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [saving, setSaving] = useState(false);
  const [temp, setTemp] = useState<{ email: string; password: string; created: boolean } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<User | null>(null);

  const load = useCallback(() => {
    userService.getAll().then(setUsers).catch((err) => toast.error(apiErrorMessage(err, "Couldn't load users.")));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isSelf = (u: User) => u.email.toLowerCase() === (userEmail ?? "").toLowerCase();

  const run = async (fn: () => Promise<{ message: string }>) => {
    try {
      toast.success((await fn()).message);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  const create = async () => {
    setSaving(true);
    try {
      const res = await userService.create(name.trim(), email.trim(), role);
      setCreateOpen(false);
      setTemp({ email: res.data!.user.email, password: res.data!.temporary_password, created: true });
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const reset = async (u: User) => {
    try {
      const res = await userService.resetPassword(u.id);
      setTemp({ email: u.email, password: res.data!.temporary_password, created: false });
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Users"
        subtitle="Staff accounts are created here — there's no public sign-up. New accounts get a temporary password that must be changed at first sign-in."
        actions={
          <button className="btn btn-primary btn-sm d-flex align-items-center gap-1"
            onClick={() => { setName(""); setEmail(""); setRole("user"); setCreateOpen(true); }}>
            <UserPlus size={15} /> Create account
          </button>
        }
      />

      <Card>
        <div className="app-table-scroll">
          <table className="table app-table align-middle">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th /></tr>
            </thead>
            <tbody>
              {!users && <LoadingRow colSpan={6} />}
              {users?.map((u) => (
                <tr key={u.id}>
                  <td className="fw-semibold">{u.name}{isSelf(u) && <span style={{ color: "var(--color-text-tertiary)", fontWeight: 400 }}> (you)</span>}</td>
                  <td>{u.email}</td>
                  <td style={{ minWidth: 150 }}>
                    {isSelf(u) ? ROLE_LABELS[u.role] : (
                      <select className="form-select form-select-sm" value={u.role} aria-label={`Role for ${u.email}`}
                        onChange={(e) => run(() => userService.setRole(u.id, e.target.value as UserRole))}>
                        {(Object.keys(ROLE_LABELS) as UserRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                      </select>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={u.status} />
                    {u.must_change_password && u.status === "active" && (
                      <div style={{ fontSize: 11.5, color: "var(--color-text-tertiary)" }}>Hasn't set a password yet</div>
                    )}
                  </td>
                  <td style={{ fontSize: 13 }}>{formatDate(u.created)}</td>
                  <td className="text-end text-nowrap">
                    {!isSelf(u) && (
                      <>
                        <button className="btn btn-sm btn-outline-secondary me-1 d-inline-flex align-items-center gap-1" onClick={() => reset(u)}>
                          <KeyRound size={13} /> Reset password
                        </button>
                        <button className="btn btn-sm btn-outline-secondary me-1"
                          onClick={() => run(() => userService.setStatus(u.id, u.status === "active" ? "disabled" : "active"))}>
                          {u.status === "active" ? "Disable" : "Enable"}
                        </button>
                        <button className="btn btn-sm btn-outline-danger" onClick={() => setConfirmDelete(u)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {users && users.length === 0 && <EmptyState message="No accounts yet." />}
      </Card>

      <Modal title="Create account" open={createOpen} onClose={() => setCreateOpen(false)} onSubmit={create}
        submitLabel="Create account" submitting={saving}
        submitDisabled={!name.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())}>
        <Field label="Full name">
          <input className="form-control" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoFocus />
        </Field>
        <Field label="Work email">
          <input type="email" className="form-control" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={100} />
        </Field>
        <Field label="Role" hint={ROLE_HELP[role]}>
          <select className="form-select" value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
            {(Object.keys(ROLE_LABELS) as UserRole[]).map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </Field>
        <p className="mb-0" style={{ fontSize: 12.5, color: "var(--color-text-tertiary)" }}>
          A temporary password is generated and shown once after you create the account.
        </p>
      </Modal>

      <Modal title="Delete account" open={!!confirmDelete} onClose={() => setConfirmDelete(null)} submitVariant="danger"
        submitLabel="Delete account"
        onSubmit={() => { const u = confirmDelete!; setConfirmDelete(null); run(() => userService.delete(u.id)); }}>
        <p className="mb-0" style={{ fontSize: 14 }}>
          Delete <strong>{confirmDelete?.email}</strong>? Their past actions stay in the audit log. To block access but keep the
          account, disable it instead.
        </p>
      </Modal>

      <TemporaryPasswordModal result={temp} onClose={() => setTemp(null)} />
    </div>
  );
}
