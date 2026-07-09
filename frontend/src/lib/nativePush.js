// Notifications push natives (app mobile Capacitor uniquement).
// Demande la permission, récupère le jeton FCM du téléphone et l'enregistre
// auprès du backend, qui s'en sert pour pousser chaque notification via Firebase.
import { Capacitor } from "@capacitor/core";
import { api } from "../api/client";

export async function registerNativePush() {
    if (!Capacitor.isNativePlatform()) return;
    try {
        const { PushNotifications } = await import("@capacitor/push-notifications");

        let perm = await PushNotifications.checkPermissions();
        if (perm.receive === "prompt") {
            perm = await PushNotifications.requestPermissions();
        }
        if (perm.receive !== "granted") return;

        // Canal Android (doit correspondre au channel_id envoyé par le backend)
        await PushNotifications.createChannel({
            id: "goldflow",
            name: "GoldFlow SMC",
            description: "Signaux, trades et alertes du bot",
            importance: 4, // haute : bannière + son
            visibility: 1,
        }).catch(() => {});

        PushNotifications.addListener("registration", async ({ value }) => {
            try {
                await api.post("/push/register", { token: value, platform: "android" });
                console.log("Push: téléphone enregistré auprès du backend");
            } catch (e) {
                console.error("Push: échec d'enregistrement du jeton:", e);
            }
        });
        PushNotifications.addListener("registrationError", (err) => {
            console.error("Push: erreur d'enregistrement FCM:", err);
        });

        await PushNotifications.register();
    } catch (e) {
        console.error("Push natif indisponible:", e);
    }
}
