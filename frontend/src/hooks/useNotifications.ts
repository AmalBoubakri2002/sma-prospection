import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/stores/authStore";
import api from "@/utils/api";

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  related_user_id: string | null;
  created_at: string;
}

export interface CampaignUpdate {
  campaign_id: string;
  status: string;
}

const RECONNECT_DELAY_MS = 3000;

export function useNotifications(
  onNotification?: (notification: NotificationItem) => void,
  onCampaignUpdate?: (update: CampaignUpdate) => void,
) {
  const token = useAuthStore((s) => s.token);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const onNotificationRef = useRef(onNotification);
  onNotificationRef.current = onNotification;
  const onCampaignUpdateRef = useRef(onCampaignUpdate);
  onCampaignUpdateRef.current = onCampaignUpdate;

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const fetchNotifications = () => {
      api.get<NotificationItem[]>("/notifications/")
        .then((res) => { if (!cancelled) setNotifications(res.data); })
        .catch(() => {});
    };

    const connect = () => {
      if (cancelled) return;
      // Même logique que utils/api.ts : en prod, le backend vit sur une autre
      // origine que le frontend (VITE_API_URL), donc le host du WS ne peut pas
      // être déduit de window.location comme en dev (proxy Vite same-origin).
      const backendUrl = import.meta.env.VITE_API_URL;
      const host = backendUrl ? new URL(backendUrl).host : window.location.host;
      const proto = (backendUrl ? new URL(backendUrl).protocol : window.location.protocol) === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${host}/api/v1/notifications/ws?token=${encodeURIComponent(token)}`);

      socket.onmessage = (event) => {
        try {
          // Contrat du bus (voir backend notification_bus.py) : chaque message
          // porte un "kind" — notification (cloche) ou campaign_update (pages).
          const msg = JSON.parse(event.data);
          if (msg.kind === "campaign_update") {
            onCampaignUpdateRef.current?.(msg.data as CampaignUpdate);
          } else if (msg.kind === "notification") {
            const notification = msg.data as NotificationItem;
            setNotifications((prev) => [notification, ...prev]);
            onNotificationRef.current?.(notification);
          }
        } catch {
          // payload inattendu, on l'ignore
        }
      };

      socket.onclose = () => {
        if (!cancelled) reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    };

    fetchNotifications();
    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  const markRead = async (id: string) => {
    try {
      await api.patch(`/notifications/${id}/read`);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch {
      // ignore — la notification restera affichée comme non lue
    }
  };

  return { notifications, markRead };
}
