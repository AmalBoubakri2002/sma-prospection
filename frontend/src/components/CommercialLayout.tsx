import { useNavigate, useLocation, Outlet } from "react-router-dom";
import { Avatar, Dropdown, Badge } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  TeamOutlined,
  CalendarOutlined,
  BarChartOutlined,
  LogoutOutlined,
  BellOutlined,
  UserOutlined,
  DownOutlined,
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
  { key: "dashboard", label: "Tableau de bord", icon: <DashboardOutlined />, path: "/commercial" },
  { key: "prospects", label: "Prospects",        icon: <TeamOutlined />,      path: "/commercial/prospects" },
  { key: "agenda",    label: "Agenda",            icon: <CalendarOutlined />,  path: "/commercial/agenda" },
  { key: "stats",     label: "Statistiques",      icon: <BarChartOutlined />,  path: "/commercial/stats" },
];

function ProspectLogo() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="url(#cl-lg)" />
      <circle cx="16" cy="16" r="7.5" stroke="white" strokeWidth="1.8" fill="none" opacity="0.9" />
      <circle cx="16" cy="16" r="4"   stroke="white" strokeWidth="1.6" fill="none" opacity="0.7" />
      <circle cx="16" cy="16" r="1.5" fill="white" />
      <line x1="16" y1="6"  x2="16" y2="9"  stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="16" y1="23" x2="16" y2="26" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="6"  y1="16" x2="9"  y2="16" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <line x1="23" y1="16" x2="26" y2="16" stroke="white" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <defs>
        <linearGradient id="cl-lg" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1b3a6b" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export default function CommercialLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, clearAuth } = useAuthStore();

  const activeKey = navItems.find((item) =>
    item.path === "/commercial"
      ? location.pathname === "/commercial"
      : location.pathname.startsWith(item.path)
  )?.key;

  const handleLogout = () => { clearAuth(); navigate("/login"); };

  const userMenu: MenuProps["items"] = [
    {
      key: "profile",
      icon: <UserOutlined />,
      label: (
        <div>
          <div style={{ fontWeight: 600, color: C.text, fontSize: 13 }}>
            {user?.full_name ?? user?.email?.split("@")[0]}
          </div>
          <div style={{ fontSize: 11, color: C.textMuted }}>{user?.email}</div>
        </div>
      ),
      disabled: true,
    },
    { type: "divider" },
    {
      key: "logout",
      icon: <LogoutOutlined />,
      label: "Déconnexion",
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: C.bg }}>

      {/* ── Top navbar ──────────────────────────────────────── */}
      <header
        aria-label="Navigation principale"
        style={{
          height:       64,
          background:   C.surface,
          display:      "flex",
          alignItems:   "center",
          padding:      "0 32px",
          position:     "sticky",
          top:          0,
          zIndex:       100,
          boxShadow:    S.nav,
          gap:          0,
          flexShrink:   0,
        }}
      >
        {/* Logo */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Aller au tableau de bord"
          onClick={() => navigate("/commercial")}
          onKeyDown={(e) => e.key === "Enter" && navigate("/commercial")}
          style={{
            display:    "flex",
            alignItems: "center",
            gap:        10,
            cursor:     "pointer",
            marginRight:32,
            flexShrink: 0,
            outline:    "none",
            padding:    "4px 0",
            borderRadius: 8,
          }}
        >
          <ProspectLogo />
          <span style={{ fontWeight: 800, fontSize: 15, color: C.navy, letterSpacing: 0.1 }}>
            ProspectAI
          </span>
        </div>

        {/* Nav links — active underline style (SaaS standard) */}
        <nav
          aria-label="Menu commercial"
          style={{ display: "flex", gap: 2, flex: 1, alignItems: "center", height: "100%", paddingTop: 14 }}
        >
          {navItems.map((item) => {
            const isActive = activeKey === item.key;
            return (
              <div
                key={item.key}
                role="button"
                tabIndex={0}
                aria-current={isActive ? "page" : undefined}
                aria-label={item.label}
                className={`top-nav-link${isActive ? " is-active" : ""}`}
                onClick={() => navigate(item.path)}
                onKeyDown={(e) => e.key === "Enter" && navigate(item.path)}
              >
                <span style={{ fontSize: 14 }} aria-hidden="true">{item.icon}</span>
                {item.label}
              </div>
            );
          })}
        </nav>

        {/* Right controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>

          {/* Notifications */}
          <Badge count={0} size="small">
            <button
              aria-label="Notifications"
              style={{
                width:        36,
                height:       36,
                borderRadius: 8,
                border:       "none",
                background:   "transparent",
                display:      "flex",
                alignItems:   "center",
                justifyContent:"center",
                cursor:       "pointer",
                color:        C.textMuted,
                fontSize:     17,
                transition:   "background 0.15s, color 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = C.bg;
                (e.currentTarget as HTMLButtonElement).style.color = C.navy;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                (e.currentTarget as HTMLButtonElement).style.color = C.textMuted;
              }}
            >
              <BellOutlined />
            </button>
          </Badge>

          {/* User menu */}
          <Dropdown menu={{ items: userMenu }} trigger={["click"]} placement="bottomRight">
            <button
              aria-label="Menu utilisateur"
              aria-haspopup="menu"
              style={{
                display:     "flex",
                alignItems:  "center",
                gap:         8,
                cursor:      "pointer",
                padding:     "5px 10px 5px 6px",
                borderRadius:9,
                border:      `1.5px solid ${C.border}`,
                background:  "transparent",
                transition:  "border-color 0.15s, background 0.15s",
                outline:     "none",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = C.borderMd;
                (e.currentTarget as HTMLButtonElement).style.background  = C.bg;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = C.border;
                (e.currentTarget as HTMLButtonElement).style.background  = "transparent";
              }}
            >
              <Avatar
                size={28}
                style={{ background: `linear-gradient(135deg, ${C.navy}, ${C.indigo})`, fontSize: 12, fontWeight: 700, flexShrink: 0 }}
              >
                {(user?.full_name ?? user?.email ?? "C")[0].toUpperCase()}
              </Avatar>
              <span style={{ fontSize: 13, fontWeight: 600, color: C.navy, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user?.full_name ?? user?.email?.split("@")[0]}
              </span>
              <DownOutlined style={{ fontSize: 10, color: C.textMuted }} aria-hidden="true" />
            </button>
          </Dropdown>
        </div>
      </header>

      {/* ── Page content ──────────────────────────────────── */}
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>
    </div>
  );
}
