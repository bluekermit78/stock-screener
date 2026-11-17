import pandas as pd
import requests
import io
import logging

class UniverseProvider:
    URLS = {
        "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "dax": "https://en.wikipedia.org/wiki/DAX",
        "mdax": "https://en.wikipedia.org/wiki/MDAX"
    }
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) StockScreener/1.0"
    }

    @classmethod
    def _fetch_tables(cls, url: str) -> list:
        response = requests.get(url, headers=cls.HEADERS, timeout=15)
        response.raise_for_status()
        return pd.read_html(io.StringIO(response.text))

    @classmethod
    def get_sp500_tickers(cls) -> list:
        logging.info("Lade S&P 500 Ticker von Wikipedia...")
        tables = cls._fetch_tables(cls.URLS["sp500"])
        df = tables[0]
        tickers = df['Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()
        logging.info(f"{len(tickers)} S&P 500 Ticker geladen.")
        return tickers

    @classmethod
    def get_german_index_tickers(cls, index_key: str) -> list:
        logging.info(f"Lade {index_key.upper()} Ticker von Wikipedia...")
        tables = cls._fetch_tables(cls.URLS[index_key])
        
        tickers = []
        for df in tables:
            # Suche nach der Tabelle mit der Spalte 'Ticker' oder 'Ticker symbol'
            col_name = next((col for col in df.columns if 'ticker' in str(col).lower()), None)
            if col_name and len(df) >= 30:
                raw_tickers = df[col_name].dropna().astype(str).tolist()
                for t in raw_tickers:
                    t = t.strip().split()[0]  # Bereinige eventuelle Fußnoten
                    if not t.endswith(".DE"):
                        t = f"{t}.DE"
                    tickers.append(t)
                break

        logging.info(f"{len(tickers)} {index_key.upper()} Ticker geladen.")
        return tickers

    @classmethod
    def get_tickers(cls, config: dict) -> list:
        # Unterstützt Liste unter 'markets' oder den bisherigen String 'universe_mode'
        markets = config.get('markets', [config.get('universe_mode', 'custom')])
        if isinstance(markets, str):
            markets = [markets]

        combined_tickers = []

        for market in markets:
            market = market.lower()
            try:
                if market == 'sp500':
                    combined_tickers.extend(cls.get_sp500_tickers())
                elif market in ('dax', 'mdax'):
                    combined_tickers.extend(cls.get_german_index_tickers(market))
                elif market == 'custom':
                    combined_tickers.extend(config.get('universe', []))
            except Exception as e:
                logging.error(f"Fehler beim Laden von '{market}': {e}")

        # Fallback auf custom universe, falls alle Abrufe fehlschlagen
        if not combined_tickers:
            logging.warning("Keine Index-Ticker geladen, nutze Fallback-Liste aus config.yaml.")
            combined_tickers = config.get('universe', [])

        # Duplikate entfernen unter Beibehaltung der Reihenfolge
        unique_tickers = list(dict.fromkeys(combined_tickers))
        logging.info(f"Gesamtes Screening-Universum: {len(unique_tickers)} Aktien.")
        return unique_tickers
