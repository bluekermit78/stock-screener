import requests
import logging

class Notifier:
    def __init__(self, config: dict):
        self.endpoint = config['endpoint']

    def send_push(self, top_signals: list):
        if not top_signals:
            logging.info("Keine Signale nach technischer & fundamentaler Prüfung.")
            return

        message = "🚨 **Top 3 Aktiensignale (Technik + Fundamental)**\n\n"
        for idx, sig in enumerate(top_signals, 1):
            fund_info = sig.get('fundamentals', 'n/a')
            currency = "€" if sig['ticker'].endswith(".DE") else "$"
            message += (
                f"{idx}. **{sig['ticker']}** | {sig['price']} {currency} (Score: {sig['score']})\n"
                f"   📈 Technik: {sig['reasons']}\n"
                f"   🏛️ Fundamental: {fund_info}\n\n"
            )

        response = requests.post(
            self.endpoint,
            data=message.encode('utf-8'),
            headers={"Title": "Aktien-Screener Kaufsignale", "Priority": "urgent"}
        )
        if response.status_code == 200:
            logging.info("Push-Benachrichtigung erfolgreich gesendet.")
        else:
            logging.error(f"Fehler beim Senden der Benachrichtigung: {response.text}")
