import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { SuperAdminRoute } from "./SuperAdminRoute";
import { AdminRoute } from "./AdminRoute";
import { AppShell } from "@/components/layout/AppShell";
import LoginPage from "@/pages/auth/LoginPage";
import ChangePasswordPage from "@/pages/auth/ChangePasswordPage";
import { ROUTES } from "@/lib/constants";

const OverviewPage = lazy(() => import("@/pages/dashboard/OverviewPage"));
const InvestorDirectoryPage = lazy(() => import("@/pages/investors/InvestorDirectoryPage"));
const AddInvestorPage = lazy(() => import("@/pages/investors/AddInvestorPage"));
const InvestorDetailPage = lazy(() => import("@/pages/investors/InvestorDetailPage"));
const DepositsPage = lazy(() => import("@/pages/deposits/DepositsPage"));
const WithdrawalsPage = lazy(() => import("@/pages/withdrawals/WithdrawalsPage"));
const InterestPage = lazy(() => import("@/pages/interest/InterestPage"));
const InterestPeriodPage = lazy(() => import("@/pages/interest/InterestPeriodPage"));
const EmailsPage = lazy(() => import("@/pages/emails/EmailsPage"));
const UserManagementPage = lazy(() => import("@/pages/users/UserManagementPage"));
const AuditLogPage = lazy(() => import("@/pages/audit/AuditLogPage"));
const BackupsPage = lazy(() => import("@/pages/backups/BackupsPage"));
const ReportsPage = lazy(() => import("@/pages/reports/ReportsPage"));
const ApprovalsPage = lazy(() => import("@/pages/approvals/ApprovalsPage"));
const ClientListPage = lazy(() => import("@/pages/clients/ClientListPage"));
const ClientFormPage = lazy(() => import("@/pages/clients/ClientFormPage"));
const ClientDetailPage = lazy(() => import("@/pages/clients/ClientDetailPage"));
const WatchlistPage = lazy(() => import("@/pages/clients/WatchlistPage"));
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));
const ApplicationListPage = lazy(() => import("@/pages/applications/ApplicationListPage"));
const ApplicationFormPage = lazy(() => import("@/pages/applications/ApplicationFormPage"));
const ApplicationDetailPage = lazy(() => import("@/pages/applications/ApplicationDetailPage"));
const ReviewExtractionPage = lazy(() => import("@/pages/applications/ReviewExtractionPage"));
const AiOversightPage = lazy(() => import("@/pages/settings/AiOversightPage"));

function PageLoader() {
  return (
    <div className="tw:flex tw:items-center tw:justify-center tw:h-64">
      <div
        className="tw:w-6 tw:h-6 tw:border-2 tw:rounded-full tw:animate-spin"
        style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }}
      />
    </div>
  );
}

function withSuspense(Component: React.LazyExoticComponent<React.ComponentType>) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

const routes: RouteObject[] = [
  { path: "/", element: <Navigate to={ROUTES.OVERVIEW} replace /> },
  { path: ROUTES.LOGIN, element: <LoginPage /> },
  { path: ROUTES.CHANGE_PASSWORD, element: <ChangePasswordPage /> },

  {
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { path: ROUTES.OVERVIEW, element: withSuspense(OverviewPage) },
      { path: ROUTES.INVESTORS, element: withSuspense(InvestorDirectoryPage) },
      { path: ROUTES.INVESTOR_ADD, element: withSuspense(AddInvestorPage) },
      { path: "/investors/:id", element: withSuspense(InvestorDetailPage) },
      { path: ROUTES.DEPOSITS, element: withSuspense(DepositsPage) },
      { path: ROUTES.WITHDRAWALS, element: withSuspense(WithdrawalsPage) },
      { path: ROUTES.INTEREST, element: withSuspense(InterestPage) },
      { path: "/interest/periods/:id", element: withSuspense(InterestPeriodPage) },
      { path: ROUTES.EMAILS, element: withSuspense(EmailsPage) },
      { path: ROUTES.APPROVALS, element: withSuspense(ApprovalsPage) },
      { path: ROUTES.CLIENTS, element: withSuspense(ClientListPage) },
      { path: ROUTES.CLIENT_NEW, element: withSuspense(ClientFormPage) },
      { path: "/clients/:id", element: withSuspense(ClientDetailPage) },
      { path: "/clients/:id/edit", element: withSuspense(ClientFormPage) },
      { path: ROUTES.SETTINGS, element: withSuspense(SettingsPage) },
      { path: ROUTES.REPORTS, element: withSuspense(ReportsPage) },
      { path: ROUTES.APPLICATIONS, element: withSuspense(ApplicationListPage) },
      { path: ROUTES.APPLICATION_NEW, element: withSuspense(ApplicationFormPage) },
      { path: "/applications/:id", element: withSuspense(ApplicationDetailPage) },
    ],
  },

  {
    element: (
      <AdminRoute>
        <AppShell />
      </AdminRoute>
    ),
    children: [
      { path: ROUTES.AUDIT_LOG, element: withSuspense(AuditLogPage) },
      { path: ROUTES.WATCHLIST, element: withSuspense(WatchlistPage) },
      { path: "/readings/:id/review", element: withSuspense(ReviewExtractionPage) },
      { path: ROUTES.AI_OVERSIGHT, element: withSuspense(AiOversightPage) },
    ],
  },

  {
    element: (
      <SuperAdminRoute>
        <AppShell />
      </SuperAdminRoute>
    ),
    children: [
      { path: ROUTES.USERS, element: withSuspense(UserManagementPage) },
      { path: ROUTES.BACKUPS, element: withSuspense(BackupsPage) },
    ],
  },

  { path: "/dashboard", element: <Navigate to={ROUTES.OVERVIEW} replace /> },
  {
    path: "*",
    element: (
      <div className="tw:min-h-screen tw:flex tw:items-center tw:justify-center" style={{ background: "var(--color-bg-base)" }}>
        <div className="text-center">
          <h1 className="tw:text-4xl tw:font-bold tw:mb-2" style={{ color: "var(--color-text-primary)" }}>404</h1>
          <p className="tw:text-sm" style={{ color: "var(--color-text-secondary)" }}>Page not found</p>
        </div>
      </div>
    ),
  },
];

export const router = createBrowserRouter(routes);
