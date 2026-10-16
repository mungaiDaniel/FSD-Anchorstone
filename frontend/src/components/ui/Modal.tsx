import { useEffect, type FormEvent, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** When provided, the body is a form and the primary button submits it. */
  onSubmit?: () => void;
  submitLabel?: string;
  submitting?: boolean;
  submitVariant?: "primary" | "danger";
  submitDisabled?: boolean;
  wide?: boolean;
}

export function Modal({
  title,
  open,
  onClose,
  children,
  onSubmit,
  submitLabel = "Save",
  submitting = false,
  submitVariant = "primary",
  submitDisabled = false,
  wide = false,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !submitting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, submitting]);

  if (!open) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!submitting && !submitDisabled) onSubmit?.();
  };

  const header = (
    <div className="d-flex align-items-center justify-content-between px-4 pt-4 pb-2">
      <h2 className="app-section-title mb-0">{title}</h2>
      <button type="button" className="btn p-1 border-0" onClick={onClose} disabled={submitting} aria-label="Close"
        style={{ color: "var(--color-text-tertiary)" }}>
        <X size={18} />
      </button>
    </div>
  );
  const body = <div className="px-4 py-2 pb-4" style={{ maxHeight: "75vh", overflowY: "auto" }}>{children}</div>;
  const style = { maxWidth: wide ? 760 : 500 };

  return (
    <div
      className="app-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}
    >
      {onSubmit ? (
        <form className="modal-content app-modal" style={style} onSubmit={handleSubmit}>
          {header}
          {body}
          <div className="d-flex justify-content-end gap-2 px-4 pb-4">
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className={`btn btn-sm btn-${submitVariant}`} disabled={submitting || submitDisabled}>
              {submitting ? "Working…" : submitLabel}
            </button>
          </div>
        </form>
      ) : (
        // Content brings its own form/buttons (e.g. InvestorForm) — never nest forms.
        <div className="modal-content app-modal" style={style}>
          {header}
          {body}
        </div>
      )}
    </div>
  );
}
