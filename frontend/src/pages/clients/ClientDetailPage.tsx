import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  BadgeCheck, Building2, ChevronLeft, FileUp, Pencil, PiggyBank, ShieldAlert, UserPlus,
} from "lucide-react";
import { Actor, Card, EmptyState, PageHeader, Stat } from "@/components/ui/Page";
import { StatusBadge } from "@/components/data/StatusBadge";
import { KycBadge, PartyFlags } from "@/components/clients/ClientBadges";
import {
  ConsentModal, MandateModal, OpenInvestmentModal, PepModal, RelatedPartyModal, ScreeningReviewModal, UploadDocumentModal,
} from "@/components/clients/ClientModals";
import { requestTypeLabel } from "@/components/approvals/ChangeRequestModal";
import { partyService } from "@/services";
import { useAuth } from "@/context/AuthContext";
import type { PartyDocument, PartyOverview, PartyRelationship, ScreeningResult } from "@/lib/types";
import {
  CONSENT_METHOD_LABELS, CONSENT_PURPOSE_LABELS, ID_TYPE_LABELS, ORG_TYPE_LABELS, PARTY_ROLE_LABELS,
  RELATIONSHIP_LABELS, REQUIRED_FIELD_LABELS, ROUTES, WATCHLIST_LABELS,
} from "@/lib/constants";
import { apiErrorMessage, formatDate, formatDateTime, formatKES } from "@/lib/utils";

type Tab = "details" | "accounts" | "relationships" | "documents" | "consents" | "screening" | "changes";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="d-flex py-1 tw:gap-3" style={{ fontSize: 13.5 }}>
      <dt className="fw-normal tw:w-40 tw:shrink-0 tw:text-text-tertiary">{label}</dt>
      <dd className="mb-0 tw:min-w-0 tw:break-words">{children ?? <span className="tw:text-text-disabled">—</span>}</dd>
    </div>
  );
}

function relLabel(r: PartyRelationship) {
  return RELATIONSHIP_LABELS[r.relationship][r.direction];
}

function relDetail(r: PartyRelationship) {
  return [r.kin_relationship, r.share_pct && `${Number(r.share_pct)}%`, r.signatory_list && `List ${r.signatory_list}`,
    r.committed_amount && formatKES(r.committed_amount)].filter(Boolean).join(" · ");
}

export default function ClientDetailPage() {
  const id = Number(useParams().id);
  const { isAdmin } = useAuth();
  const [p, setP] = useState<PartyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("details");
  const [modal, setModal] = useState<"related" | "mandate" | "upload" | "consent" | "pep" | "investment" | null>(null);
  const [review, setReview] = useState<ScreeningResult | null>(null);

  const load = useCallback(() => {
    partyService.overview(id).then((d) => { setP(d); setError(null); })
      .catch((err) => setError(apiErrorMessage(err, "Couldn't load this client.")));
  }, [id]);
  useEffect(load, [load]);

  const act = async (call: () => Promise<{ message: string }>) => {
    try {
      const res = await call();
      toast.success(res.message);
      load();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  if (error && !p) {
    return <div className="app-page"><div className="alert alert-danger">{error}</div><Link to={ROUTES.CLIENTS}>Back to clients</Link></div>;
  }
  if (!p) return <div className="app-page tw:text-text-tertiary">Loading…</div>;

  const person = p.party_type === "person";
  const investment = p.accounts.find((a) => a.account_type === "investment");
  const pendingReview = p.screening_results.filter((r) => r.review_status === "pending");
  const canVerify = p.kyc_status === "pending_review" && p.verification_blockers.length === 0
    && !p.pending_changes.some((c) => c.request_type === "party.verify");
  const docLabel = (d: PartyDocument) => d.label || d.document_type;

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "details", label: "Details" },
    { key: "accounts", label: "Accounts", count: p.accounts.length },
    { key: "relationships", label: "Related parties", count: p.relationships.filter((r) => r.status === "active").length },
    { key: "documents", label: "Documents", count: p.documents.filter((d) => d.current).length },
    { key: "consents", label: "Consents", count: p.consents.filter((c) => c.status === "active").length },
    { key: "screening", label: "Screening", count: pendingReview.length || undefined },
    { key: "changes", label: "Pending changes", count: p.pending_changes.length || undefined },
  ];

  return (
    <div className="app-page">
      <Link to={ROUTES.CLIENTS} className="d-inline-flex align-items-center gap-1 mb-2 text-decoration-none" style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
        <ChevronLeft size={14} /> Clients
      </Link>
      <PageHeader
        title={p.display_name}
        subtitle={
          <span className="d-inline-flex flex-wrap align-items-center gap-2">
            <span className="font-tabular">{p.party_no}</span> ·
            {person ? " Individual" : <span className="d-inline-flex align-items-center gap-1"><Building2 size={13} /> {ORG_TYPE_LABELS[p.organisation!.org_type]}</span>}
            <KycBadge status={p.kyc_status} /><PartyFlags party={p} />
          </span>
        }
        actions={
          p.status !== "merged" && (
            <>
              <Link to={ROUTES.CLIENT_EDIT(p.id)} className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1">
                <Pencil size={14} /> Edit
              </Link>
              {!investment && p.status === "active" && (
                <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("investment")}>
                  <PiggyBank size={14} /> Open investment account
                </button>
              )}
              <button className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1" onClick={() => setModal("pep")}>
                <ShieldAlert size={14} /> {p.is_pep ? "PEP details" : "Flag as PEP"}
              </button>
              {canVerify && (
                <button className="btn btn-primary btn-sm d-flex align-items-center gap-1"
                  onClick={() => act(() => partyService.requestVerification(p.id))}>
                  <BadgeCheck size={14} /> Request KYC verification
                </button>
              )}
            </>
          )
        }
      />

      {p.merged_into && (
        <div className="alert alert-secondary py-2" style={{ fontSize: 13 }}>
          Merged into <Link to={ROUTES.CLIENT_DETAIL(p.merged_into.id)}>{p.merged_into.party_no} {p.merged_into.display_name}</Link>.
        </div>
      )}
      {p.kyc_status !== "verified" && p.verification_blockers.length > 0 && p.status !== "merged" && (
        <div className="alert alert-warning py-2" style={{ fontSize: 13 }}>
          <strong>KYC can't be verified yet.</strong>{" "}
          {p.missing_fields.length > 0 && <>Missing: {p.missing_fields.map((f) => REQUIRED_FIELD_LABELS[f] ?? f).join(", ")}. </>}
          {p.verification_blockers.filter((b) => !b.startsWith("Missing")).join(" ")}
        </div>
      )}

      <div className="card shadow mb-3">
        <div className="card-body">
          <div className="row g-3">
            <div className="col-6 col-md-3"><Stat label="Roles" value={p.roles.map((r) => PARTY_ROLE_LABELS[r.role]).join(", ") || "—"} /></div>
            <div className="col-6 col-md-3"><Stat label="Investment balance" value={investment?.balance ? formatKES(investment.balance) : "—"}
              sub={investment ? investment.account_no : "No investment account"} /></div>
            <div className="col-6 col-md-3"><Stat label="Guarantees given" value={p.guarantees.length}
              sub={p.guarantees.length ? formatKES(p.guarantees.reduce((s, g) => s + Number(g.committed_amount ?? 0), 0)) : undefined} /></div>
            <div className="col-6 col-md-3"><Stat label="Verified" value={p.verified_at ? formatDate(p.verified_at) : "Not yet"}
              sub={p.verified_by ? <Actor email={p.verified_by} prefix="by" /> : undefined} /></div>
          </div>
        </div>
      </div>

      <ul className="nav nav-tabs app-tabs mb-3" role="tablist">
        {tabs.map((t) => (
          <li className="nav-item" key={t.key}>
            <button className={`nav-link${tab === t.key ? " active" : ""}`} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}{t.count !== undefined && <span className="ms-1 tw:text-[11px] tw:text-text-tertiary">{t.count}</span>}
            </button>
          </li>
        ))}
      </ul>

      {tab === "details" && (
        <div className="row g-3">
          <div className="col-lg-6">
            <Card title={person ? "Individual" : "Organisation"} className="mb-3">
              <dl className="mb-0">
                {person ? (
                  <>
                    <Row label="Name">{[p.person?.salutation, p.person?.first_name, p.person?.middle_name, p.person?.last_name].filter(Boolean).join(" ")}
                      {p.person?.name_needs_review && <span className="app-badge badge-waiting ms-2" title="Split from the old investor name; check it">Check name</span>}</Row>
                    <Row label="Gender">{p.person?.gender}</Row>
                    <Row label="Date of birth">{p.person?.date_of_birth ? formatDate(p.person.date_of_birth) : null}</Row>
                    <Row label="Marital status">{p.person?.marital_status}</Row>
                    <Row label="Nationality">{p.person?.nationality} · {p.person?.residency}</Row>
                    <Row label="Employer">{p.person?.employer_name}</Row>
                  </>
                ) : (
                  <>
                    <Row label="Registered name">{p.organisation?.legal_name}</Row>
                    <Row label="Trading name">{p.organisation?.trading_name}</Row>
                    <Row label="Registered on">{p.organisation?.registration_date ? formatDate(p.organisation.registration_date) : null}</Row>
                    <Row label="Signing rule">{p.mandate ? `${p.mandate.rule.replace(/_/g, " ")}${p.mandate.description ? ` — ${p.mandate.description}` : ""}` : null}
                      {" "}<button className="btn btn-link btn-sm p-0 align-baseline" onClick={() => setModal("mandate")}>Set</button></Row>
                  </>
                )}
                <Row label="Sector">{p.person?.sector ?? p.organisation?.sector}</Row>
                <Row label="Nature of business">{p.person?.nature_of_business ?? p.organisation?.nature_of_business}</Row>
                <Row label="Classification">{p.classification}</Row>
                <Row label="Risk rating">{p.risk_rating}</Row>
              </dl>
            </Card>
            {p.pep && (
              <Card title="PEP details" className="mb-3" actions={<StatusBadge status={p.pep.status === "approved" ? "approved" : p.pep.status === "pending" ? "pending" : "cancelled"} label={p.pep.status} />}>
                <dl className="mb-0">
                  <Row label="Position">{p.pep.position_held}{p.pep.since ? ` since ${formatDate(p.pep.since)}` : ""}</Row>
                  <Row label="PEP is">{p.pep.pep_relationship === "self" ? "The client" : `${p.pep.pep_relationship.replace("_", " ")}: ${p.pep.related_pep_name}`}</Row>
                  <Row label="Source of funds">{p.pep.source_of_funds}</Row>
                  <Row label="Source of wealth">{p.pep.source_of_wealth}</Row>
                  <Row label="Approved by">{p.pep.approved_by}</Row>
                </dl>
              </Card>
            )}
          </div>
          <div className="col-lg-6">
            <Card title="Identification and contact" className="mb-3">
              <dl className="mb-0">
                {p.identifiers.length === 0 && <Row label="Identifiers">{null}</Row>}
                {p.identifiers.map((i) => <Row key={i.id} label={ID_TYPE_LABELS[i.id_type]}><span className="font-tabular">{i.value}</span></Row>)}
                {p.contacts.map((c) => (
                  <Row key={c.id} label={c.kind === "email" ? "Email" : c.kind === "mobile" ? "Mobile" : "Phone"}>
                    <span className="font-tabular">{c.value}</span>
                    {c.needs_review && <span className="app-badge badge-waiting ms-2" title="Couldn't be read as a Kenyan number">Check</span>}
                  </Row>
                ))}
                {p.addresses.map((a) => (
                  <Row key={a.id} label={`${a.kind.charAt(0).toUpperCase()}${a.kind.slice(1)} address`}>
                    {[a.line1, a.line2, a.town, a.county].filter(Boolean).join(", ")}
                  </Row>
                ))}
              </dl>
            </Card>
            <Card title="Bank and payout" className="mb-3">
              {p.bank_accounts.length === 0 ? <p className="tw:text-sm tw:text-text-tertiary mb-0">No account on file.</p> : (
                <dl className="mb-0">
                  {p.bank_accounts.map((b) => (
                    <Row key={b.id} label={b.kind === "mpesa" ? "M-Pesa" : b.bank_name ?? "Bank"}>
                      <span className="font-tabular">{b.account_no}</span>{b.branch_name ? ` · ${b.branch_name}` : ""}
                      {b.is_default_payout && <span className="app-badge badge-positive ms-2">Payout</span>}
                    </Row>
                  ))}
                </dl>
              )}
            </Card>
            <Card title="Record" className="mb-3">
              <dl className="mb-0">
                <Row label="Created">{formatDateTime(p.created_at)} <Actor email={p.created_by} prefix="by" /></Row>
                <Row label="Branch">{p.home_branch_id === 1 ? "000 Head Office" : `Branch ${p.home_branch_id}`}</Row>
                <Row label="Notes">{p.notes}</Row>
              </dl>
            </Card>
          </div>
        </div>
      )}

      {tab === "accounts" && (
        <Card title="Accounts and loans">
          {p.accounts.length === 0 ? (
            <EmptyState icon={<PiggyBank size={22} />} title="No accounts" message="This client has no investment account or loan."
              action={p.status === "active" ? <button className="btn btn-sm btn-primary" onClick={() => setModal("investment")}>Open investment account</button> : undefined} />
          ) : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Account</th><th>Type</th><th>Opened</th><th>Status</th><th className="text-end">Balance</th><th className="text-end">Pending withdrawals</th><th /></tr></thead>
                <tbody>
                  {p.accounts.map((a) => (
                    <tr key={a.id}>
                      <td className="font-tabular tw:font-semibold">{a.account_no}</td>
                      <td>Investment</td>
                      <td className="nowrap">{formatDate(a.opened_on)}</td>
                      <td><StatusBadge status={a.status} /></td>
                      <td className="text-end font-tabular">{a.balance ? formatKES(a.balance) : "—"}</td>
                      <td className="text-end font-tabular">{a.pending_withdrawals ? formatKES(a.pending_withdrawals) : "—"}</td>
                      <td className="text-end">{a.investor_id && <Link to={ROUTES.INVESTOR_DETAIL(a.investor_id)} className="btn btn-sm app-btn-ghost">Open</Link>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="tw:text-xs tw:text-text-tertiary mt-3 mb-0">Loans appear here once lending goes live.</p>
        </Card>
      )}

      {tab === "relationships" && (
        <Card title="Related parties" actions={p.status !== "merged" && (
          <button className="btn btn-sm btn-primary d-flex align-items-center gap-1" onClick={() => setModal("related")}><UserPlus size={14} /> Add</button>)}>
          {p.relationships.length === 0 ? <EmptyState message="No directors, next of kin, guarantors or other links yet." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Relationship</th><th>Client</th><th>Details</th><th>Since</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {p.relationships.map((r) => (
                    <tr key={r.id}>
                      <td className="nowrap">{relLabel(r)}</td>
                      <td><Link to={ROUTES.CLIENT_DETAIL(r.party.id)}>{r.party.display_name}</Link>
                        <div className="font-tabular tw:text-[11px] tw:text-text-tertiary">{r.party.party_no}</div></td>
                      <td className="tw:text-text-secondary">{relDetail(r) || "—"}</td>
                      <td className="nowrap">{formatDate(r.started_on)}</td>
                      <td><StatusBadge status={r.status === "active" ? "active" : "closed"} label={r.status} /></td>
                      <td className="text-end">
                        {r.status === "active" && (
                          <button className="btn btn-sm app-btn-ghost-danger" onClick={() => act(() => partyService.endRelationship(p.id, r.id))}>End</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "documents" && (
        <Card title="Documents" actions={p.status !== "merged" && (
          <button className="btn btn-sm btn-primary d-flex align-items-center gap-1" onClick={() => setModal("upload")}><FileUp size={14} /> Upload</button>)}>
          {p.documents.length === 0 ? <EmptyState message="No documents uploaded yet." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Document</th><th>File</th><th>Uploaded</th><th>Version</th><th /></tr></thead>
                <tbody>
                  {p.documents.map((d) => (
                    <tr key={d.id} className={d.current ? "" : "tw:opacity-70"}>
                      <td>{docLabel(d)}</td>
                      <td className="tw:text-text-secondary tw:truncate tw:max-w-[220px]">{d.filename}</td>
                      <td className="nowrap">{formatDateTime(d.uploaded_at)} <Actor email={d.uploaded_by} prefix="by" /></td>
                      <td>{d.status === "destroyed" ? <StatusBadge status="cancelled" label="Destroyed" /> :
                        d.current ? <span className="app-badge badge-positive">Current</span> : <span className="app-badge badge-neutral">Earlier</span>}</td>
                      <td className="text-end">
                        {d.status === "active" && (
                          <button className="btn btn-sm app-btn-ghost" onClick={() => partyService.openDocument(d).catch((err) => toast.error(apiErrorMessage(err)))}>Open</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "consents" && (
        <Card title="Consents" actions={p.status !== "merged" && (
          <button className="btn btn-sm btn-primary" onClick={() => setModal("consent")}>Record consent</button>)}>
          {p.consents.length === 0 ? (
            <EmptyState message="No consent recorded. Without consent for automatic document reading, documents are captured by hand." />
          ) : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Purpose</th><th>Given</th><th>How</th><th>Notice</th><th>Captured by</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {p.consents.map((c) => (
                    <tr key={c.id}>
                      <td>{CONSENT_PURPOSE_LABELS[c.purpose]}</td>
                      <td className="nowrap">{formatDate(c.granted_on)}</td>
                      <td>{CONSENT_METHOD_LABELS[c.method]}</td>
                      <td className="font-tabular">{c.notice_version}</td>
                      <td><Actor email={c.captured_by} /></td>
                      <td>{c.status === "active" ? <StatusBadge status="active" /> : (
                        <span title={c.withdrawal_note ?? undefined}><StatusBadge status="cancelled" label={`Withdrawn ${formatDate(c.withdrawn_at)}`} /></span>)}</td>
                      <td className="text-end">
                        {c.status === "active" && (
                          <button className="btn btn-sm app-btn-ghost-danger" onClick={() => act(() => partyService.withdrawConsent(p.id, c.id))}>Withdraw</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "screening" && (
        <Card title="Watchlist screening">
          {p.screening_results.length === 0 ? <EmptyState message="Not screened yet. The daily check will screen this client." /> : (
            <div className="app-table-scroll">
              <table className="table app-table align-middle mb-0">
                <thead><tr><th>Screened</th><th>Why</th><th>Result</th><th>Review</th><th /></tr></thead>
                <tbody>
                  {p.screening_results.map((r) => (
                    <tr key={r.id}>
                      <td className="nowrap">{formatDateTime(r.screened_at)}</td>
                      <td>{r.trigger.replace("_", " ")}</td>
                      <td>{r.outcome === "clear" ? <span className="tw:text-text-secondary">Clear</span> : (
                        <div>{r.matches.map((m) => <div key={m.entry_id}><strong>{m.name}</strong> · {WATCHLIST_LABELS[m.list]} ({m.matched_on.join(", ")})</div>)}</div>)}</td>
                      <td>
                        {r.review_status === "not_required" ? "—" : <StatusBadge status={r.review_status === "pending" ? "pending" : r.review_status === "cleared" ? "approved" : "rejected"} label={r.review_status} />}
                        {r.review_note && <div className="tw:text-[11px] tw:text-text-tertiary">{r.review_note} · <Actor email={r.reviewed_by} /></div>}
                      </td>
                      <td className="text-end">
                        {r.review_status === "pending" && isAdmin && <button className="btn btn-sm btn-primary" onClick={() => setReview(r)}>Review</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "changes" && (
        <Card title="Pending changes">
          {p.pending_changes.length === 0 ? <EmptyState message="Nothing is waiting for approval for this client." /> : (
            <ul className="list-unstyled mb-0">
              {p.pending_changes.map((c) => (
                <li key={c.id} className="d-flex align-items-center justify-content-between gap-3 py-2 tw:border-b tw:border-border-subtle">
                  <div>
                    <div className="tw:text-[11px] tw:font-semibold tw:uppercase tw:text-text-tertiary">{requestTypeLabel(c.request_type)} · #{c.id}</div>
                    <div style={{ fontSize: 13.5 }}>{c.summary}</div>
                    <div className="tw:text-[11px] tw:text-text-tertiary"><Actor email={c.maker_email} prefix="by" /> · {formatDateTime(c.submitted_at)} · {c.levels_done} of {c.levels_required} level(s)</div>
                  </div>
                  <Link to={`${ROUTES.APPROVALS}?id=${c.id}`} className={`btn btn-sm ${c.can_decide ? "btn-primary" : "app-btn-ghost"}`}>
                    {c.can_decide ? "Review" : "View"}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <RelatedPartyModal party={p} open={modal === "related"} onClose={() => setModal(null)} onDone={load} />
      <MandateModal party={p} open={modal === "mandate"} onClose={() => setModal(null)} onDone={load} />
      <UploadDocumentModal partyId={p.id} open={modal === "upload"} onClose={() => setModal(null)} onDone={load} />
      <ConsentModal partyId={p.id} documents={p.documents} open={modal === "consent"} onClose={() => setModal(null)} onDone={load} />
      <PepModal party={p} open={modal === "pep"} onClose={() => setModal(null)} onDone={load} />
      <OpenInvestmentModal party={p} open={modal === "investment"} onClose={() => setModal(null)} onDone={load} />
      <ScreeningReviewModal result={review} onClose={() => setReview(null)} onDone={load} />
    </div>
  );
}
