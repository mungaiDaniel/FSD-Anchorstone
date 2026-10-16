import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Building2, UserPlus, Users } from "lucide-react";
import { EmptyState, InvestorCell, LoadingRow, PageHeader, Pagination, SearchField, SegmentedTabs } from "@/components/ui/Page";
import { KycBadge, PartyFlags } from "@/components/clients/ClientBadges";
import { partyService } from "@/services";
import type { KycStatus, Paginated, PartyListItem, PartyType } from "@/lib/types";
import { KYC_STATUS_LABELS, PARTY_ROLE_LABELS, ROUTES } from "@/lib/constants";
import { apiErrorMessage } from "@/lib/utils";
import { useRequestGuard } from "@/lib/useRequestGuard";

const PER_PAGE = 50;
type TypeTab = "" | PartyType;
const TYPE_TABS: { key: TypeTab; label: string }[] = [
  { key: "", label: "All clients" },
  { key: "person", label: "Individuals" },
  { key: "organisation", label: "Organisations" },
];

export default function ClientListPage() {
  const navigate = useNavigate();
  const [type, setType] = useState<TypeTab>("");
  const [kyc, setKyc] = useState<"" | KycStatus>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<PartyListItem> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startRequest = useRequestGuard();

  const load = useCallback(() => {
    const isLatest = startRequest();
    partyService
      .list({ type: type || undefined, kyc_status: kyc || undefined, search: search || undefined, page, per_page: PER_PAGE })
      .then((d) => {
        if (!isLatest()) return;
        setData(d);
        setError(null);
      })
      .catch((err) => isLatest() && setError(apiErrorMessage(err)));
  }, [type, kyc, search, page, startRequest]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  return (
    <div className="app-page">
      <PageHeader
        title="Clients"
        subtitle="One record per person or organisation, whatever their roles: investor, borrower, guarantor, director, next of kin."
        actions={
          <Link to={ROUTES.CLIENT_NEW} className="btn btn-primary btn-sm d-flex align-items-center gap-1">
            <UserPlus size={14} /> New client
          </Link>
        }
      />

      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <SegmentedTabs label="Client type" items={TYPE_TABS} value={type} onChange={(k) => { setType(k); setPage(1); }} />
        <select className="form-select form-select-sm tw:w-auto" aria-label="KYC status" value={kyc}
          onChange={(e) => { setKyc(e.target.value as "" | KycStatus); setPage(1); }}>
          <option value="">Any KYC status</option>
          {(Object.keys(KYC_STATUS_LABELS) as KycStatus[]).map((k) => <option key={k} value={k}>{KYC_STATUS_LABELS[k]}</option>)}
        </select>
      </div>

      <div className="card shadow">
        <div className="card-body">
          <SearchField className="mb-3 tw:max-w-md" value={search} label="Search clients"
            placeholder="Name, client no., ID number, KRA PIN, phone or email" onChange={(v) => { setSearch(v); setPage(1); }} />
          {error && <div className="alert alert-danger py-2" style={{ fontSize: 13 }}>{error}</div>}
          <div className="app-table-scroll">
            <table className="table app-table align-middle mb-0">
              <thead>
                <tr><th>Client</th><th>Type</th><th>Roles</th><th>Phone</th><th>Email</th><th>KYC</th></tr>
              </thead>
              <tbody>
                {!data && !error && <LoadingRow colSpan={6} />}
                {data?.items.map((p) => (
                  <tr key={p.id} className="tw:cursor-pointer" onClick={() => navigate(ROUTES.CLIENT_DETAIL(p.id))}>
                    <td><InvestorCell name={p.display_name} code={p.party_no} to={ROUTES.CLIENT_DETAIL(p.id)} /></td>
                    <td className="nowrap tw:text-text-secondary">
                      {p.party_type === "person" ? "Individual" : (
                        <span className="d-inline-flex align-items-center gap-1"><Building2 size={13} /> Organisation</span>)}
                    </td>
                    <td>
                      <div className="d-flex flex-wrap gap-1">
                        {p.roles.length === 0 && <span className="tw:text-text-disabled">—</span>}
                        {p.roles.map((r) => <span key={r} className="app-badge badge-neutral">{PARTY_ROLE_LABELS[r]}</span>)}
                      </div>
                    </td>
                    <td className="nowrap font-tabular tw:text-text-secondary">{p.phone ?? "—"}</td>
                    <td className="tw:text-text-secondary tw:truncate tw:max-w-[220px]">{p.email ?? "—"}</td>
                    <td><div className="d-flex flex-wrap gap-1"><KycBadge status={p.kyc_status} /><PartyFlags party={p} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.items.length === 0 && (
            <EmptyState icon={<Users size={22} />} title="No clients found"
              message={search ? "No client matches this search." : "Add the first client to get started."}
              action={<Link to={ROUTES.CLIENT_NEW} className="btn btn-sm btn-primary">New client</Link>} />
          )}
          {data && <Pagination page={page} perPage={PER_PAGE} total={data.total} onPage={setPage} />}
        </div>
      </div>
    </div>
  );
}
