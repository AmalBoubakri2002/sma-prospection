import { useState } from "react";
import { useNavigate, useLocation, Outlet } from "react-router-dom";
import { Avatar, Tooltip } from "antd";
import {
  DashboardOutlined,
  TeamOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "@/stores/authStore";
import { C, S } from "@/styles/tokens";

interface NavItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  path: string;
}

const navItems: NavItem[] = [
  { key: "dashboard", label: "Tableau de bord", icon: <DashboardOutlined />, path: "/admin" },
  { key: "users",     label: "Commerciaux",     icon: <TeamOutlined />,      path: "/admin/commerciaux" },
];

const SIDEBAR_W           = 240;
const SIDEBAR_W_COLLAPSED = 64;

function ProspectLogo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="url(#lg)" />
      <circle cx="16" cy="16" r="7.5" stroke="white" strokeWidth="1.8" fill="none" opacity="0.9" />
      <circle cx="16" cy="16" r="4"   stroke="white" strokeWidth="1.6" fill="none" opacity="0.7" />
      <circle cx="16" cy="16" r="1.5" fill="white" />
      <line x1="16" y1="6"  x2="16" y2="9"  stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="16" y1="23" x2="16" y2="26" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="6"  y1="16" x2="9"  y2="16" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="23" y1="16" x2="26" y2="16" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4f6fd0" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate   = useNavigate();
  const location   = useLocation();
  const { user, clearAuth } = useAuthStore();

  const width = collapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W;

  const activeKey = navItems.find((item) =>
    item.path === "/admin"
      ? location.pathname === "/admin"
      : location.pathname.startsWith(item.path)
  )?.key;

  const handleLogout = () => { clearAuth(); navigate("/login"); };

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: C.bg }}>

      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside
        aria-label="Navigation principale"
        style={{
          width,
          minHeight: "100vh",
          background: C.navy,
          display:        "flex",
          flexDirection:  "column",
          transition:     "width 0.2s ease",
          overflow:       "hidden",
          position:       "fixed",
          top: 0, left: 0, bottom: 0,
          zIndex: 100,
          boxShadow: S.sidebar,
        }}
      >
        {/* Logo */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Aller au tableau de bord"
          onClick={() => navigate("/admin")}
          onKeyDown={(e) => e.key === "Enter" && navigate("/admin")}
          style={{
            height: 64,
            display:     "flex",
            alignItems:  "center",
            padding:     collapsed ? "0 0 0 16px" : "0 16px",
            gap:         12,
            overflow:    "hidden",
            cursor:      "pointer",
            flexShrink:  0,
            borderBottom:`1px solid rgba(255,255,255,0.07)`,
            outline:     "none",
          }}
        >
          <ProspectLogo />
          {!collapsed && (
            <span style={{ color: "#fff", fontWeight: 700, fontSize: 15, letterSpacing: 0.1, whiteSpace: "nowrap" }}>
              ProspectAI
            </span>
          )}
        </div>

        {/* Section label */}
        {!collapsed && (
          <div style={{ padding: "20px 20px 8px", fontSize: 10, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", color: "rgba(255,255,255,0.28)" }}>
            Menu
          </div>
        )}

        {/* Nav */}
        <nav aria-label="Menu admin" style={{ flex: 1, padding: "4px 8px" }}>
          {navItems.map((item) => {
            const isActive = activeKey === item.key;
            return (
              <Tooltip key={item.key} title={collapsed ? item.label : ""} placement="right">
                <div
                  role="button"
                  tabIndex={0}
                  aria-current={isActive ? "page" : undefined}
                  aria-label={item.label}
                  className={`sidebar-item${isActive ? " is-active" : ""}${collapsed ? " is-collapsed" : ""}`}
                  onClick={() => navigate(item.path)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(item.path)}
                >
                  <span style={{ fontSize: 16, flexShrink: 0 }} aria-hidden="true">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </div>
              </Tooltip>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", padding: "12px 8px" }}>

          {/* User card */}
          <div style={{
            display:     "flex",
            alignItems:  "center",
            gap:         10,
            padding:     collapsed ? "8px 0" : "8px 12px",
            justifyContent: collapsed ? "center" : "flex-start",
            marginBottom: 8,
            borderRadius: 8,
            background:   "rgba(255,255,255,0.05)",
            overflow:     "hidden",
          }}>
            <Avatar
              size={32}
              style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)", fontSize: 12, fontWeight: 700, flexShrink: 0 }}
              aria-label="Avatar administrateur"
            >
              {(user?.full_name ?? user?.email ?? "A")[0].toUpperCase()}
            </Avatar>
            {!collapsed && (
              <div style={{ overflow: "hidden", minWidth: 0 }}>
                <div style={{ color: "#fff", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {user?.full_name ?? "Admin"}
                </div>
                <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 11, marginTop: 1 }}>Administrateur</div>
              </div>
            )}
          </div>

          {/* Logout */}
          <Tooltip title={collapsed ? "Déconnexion" : ""} placement="right">
            <div
              role="button"
              tabIndex={0}
              aria-label="Déconnexion"
              className={`sidebar-action logout${collapsed ? " is-collapsed" : ""}`}
              onClick={handleLogout}
              onKeyDown={(e) => e.key === "Enter" && handleLogout()}
            >
              <LogoutOutlined style={{ fontSize: 15, flexShrink: 0 }} aria-hidden="true" />
              {!collapsed && <span>Déconnexion</span>}
            </div>
          </Tooltip>

          {/* Collapse toggle */}
          <Tooltip title={collapsed ? "Déplier" : ""} placement="right">
            <div
              role="button"
              tabIndex={0}
              aria-label={collapsed ? "Déplier la barre" : "Réduire la barre"}
              className={`sidebar-action collapse${collapsed ? " is-collapsed" : ""}`}
              onClick={() => setCollapsed((c) => !c)}
              onKeyDown={(e) => e.key === "Enter" && setCollapsed((c) => !c)}
            >
              {collapsed
                ? <MenuUnfoldOutlined style={{ fontSize: 15 }} aria-hidden="true" />
                : (<><MenuFoldOutlined style={{ fontSize: 15 }} aria-hidden="true" /><span>Réduire</span></>)
              }
            </div>
          </Tooltip>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────── */}
      <div style={{ marginLeft: width, flex: 1, transition: "margin-left 0.2s ease", minHeight: "100vh" }}>
        <Outlet />
      </div>
    </div>
  );
}
