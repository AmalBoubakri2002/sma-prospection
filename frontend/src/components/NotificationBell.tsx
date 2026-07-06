import { Badge, Dropdown, Empty } from "antd";
import { BellOutlined } from "@ant-design/icons";
import type { NotificationItem } from "@/hooks/useNotifications";
import { C } from "@/styles/tokens";

interface Props {
  notifications: NotificationItem[];
  onMarkRead: (id: string) => void;
  onClickNotification?: (notification: NotificationItem) => void;
}

export default function NotificationBell({ notifications, onMarkRead, onClickNotification }: Props) {
  const unreadCount = notifications.filter((n) => !n.is_read).length;

  const dropdown = (
    <div
      style={{
        width: 340,
        maxHeight: 420,
        overflowY: "auto",
        background: C.surface,
        borderRadius: 12,
        boxShadow: "0 8px 32px rgba(27,58,107,0.18)",
        border: `1px solid ${C.border}`,
      }}
    >
      <div style={{ padding: "14px 16px", borderBottom: `1px solid ${C.border}`, fontWeight: 700, color: C.navy, fontSize: 13.5 }}>
        Notifications
      </div>
      {notifications.length === 0 ? (
        <div style={{ padding: "32px 16px" }}>
          <Empty description="Aucune notification" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      ) : (
        notifications.map((n) => (
          <div
            key={n.id}
            role="button"
            tabIndex={0}
            onClick={() => {
              if (!n.is_read) onMarkRead(n.id);
              onClickNotification?.(n);
            }}
            style={{
              padding: "12px 16px",
              borderBottom: `1px solid ${C.border}`,
              background: n.is_read ? C.surface : "#eef3fc",
              cursor: "pointer",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13, color: C.navy, marginBottom: 3 }}>{n.title}</div>
            <div style={{ fontSize: 12.5, color: C.textMuted, lineHeight: 1.4 }}>{n.message}</div>
            <div style={{ fontSize: 11, color: C.textFaint, marginTop: 5 }}>
              {new Date(n.created_at).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
            </div>
          </div>
        ))
      )}
    </div>
  );

  return (
    <Dropdown trigger={["click"]} placement="bottomRight" dropdownRender={() => dropdown}>
      <Badge count={unreadCount} size="small" offset={[-4, 4]}>
        <button
          aria-label="Notifications"
          style={{
            width:          36,
            height:         36,
            borderRadius:   8,
            border:         "none",
            background:     "transparent",
            display:        "flex",
            alignItems:     "center",
            justifyContent: "center",
            cursor:         "pointer",
            color:          C.textMuted,
            fontSize:       17,
            transition:     "background 0.15s, color 0.15s",
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
    </Dropdown>
  );
}
