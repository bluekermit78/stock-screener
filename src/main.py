import os
import yaml
import logging
from universe import UniverseProvider
from fetcher import DataFetcher
from indicators import TechnicalIndicators
from screener import MarketScreener
from fundamentals import FundamentalAnalyzer
from notifier import Notifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

def main():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    tickers = UniverseProvider.get_tickers(config)
    fetcher = DataFetcher(tickers)
    raw_data = fetcher.fetch_eod_data()

    screener = MarketScreener(config['parameters'])
    tech_signals = []

    for ticker in tickers:
        try:
            if ticker not in raw_data or raw_data[ticker].empty:
                continue
            df = raw_data[ticker].dropna()
            df = TechnicalIndicators.apply_indicators(df, config['parameters'])
            signal = screener.evaluate(ticker, df)
            if signal:
                tech_signals.append(signal)
        except Exception as e:
            logging.error(f"Fehler bei Verarbeitung von {ticker}: {e}")

    # Stufe 1: Top 15 technische Kandidaten vorfiltern
    tech_signals = sorted(tech_signals, key=lambda x: x['score'], reverse=True)[:15]

    # Stufe 2: Fundamentale Prüfung & Re-Scoring für die Top-Kandidaten
    fund_analyzer = FundamentalAnalyzer(config['parameters'])
    final_signals = fund_analyzer.enrich_and_filter(tech_signals)

    # Nach kombiniertem Score sortieren und Top 3 auswählen
    final_signals = sorted(final_signals, key=lambda x: x['score'], reverse=True)
    top_3 = final_signals[:config['parameters']['top_signals_limit']]

    notifier = Notifier(config['notifications'])
    notifier.send_push(top_3)

if __name__ == "__main__":
    main()
