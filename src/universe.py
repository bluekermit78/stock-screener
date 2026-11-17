import os
import json
import pandas as pd
import requests
import io
import logging
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_CACHE_PATH = os.path.join(BASE_DIR, "data", "metadata_cache.json")

class UniverseProvider:
    URLS = {
        "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "dax": "https://en.wikipedia.org/wiki/DAX",
        "mdax": "https://en.wikipedia.org/wiki/MDAX"
    }
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) StockScreener/1.0"
    }
    # Bekannte delistete oder fehlerhafte Wikipedia-Ticker (z. B. Encavis nach Übernahme)
    IGNORED_TICKERS = {"ECV.DE", "MOR.DE", "VTSC.DE"}

    @classmethod
    def _fetch_tables(cls, url: str) -> list:
        response = requests.get(url, headers=cls.HEADERS, timeout=15)
        response.raise_for_status()
        return pd.read_html(io.StringIO(response.text))

    @staticmethod
    def _clean_de_ticker(raw: str) -> str:
        t = str(raw).strip().split()[0]
        if '.' in t:
            base = t.split('.')[0]
            return f"{base}.DE"
        return t if t.endswith(".DE") else f"{t}.DE"

    @classmethod
    def get_sp500_data(cls) -> dict:
        logging.info("Lade S&P 500 Ticker & Metadaten von Wikipedia...")
        tables = cls._fetch_tables(cls.URLS["sp500"])
        df = tables[0]
        meta = {}
        for _, row in df.iterrows():
            sym = str(row['Symbol']).strip().replace('.', '-')
            if sym in cls.IGNORED_TICKERS:
                continue
            name = str(row.get('Security', sym)).strip()
            sector = str(row.get('GICS Sector', 'Unbekannt')).strip()
            meta[sym] = {"name": name, "sector": sector}
        logging.info(f"{len(meta)} S&P 500 Einträge geladen.")
        return meta

    @classmethod
    def get_german_index_data(cls, index_key: str) -> dict:
        logging.info(f"Lade {index_key.upper()} Ticker & Metadaten von Wikipedia...")
        tables = cls._fetch_tables(cls.URLS[index_key])
        meta = {}

        for df in tables:
            cols_lower = {col: str(col).lower() for col in df.columns}
            ticker_col = next((c for c, l in cols_lower.items() if any(k in l for k in ['ticker', 'symbol'])), None)
            if ticker_col is not None and len(df) >= 10:
                name_col = next((c for c, l in cols_lower.items() if any(k in l for k in ['company', 'name'])), None)
                sector_col = next((c for c, l in cols_lower.items() if any(k in l for k in ['sector', 'industry', 'prime standard'])), None)

                for _, row in df.iterrows():
                    raw_t = row[ticker_col]
                    if pd.isna(raw_t):
                        continue
                    t = cls._clean_de_ticker(raw_t)
                    if t in cls.IGNORED_TICKERS:
                        continue
                    name = str(row[name_col]).strip() if (name_col and pd.notna(row[name_col])) else t
                    sector = str(row[sector_col]).strip() if (sector_col and pd.notna(row[sector_col])) else index_key.upper()
                    meta[t] = {"name": name, "sector": sector}
                break

        logging.info(f"{len(meta)} {index_key.upper()} Einträge geladen.")
        return meta

    @classmethod
    def get_universe_with_metadata(cls, config: dict) -> tuple[list, dict]:
        markets = config.get('markets', [config.get('universe_mode', 'custom')])
        if isinstance(markets, str):
            markets = [markets]

        custom_excludes = {str(x).strip().upper() for x in config.get('exclude', [])}
        all_ignored = cls.IGNORED_TICKERS | custom_excludes

        cached_meta = {}
        if os.path.exists(META_CACHE_PATH):
            try:
                with open(META_CACHE_PATH, "r") as f:
                    cached_meta = json.load(f)
            except Exception:
                cached_meta = {}

        combined_meta = {}

        for market in markets:
            market = market.lower()
            try:
                if market == 'sp500':
                    combined_meta.update(cls.get_sp500_data())
                elif market in ('dax', 'mdax'):
                    combined_meta.update(cls.get_german_index_data(market))
                elif market == 'custom':
                    for t in config.get('universe', []):
                        t = str(t).strip().upper()
                        if t in all_ignored:
                            continue
                        if t not in combined_meta:
                            if t in cached_meta and cached_meta[t].get("name") != t:
                                combined_meta[t] = cached_meta[t]
                            else:
                                try:
                                    info = yf.Ticker(t).info
                                    combined_meta[t] = {
                                        "name": info.get("shortName", t),
                                        "sector": info.get("sector", "Custom")
                                    }
                                except Exception:
                                    combined_meta[t] = {"name": t, "sector": "Custom"}
            except Exception as e:
                logging.error(f"Fehler beim Laden von '{market}': {e}")

        # Ausgeschlossene Ticker bereinigen
        for ignored in all_ignored:
            combined_meta.pop(ignored, None)

        if not combined_meta:
            for t in config.get('universe', []):
                t = str(t).strip().upper()
                if t not in all_ignored:
                    combined_meta[t] = cached_meta.get(t, {"name": t, "sector": "Custom"})

        cached_meta.update(combined_meta)
        os.makedirs(os.path.dirname(META_CACHE_PATH), exist_ok=True)
        with open(META_CACHE_PATH, "w") as f:
            json.dump(cached_meta, f, indent=2)

        tickers = list(combined_meta.keys())
        logging.info(f"Gesamtes Screening-Universum: {len(tickers)} Aktien inkl. Metadaten.")
        return tickers, combined_meta

    @classmethod
    def get_tickers(cls, config: dict) -> list:
        tickers, _ = cls.get_universe_with_metadata(config)
        return tickers
