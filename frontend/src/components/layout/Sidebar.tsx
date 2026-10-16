import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { Wordmark } from "@/components/brand/Wordmark";
import { RoleGate } from "./RoleGate";
import { useUI } from "@/context/UIContext";
import {
  LayoutDashboard,
  BookUser,
  ArrowDownToLine,
  ArrowUpFromLine,
  Percent,
  Mail,
  ClipboardCheck,
  Contact,
  ShieldAlert,
  Users,
  ShieldCheck,
  DatabaseBackup,
  Settings,
  FileSpreadsheet,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

const mainNav: NavItem[] = [
  { label: "Overview", path: ROUTES.OVERVIEW, icon: <LayoutDashboard size={17} /> },
  { label: "Clients", path: ROUTES.CLIENTS, icon: <Contact size={17} /> },
  { label: "Investors", path: ROUTES.INVESTORS, icon: <BookUser size={17} /> },
  { label: "Deposits", path: ROUTES.DEPOSITS, icon: <ArrowDownToLine size={17} /> },
  { label: "Withdrawals", path: ROUTES.WITHDRAWALS, icon: <ArrowUpFromLine size={17} /> },
  { label: "Interest", path: ROUTES.INTEREST, icon: <Percent size={17} /> },
  { label: "Emails", path: ROUTES.EMAILS, icon: <Mail size={17} /> },
  { label: "Approvals", path: ROUTES.APPROVALS, icon: <ClipboardCheck size={17} /> },
];

// Administration: Reports for all staff, Audit Log for admins, the rest super admin only.
const reportsNav: NavItem[] = [{ label: "Reports", path: ROUTES.REPORTS, icon: <FileSpreadsheet size={17} /> }];
const adminNav: NavItem[] = [
  { label: "Watchlists", path: ROUTES.WATCHLIST, icon: <ShieldAlert size={17} /> },
  { label: "Audit Log", path: ROUTES.AUDIT_LOG, icon: <ShieldCheck size={17} /> },
];
const superAdminNav: NavItem[] = [
  { label: "Users", path: ROUTES.USERS, icon: <Users size={17} /> },
  { label: "Backups", path: ROUTES.BACKUPS, icon: <DatabaseBackup size={17} /> },
];

export function Sidebar() {
  const { sidebarCollapsed, sidebarMobileOpen, toggleSidebar, setSidebarMobileOpen, isMobile } = useUI();
  const showLabels = isMobile || !sidebarCollapsed;
  const desktopWidth = sidebarCollapsed ? "var(--sidebar-collapsed)" : "var(--sidebar-width)";
  const closeMobile = () => setSidebarMobileOpen(false);
  const navLinkProps = (label: string) =>
    isMobile ? { onClick: closeMobile } : sidebarCollapsed ? { title: label } : {};

  const renderItems = (items: NavItem[]) => (
    <ul className="nav flex-column mb-0">
      {items.map((item) => (
        <li className="nav-item" key={item.path}>
          <NavLink
            to={item.path}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            {...navLinkProps(item.label)}
          >
            <span style={{ flexShrink: 0 }}>{item.icon}</span>
            {showLabels && <span className="text-truncate">{item.label}</span>}
          </NavLink>
        </li>
      ))}
    </ul>
  );

  return (
    <aside
      className={cn(
        "app-sidebar",
        isMobile && "app-sidebar-mobile",
        !isMobile && sidebarCollapsed && "app-sidebar-desktop-collapsed"
      )}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        height: "100vh",
        width: isMobile ? "min(100vw, 280px)" : desktopWidth,
        background: "var(--color-bg-surface)",
        borderRight: "1px solid var(--color-border-subtle)",
        display: "flex",
        flexDirection: "column",
        transition: "transform 0.25s ease, width 0.2s ease",
        zIndex: isMobile ? 1050 : 30,
        overflowX: "hidden",
        transform: isMobile && !sidebarMobileOpen ? "translateX(-100%)" : "translateX(0)",
      }}
      aria-hidden={isMobile ? !sidebarMobileOpen : undefined}
    >
      <div
        style={{
          height: "var(--topbar-height)",
          display: "flex",
          alignItems: "center",
          padding: sidebarCollapsed && !isMobile ? "0 1rem" : "0 1.25rem",
          justifyContent: sidebarCollapsed && !isMobile ? "center" : "space-between",
          borderBottom: "1px solid var(--color-border-subtle)",
          flexShrink: 0,
        }}
      >
        <Wordmark compact={!showLabels} />
        {isMobile && (
          <button
            type="button"
            className="btn p-2 border-0 rounded-2"
            onClick={closeMobile}
            style={{ color: "var(--color-text-secondary)" }}
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        )}
      </div>

      <nav className="sidebar-nav flex-grow-1 py-2 px-2" style={{ overflowY: "auto" }}>
        {renderItems(mainNav)}
        <hr style={{ borderColor: "var(--color-border-default)", margin: "0.75rem 0.5rem" }} />
          {showLabels && (
            <p
              className="mb-2 px-3"
              style={{
                color: "var(--color-text-tertiary)",
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              Administration
            </p>
          )}
        {renderItems(reportsNav)}
        <RoleGate allowedRoles={["admin", "super_admin"]}>{renderItems(adminNav)}</RoleGate>
        <RoleGate allowedRoles={["super_admin"]}>{renderItems(superAdminNav)}</RoleGate>
      </nav>

      <div className="sidebar-nav py-2 px-2" style={{ borderTop: "1px solid var(--color-border-subtle)", flexShrink: 0 }}>
        {renderItems([{ label: "Settings", path: ROUTES.SETTINGS, icon: <Settings size={17} /> }])}
        {!isMobile && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="nav-link w-100 mt-1 d-flex align-items-center"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              justifyContent: sidebarCollapsed ? "center" : "flex-start",
              gap: "0.5rem",
            }}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse to icons"}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            {showLabels && <span>{sidebarCollapsed ? "Expand" : "Collapse"}</span>}
          </button>
        )}
      </div>
    </aside>
  );
}
