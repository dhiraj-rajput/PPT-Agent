import { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../lib/api.jsx';
import { useAuth } from './AuthContext.jsx';

const NotificationContext = createContext(null);
const POLL_INTERVAL_MS = 15000; // check for new alerts every 15s

export function NotificationProvider({ children }) {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      setLoading(true);
      const data = await api.listNotifications();
      let notifs = data.notifications || [];
      notifs = notifs.map(n => {
        let link = n.link || '';
        if (link.startsWith('/api/')) {
          link = link.replace('/api/', '/');
        }
        return { ...n, link };
      });
      setNotifications(notifs);
      setUnreadCount(data.unreadCount || 0);
    } catch {
      // Silent — polling shouldn't surface errors to the user.
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (!user) {
      setNotifications([]);
      setUnreadCount(0);
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    refresh();
    timerRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [user, refresh]);

  async function markRead(id) {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await api.markNotificationRead(id);
    } catch {
      refresh();
    }
  }

  async function markAllRead() {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
    try {
      await api.markAllNotificationsRead();
    } catch {
      refresh();
    }
  }

  async function createAlert(title, message = '', link = '', userId = null) {
    const { notification } = await api.createNotification(title, message, link, userId);
    // Only reflect it locally if it landed in our own list (i.e. we alerted ourselves).
    if (!userId) {
      let safeLink = notification.link || '';
      if (safeLink.startsWith('/api/')) {
        safeLink = safeLink.replace('/api/', '/');
        notification.link = safeLink;
      }
      setNotifications((prev) => [notification, ...prev]);
      setUnreadCount((c) => c + 1);
    }
    return notification;
  }

  async function removeNotification(id) {
    const existed = notifications.find((n) => n.id === id);
    setNotifications((prev) => prev.filter((n) => n.id !== id));
    if (existed && !existed.read) setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await api.deleteNotification(id);
    } catch {
      refresh();
    }
  }

  return (
    <NotificationContext.Provider
      value={{ notifications, unreadCount, loading, refresh, markRead, markAllRead, createAlert, removeNotification }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider');
  return ctx;
}
