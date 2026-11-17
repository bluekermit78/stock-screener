import yfinance as yf
import pandas as pd
import logging

class DataFetcher:
    def __init__(self, tickers: list):
        self.tickers = tickers

    def fetch_eod_data(self, period="1y") -> dict:
        logging.info(f"Lade EOD-Daten für {len(tickers)} Ticker...")
        data = yf.download(self.tickers, period=period, group_by='ticker', threads=True)
        return data
