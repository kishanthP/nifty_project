/* Service worker: shows price-alert notifications even when the app tab is closed.
 *
 * Firebase Cloud Messaging delivers a standard Web Push message to this worker.
 * We display it ourselves, so this file needs no Firebase SDK and no config.
 */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { notification: { title: "Price alert", body: event.data ? event.data.text() : "" } };
  }
  const notification = payload.notification || {};
  const data = payload.data || {};
  const title = notification.title || data.title || "Price alert";

  event.waitUntil(
    self.registration.showNotification(title, {
      body: notification.body || data.body || "",
      icon: notification.icon || "/icon-192.png",
      badge: "/icon-192.png",
      tag: notification.tag || data.alert_id || undefined,
      requireInteraction: notification.requireInteraction ?? true,
      data: { url: data.url || self.location.origin },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || self.location.origin;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(target);
    }),
  );
});
