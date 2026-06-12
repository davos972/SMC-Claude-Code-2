// Browser push notification helpers (works with app closed via Service Worker)

let swRegistration = null;

export async function registerServiceWorker() {
    if (!("serviceWorker" in navigator) || !("Notification" in window)) return;
    try {
        swRegistration = await navigator.serviceWorker.register("/sw.js");
    } catch (e) {
        console.warn("SW registration failed:", e);
    }
}

export async function requestPermission() {
    if (!("Notification" in window)) return "denied";
    if (Notification.permission === "granted") return "granted";
    return await Notification.requestPermission();
}

export function sendPushNotification({ title, body, tag }) {
    if (!swRegistration || Notification.permission !== "granted") return;
    swRegistration.active?.postMessage({ title, body, tag });
}
