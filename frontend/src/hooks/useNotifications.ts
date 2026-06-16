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

const RECONNECT_DELAY_MS = 3000;

export function useNotifications(onNotification?: (notification: NotificationItem) => void) {
  const token = useAuthStore((s) => s.token);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const onNotificationRef = useRef(onNotification);
  onNotificationRef.current = onNotification;

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
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}/api/v1/notifications/ws?token=${encodeURIComponent(token)}`);

      socket.onmessage = (event) => {
        try {
          const notification: NotificationItem = JSON.parse(event.data);
          setNotifications((prev) => [notification, ...prev]);
          onNotificationRef.current?.(notification);
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
