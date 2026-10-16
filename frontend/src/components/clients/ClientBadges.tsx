import type { KycStatus, PartySummary } from "@/lib/types";
import { KYC_STATUS_LABELS } from "@/lib/constants";

const KYC_TONES: Record<KycStatus, string> = {
  incomplete: "badge-neutral",
  pending_review: "badge-waiting",
  verified: "badge-positive",
};

export function KycBadge({ status }: { status: KycStatus }) {
  return <span className={`app-badge ${KYC_TONES[status]} tw:whitespace-nowrap`}>{KYC_STATUS_LABELS[status]}</span>;
}

/** PEP, blacklisted and merged markers. */
export function PartyFlags({ party }: { party: Pick<PartySummary, "is_pep" | "status"> }) {
  return (
    <>
      {party.is_pep && <span className="app-badge badge-waiting" title="Politically exposed person">PEP</span>}
      {party.status === "blacklisted" && <span className="app-badge badge-negative">Blacklisted</span>}
      {party.status === "merged" && <span className="app-badge badge-neutral">Merged</span>}
    </>
  );
}
