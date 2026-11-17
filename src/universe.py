import pandas as pd
import requests
import io
import logging

class UniverseProvider:
    SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    @classmethod
    def get_sp500_tickers(cls) -> list:
        logging.info("Rufe aktuelle S&P 500 Ticker-Liste von Wikipedia ab...")
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) StockScreener/1.0"
        }
        response = requests.get(cls.SP500_URL, headers=headers, timeout=15)
        response.raise_for_status()

        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]

        # Punkte durch Bindestriche ersetzen (z.B. BRK.B -> BRK-B für Yahoo Finance)
        tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
        logging.info(f"{len(tickers)} S&P 500 Ticker erfolgreich geladen.")
        return tickers

    @classmethod
    def get_tickers(cls, config: dict) -> list:
        mode = config.get('universe_mode', 'custom')
        custom_tickers = config.get('universe', [])

        if mode == 'sp500':
            try:
                sp500 = cls.get_sp500_tickers()
                # Optional: Eigene Watchlist-Werte aus config.yaml zusätzlich beimischen
                combined = list(dict.fromkeys(sp500 + custom_tickers))
                return combined
            except Exception as e:
                logging.error(f"Fehler beim Abruf des S&P 500, nutze Fallback aus config.yaml: {e}")
                return custom_tickers

        return custom_tickers
