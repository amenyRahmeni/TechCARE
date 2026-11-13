"use strict";

self.addEventListener("push", event => {
  event.waitUntil((async () => {
    let data;
    try { data = event.data.json(); } catch { return; }
    if (!data || !Number.isInteger(data.id) || !Number.isInteger(data.recipient_id)) return;
    // A signed, HttpOnly device cookie binds late deliveries to the current account.
    let response;
    try { response = await fetch("/notifications/push/session/?notification=" + data.id, {credentials: "same-origin", cache: "no-store"}); } catch { return; }
    if (!response.ok) return;
    const session = await response.json();
    if (!session.active || session.user_id !== data.recipient_id) return;
    const target = new URL(data.url || "/notifications/", self.location.origin);
    if (target.origin !== self.location.origin || !target.pathname.startsWith("/notifications/")) return;
    await self.registration.showNotification(String(data.title || "TECHcare"), {
      body: String(data.body || "Une nouvelle notification vous attend."),
      tag: "techcare-" + data.id,
      data: {url: target.href},
    });
    const windows = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    windows.forEach(client => client.postMessage({type: "techcare-notification"}));
  })());
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil((async () => {
    const target = new URL(event.notification.data?.url || "/notifications/", self.location.origin);
    if (target.origin !== self.location.origin || !target.pathname.startsWith("/notifications/")) return;
    const windows = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    const existing = windows.find(client => client.url.startsWith(self.location.origin + "/notifications/"));
    if (existing) { await existing.navigate(target.href); await existing.focus(); }
    else await self.clients.openWindow(target.href);
  })());
});
