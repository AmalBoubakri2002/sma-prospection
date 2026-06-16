import { useNavigate, useLocation, Outlet } from "react-router-dom";
import { Avatar, Dropdown, App } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  RocketOutlined,
  TeamOutlined,
  CalendarOutlined,
  LogoutOutlined,
  UserOutlined,
  DownOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "@/stores/authStore";
import NotificationBell from "@/components/NotificationBell";
import { useNotifications } from "@/hooks/useNotifications";
import type { NotificationItem } from "@/hooks/useNotifications";
import api from "@/utils/api";
import { C, S } from "@/styles/tokens";

interface NavItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  path: string;
}

function getNavItems(isActive: boolean): NavItem[] {
  const items: NavItem[] = [
    { key: "dashboard", label: "Tableau de bord", icon: <DashboardOutlined />, path: "/commercial" },
  ];
  if (isActive) {
    items.push(
      { key: "campagnes", label: "Campagnes", icon: <RocketOutlined />,   path: "/commercial/campagnes/nouvelle" },
      { key: "prospects", label: "Prospects", icon: <TeamOutlined />,     path: "/commercial/prospects" },
      { key: "agenda",    label: "Agenda",    icon: <CalendarOutlined />, path: "/commercial/agenda" },
    );
  }
  items.push({ key: "profil", label: "Profil", icon: <UserOutlined />, path: "/commercial/profil" });
  return items;
}

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

function getDisplayName(u: ReturnType<typeof useAuthStore.getState>["user"]): string {
  if (!u) return "";
  if (u.full_name && !/^\d+$/.test(u.full_name.trim())) return u.full_name.trim();
  return u.email?.split("@")[0] ?? "";
}

function getAvatarChar(u: ReturnType<typeof useAuthStore.getState>["user"]): string {
  return getDisplayName(u)[0]?.toUpperCase() ?? "C";
}

export default function CommercialLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, token, clearAuth, setAuth } = useAuthStore();
  const { message } = App.useApp();

  // Le compte peut être approuvé/refusé par un admin pendant que l'utilisateur
  // est déjà connecté : dès que la notification arrive en temps réel, on
  // resynchronise le statut sans attendre un refresh ou un relogin.
  const handleNotification = (notification: NotificationItem) => {
    if (notification.type === "ACCOUNT_APPROVED" || notification.type === "ACCOUNT_REJECTED") {
      if (!token) return;
      api.get("/auth/me").then(({ data }) => {
        setAuth(token, data);
        if (notification.type === "ACCOUNT_APPROVED") {
          message.success("Votre compte a été approuvé ! Vous avez maintenant accès à toutes les fonctionnalités.");
        }
      });
    }
  };

  const { notifications, markRead } = useNotifications(handleNotification);

  const navItems = getNavItems(user?.status === "ACTIVE");

  const activeKey = navItems.find((item) => {
    if (item.path === "/commercial") return location.pathname === "/commercial";
    if (item.key === "campagnes") return location.pathname.startsWith("/commercial/campagnes");
    return location.pathname.startsWith(item.path);
  })?.key;

  const handleLogout = () => { clearAuth(); navigate("/login"); };

  const userMenu: MenuProps["items"] = [
    {
      key: "profile",
      icon: <UserOutlined />,
      label: (
        <div>
          <div style={{ fontWeight: 600, color: C.text, fontSize: 13 }}>
            {getDisplayName(user)}
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
          <NotificationBell notifications={notifications} onMarkRead={markRead} />

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
                {getAvatarChar(user)}
              </Avatar>
              <span style={{ fontSize: 13, fontWeight: 600, color: C.navy, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {getDisplayName(user)}
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
