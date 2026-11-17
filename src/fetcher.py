import yfinance as yf
import pandas as pd
import logging
import os

# Eigener Cache-Ordner für die Zeitzonen-SQLite-DB im Projektverzeichnis
cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".yf_cache")
os.makedirs(cache_dir, exist_ok=True)
yf.set_tz_cache_location(cache_dir)

class DataFetcher:
    def __init__(self, tickers: list):
        self.tickers = tickers

    def fetch_eod_data(self, period="1y") -> dict:
        logging.info(f"Lade EOD-Daten für {len(self.tickers)} Ticker...")
        # threads=False verhindert SQLite Race-Conditions beim Schreiben der Zeitzonen-DB zuverlässig
        data = yf.download(self.tickers, period=period, group_by='ticker', threads=False)
        return data
