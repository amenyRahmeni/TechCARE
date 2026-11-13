"use strict";

(() => {
  const body = document.body;
  if (!body.dataset.notificationFeed) return;
  let cursor = Number(body.dataset.notificationLatest || 0);
  let timer, inFlight = false;
  const settings = document.querySelector("[data-push-settings]");
  const canPush = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;
  const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;

  function updateCount(count) {
    document.querySelectorAll("[data-notification-count]").forEach(element => {
      element.hidden = count === 0;
      element.textContent = count > 99 ? "99+" : String(count);
    });
    document.querySelectorAll("[data-notification-bell]").forEach(element => {
      element.setAttribute("aria-label", count ? `Notifications, ${count} non lues` : "Notifications");
    });
  }

  function toast(item) {
    let region = document.querySelector(".notification-toast-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "notification-toast-region";
      region.setAttribute("aria-live", "polite");
      body.append(region);
    }
    const card = document.createElement("div");
    card.className = "notification-live-toast";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.title;
    const message = document.createElement("p");
    message.textContent = item.message;
    const link = document.createElement("a");
    link.href = "/notifications/?notification=" + Number(item.id);
    link.textContent = "Consulter la notification";
    content.append(title, message, link);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "icon-button";
    close.setAttribute("aria-label", "Fermer la notification");
    close.textContent = "×";
    close.addEventListener("click", () => card.remove());
    card.append(content, close);
    region.prepend(card);
    while (region.children.length > 3) region.lastElementChild.remove();
    window.setTimeout(() => card.remove(), 12000);
  }

  async function poll() {
    clearTimeout(timer);
    if (document.hidden || inFlight) return;
    inFlight = true;
    try {
      const response = await fetch(body.dataset.notificationFeed + "?since=" + cursor, {credentials: "same-origin", headers: {"Accept": "application/json"}, cache: "no-store"});
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return;
      const data = await response.json();
      updateCount(data.unread);
      if (Array.isArray(data.items) && data.items.length) {
        const banner = document.querySelector("[data-notification-new]");
        if (banner) banner.hidden = false;
        // Browser notifications are delivered by the service worker; no duplicate toast.
        if (!(canPush && Notification.permission === "granted")) data.items.slice(-3).forEach(toast);
      }
      cursor = Math.max(cursor, Number(data.latest) || 0);
    } catch { /* The persistent inbox remains available after a temporary network error. */ }
    finally { inFlight = false; if (!document.hidden) timer = window.setTimeout(poll, 20000); }
  }
  document.addEventListener("visibilitychange", () => document.hidden ? clearTimeout(timer) : poll());
  window.addEventListener("pageshow", () => poll());
  if ("serviceWorker" in navigator) navigator.serviceWorker.addEventListener("message", event => {
    if (event.data?.type === "techcare-notification") poll();
  });
  document.querySelector("[data-notification-refresh]")?.addEventListener("click", () => location.reload());
  const highlighted = document.querySelector(".notification-row.is-highlighted");
  if (highlighted) highlighted.scrollIntoView({block: "center"});
  poll();

  if (!settings) return;
  const enable = settings.querySelector("[data-enable-push]");
  const disable = settings.querySelector("[data-disable-push]");
  const status = settings.querySelector("[data-push-status]");
  function say(message, error = false) { status.textContent = message; status.classList.toggle("is-error", error); }
  function enabled(value) { if (enable) enable.hidden = value; if (disable) disable.hidden = !value; }
  function keyBytes(value) {
    const encoded = atob(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4));
    return Uint8Array.from(encoded, char => char.charCodeAt(0));
  }
  async function post(url, data = {}) {
    const response = await fetch(url, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf}, body: JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.error || "La modification n’a pas abouti."); error.renew = result.renew; throw error; }
    return result;
  }
  if (!canPush) {
    say("Ce navigateur ne permet pas les alertes système ici. Vos notifications restent disponibles dans votre espace.");
    if (enable) enable.disabled = true;
  } else if (Notification.permission === "denied") {
    say("Les notifications sont bloquées dans les paramètres de ce navigateur. Vous pouvez y modifier votre autorisation.");
  }
  enable?.addEventListener("click", async () => {
    if (!canPush) return;
    enable.disabled = true;
    try {
      // Permission is requested only as a direct result of the user's click.
      const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
      if (permission !== "granted") { say("Les alertes navigateur restent désactivées. Votre centre de notifications est toujours disponible."); return; }
      say("Activation des alertes…");
      const registration = await navigator.serviceWorker.register(settings.dataset.workerUrl, {scope: "/"});
      await navigator.serviceWorker.ready;
      const options = {userVisibleOnly: true, applicationServerKey: keyBytes(settings.dataset.publicKey)};
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) subscription = await registration.pushManager.subscribe(options);
      try { await post(settings.dataset.subscribeUrl, subscription.toJSON()); }
      catch (error) {
        if (!error.renew) throw error;
        await subscription.unsubscribe();
        subscription = await registration.pushManager.subscribe(options);
        await post(settings.dataset.subscribeUrl, subscription.toJSON());
      }
      enabled(true);
      say("Les prochaines alertes seront envoyées sur ce navigateur.");
    } catch (error) { say(error.name === "NotAllowedError" ? "L’autorisation de recevoir les alertes n’a pas été accordée." : "Activation impossible pour le moment. " + (error.message || "Réessayez dans quelques instants."), true); }
    finally { enable.disabled = false; }
  });
  disable?.addEventListener("click", async () => {
    disable.disabled = true;
    try {
      await post(settings.dataset.unsubscribeUrl);
      if (canPush) {
        const registration = await navigator.serviceWorker.getRegistration("/");
        const subscription = registration && await registration.pushManager.getSubscription();
        if (subscription) await subscription.unsubscribe();
        if (registration) (await registration.getNotifications()).forEach(item => item.close());
      }
      enabled(false);
      say("Les alertes de ce navigateur sont désactivées. Vos notifications restent dans votre espace.");
    } catch { say("La désactivation n’a pas abouti. Réessayez dans quelques instants.", true); }
    finally { disable.disabled = false; }
  });
})();
