import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { InvestorForm } from "@/components/forms/InvestorForm";
import { PageHeader } from "@/components/ui/Page";
import { investorService } from "@/services";
import { ROUTES } from "@/lib/constants";
import { apiErrorMessage } from "@/lib/utils";

export default function AddInvestorPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  return (
    <div className="app-page" style={{ maxWidth: 860 }}>
      <PageHeader title="Add investor" subtitle="A client code is assigned automatically. Record their first deposit from the account page." />
      <div className="card shadow">
        <div className="card-body">
          <InvestorForm
            submitLabel="Create investor"
            submitting={submitting}
            onCancel={() => navigate(ROUTES.INVESTORS)}
            onSubmit={async (data) => {
              setSubmitting(true);
              try {
                const res = await investorService.create(data);
                toast.success(res.message);
                navigate(ROUTES.INVESTOR_DETAIL(res.data!.id));
              } catch (err) {
                toast.error(apiErrorMessage(err));
              } finally {
                setSubmitting(false);
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}
