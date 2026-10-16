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
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div
        className="w-6 h-6 border-2 rounded-full animate-spin"
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
      { path: ROUTES.SETTINGS, element: withSuspense(SettingsPage) },
      { path: ROUTES.REPORTS, element: withSuspense(ReportsPage) },
    ],
  },

  {
    element: (
      <AdminRoute>
        <AppShell />
      </AdminRoute>
    ),
    children: [{ path: ROUTES.AUDIT_LOG, element: withSuspense(AuditLogPage) }],
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
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--color-bg-base)" }}>
        <div className="text-center">
          <h1 className="text-4xl font-bold mb-2" style={{ color: "var(--color-text-primary)" }}>404</h1>
          <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Page not found</p>
        </div>
      </div>
    ),
  },
];

export const router = createBrowserRouter(routes);
