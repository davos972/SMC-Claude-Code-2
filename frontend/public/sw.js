// Service Worker for GoldFlow SMC push notifications
// Receives messages from the app and shows native browser notifications

self.addEventListener("message", (event) => {
    const { title, body, icon, tag } = event.data || {};
    if (title) {
        self.registration.showNotification(title, {
            body: body || "",
            icon: icon || "/favicon.ico",
            tag: tag || "goldflow",
            renotify: true,
        });
    }
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: "window" }).then((clientList) => {
            for (const client of clientList) {
                if ("focus" in client) return client.focus();
            }
            if (clients.openWindow) return clients.openWindow("/");
        })
    );
});
