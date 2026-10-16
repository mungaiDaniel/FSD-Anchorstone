import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ListX, Plus, ShieldAlert } from "lucide-react";
import { Actor, EmptyState, Field, LoadingRow, PageHeader, Pagination, SearchField, SegmentedTabs } from "@/components/ui/Page";
import { Modal } from "@/components/ui/Modal";
import { ScreeningReviewModal } from "@/components/clients/ClientModals";
import { screeningService, watchlistService } from "@/services";
import type { Paginated, ScreeningResult, Watchlist, WatchlistEntry } from "@/lib/types";
import { ROUTES, WATCHLIST_LABELS } from "@/lib/constants";
import { apiErrorMessage, formatDateTime } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;
type View = "matches" | Watchlist;

/** Watchlists and the review queue for possible matches (FSD v0.1 KYC-06). Admin screens; the API checks. */
export default function WatchlistPage() {
  const [view, setView] = useState<View>("matches");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [entries, setEntries] = useState<Paginated<WatchlistEntry> | null>(null);
  const [queue, setQueue] = useState<Paginated<ScreeningResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<WatchlistEntry | null>(null);
  const [review, setReview] = useState<ScreeningResult | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    setError(null);
    const call = view === "matches"
      ? screeningService.queue({ page, per_page: PER_PAGE }).then((d) => isLatest() && setQueue(d))
      : watchlistService.list({ list: view, search: search || undefined, page, per_page: PER_PAGE }).then((d) => isLatest() && setEntries(d));
    call.catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [view, search, page, startRequest]);

  useEffect(() => {
    const t = window.setTimeout(load, 200);
    return () => window.clearTimeout(t);
  }, [load]);

  const tabs: { key: View; label: string; count?: number }[] = [
    { key: "matches", label: "Matches to review", count: queue?.total },
    { key: "internal_blacklist", label: WATCHLIST_LABELS.internal_blacklist },
    { key: "pep", label: WATCHLIST_LABELS.pep },
  ];

  return (
    <div className="app-page">
      <PageHeader
        title="Watchlists"
        subtitle="Every client is screened at onboarding, when identity details change, when a name is added and daily. A possible match blocks KYC until a reviewer other than the onboarding officer clears or confirms it."
        actions={<button className="btn btn-primary btn-sm d-flex align-items-center gap-1" onClick={() => setAdding(true)}><Plus size={14} /> Add a name</button>}
      />
      <div className="mb-3">
        <SegmentedTabs label="Watchlist view" items={tabs} value={view} onChange={(k) => { setView(k); setPage(1); }} />
      </div>
      <div className="card shadow">
        <div className="card-body">
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          {view === "matches" ? (
            <>
              <div className="app-table-scroll">
                <table className="table app-table align-middle mb-0">
                  <thead><tr><th>Screened</th><th>Client</th><th>Possible match</th><th>Onboarded by</th><th /></tr></thead>
                  <tbody>
                    {!queue && !error && <LoadingRow colSpan={5} />}
                    {queue?.items.map((r) => (
                      <tr key={r.id}>
                        <td className="nowrap">{formatDateTime(r.screened_at)}</td>
                        <td>{r.party && <Link to={ROUTES.CLIENT_DETAIL(r.party.id)}>{r.party.display_name}</Link>}
                          <div className="font-tabular tw:text-[11px] tw:text-text-tertiary">{r.party?.party_no}</div></td>
                        <td>{r.matches.map((m) => <div key={m.entry_id}><strong>{m.name}</strong> · {WATCHLIST_LABELS[m.list]} ({m.matched_on.join(", ")})</div>)}</td>
                        <td><Actor email={r.maker_email} /></td>
                        <td className="text-end"><button className="btn btn-sm btn-primary" onClick={() => setReview(r)}>Review</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {queue && queue.items.length === 0 && <EmptyState icon={<ShieldAlert size={22} />} title="Nothing to review" message="No possible watchlist matches are waiting." />}
              {queue && <Pagination page={page} perPage={PER_PAGE} total={queue.total} onPage={setPage} />}
            </>
          ) : (
            <>
              <SearchField className="mb-3 tw:max-w-sm" value={search} label="Search names" placeholder="Name" onChange={(v) => { setSearch(v); setPage(1); }} />
              <div className="app-table-scroll">
                <table className="table app-table align-middle mb-0">
                  <thead><tr><th>Name</th><th>Identifiers</th><th>Reason</th><th>Added</th><th /></tr></thead>
                  <tbody>
                    {!entries && !error && <LoadingRow colSpan={5} />}
                    {entries?.items.map((e) => (
                      <tr key={e.id}>
                        <td className="tw:font-semibold">{e.full_name}</td>
                        <td className="font-tabular tw:text-xs">{e.identifiers.map((i) => i.value).join(", ") || "—"}</td>
                        <td className="tw:text-text-secondary">{e.reason}{e.source && <div className="tw:text-[11px] tw:text-text-tertiary">{e.source}</div>}</td>
                        <td className="nowrap">{formatDateTime(e.added_at)} <Actor email={e.added_by} prefix="by" /></td>
                        <td className="text-end"><button className="btn btn-sm app-btn-ghost-danger" onClick={() => setRemoving(e)}>Remove</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {entries && entries.items.length === 0 && <EmptyState icon={<ListX size={22} />} title="No names" message="Nobody is on this list." />}
              {entries && <Pagination page={page} perPage={PER_PAGE} total={entries.total} onPage={setPage} />}
            </>
          )}
        </div>
      </div>

      <AddEntryModal open={adding} list={view === "matches" ? "internal_blacklist" : view} onClose={() => setAdding(false)} onDone={load} />
      <RemoveEntryModal entry={removing} onClose={() => setRemoving(null)} onDone={load} />
      <ScreeningReviewModal result={review} onClose={() => setReview(null)} onDone={load} />
    </div>
  );
}

function AddEntryModal({ open, list, onClose, onDone }: { open: boolean; list: Watchlist; onClose: () => void; onDone: () => void }) {
  const [which, setWhich] = useState<Watchlist>(list);
  const [name, setName] = useState("");
  const [idNo, setIdNo] = useState("");
  const [reason, setReason] = useState("");
  const [source, setSource] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) { setWhich(list); setName(""); setIdNo(""); setReason(""); setSource(""); } }, [open, list]);
  const submit = async () => {
    setSaving(true);
    try {
      const res = await watchlistService.add({ list: which, full_name: name.trim(), reason: reason.trim(), source: source.trim() || undefined,
        identifiers: idNo.trim() ? [{ id_type: "national_id", value: idNo.trim() }] : [] });
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title="Add a name to a watchlist" open={open} onClose={onClose} onSubmit={submit} submitting={saving}
      submitLabel="Add and screen clients" submitDisabled={!name.trim() || !reason.trim()}>
      <Field label="List">
        <select className="form-select mt-1" value={which} onChange={(e) => setWhich(e.target.value as Watchlist)}>
          <option value="internal_blacklist">{WATCHLIST_LABELS.internal_blacklist}</option>
          <option value="pep">{WATCHLIST_LABELS.pep}</option>
        </select>
      </Field>
      <Field label="Full name"><input className="form-control mt-1" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="ID number" hint="Optional; an exact identifier match is the strongest signal."><input className="form-control mt-1 font-tabular" value={idNo} onChange={(e) => setIdNo(e.target.value)} /></Field>
      <Field label="Reason"><textarea className="form-control mt-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <Field label="Source" hint="e.g. credit committee minute, news report"><input className="form-control mt-1" value={source} onChange={(e) => setSource(e.target.value)} /></Field>
    </Modal>
  );
}

function RemoveEntryModal({ entry, onClose, onDone }: { entry: WatchlistEntry | null; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => setReason(""), [entry]);
  if (!entry) return null;
  const submit = async () => {
    setSaving(true);
    try {
      const res = await watchlistService.remove(entry.id, reason.trim());
      toast.success(res.message);
      onDone();
      onClose();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={`Remove ${entry.full_name}`} open onClose={onClose} onSubmit={submit} submitting={saving} submitVariant="danger"
      submitLabel="Submit for approval" submitDisabled={!reason.trim()}>
      <p style={{ fontSize: 13.5 }}>A second person approves the removal in Approvals; the name stays on the list until then.</p>
      <Field label="Reason"><textarea className="form-control mt-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
    </Modal>
  );
}
