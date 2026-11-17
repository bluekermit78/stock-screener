import os
import json
import yaml
import logging
from datetime import datetime
from universe import UniverseProvider
from fetcher import DataFetcher
from indicators import TechnicalIndicators
from screener import MarketScreener
from fundamentals import FundamentalAnalyzer
from advisor import InvestmentAdvisor
from notifier import Notifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DATA_PATH = os.path.join(BASE_DIR, "data", "latest_analysis.json")

def main():
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    tickers, metadata = UniverseProvider.get_universe_with_metadata(config)
    fetcher = DataFetcher(tickers)
    raw_data = fetcher.fetch_eod_data(period="2y")

    screener = MarketScreener(config['parameters'])
    tech_signals = []
    full_market_overview = []

    for ticker in tickers:
        try:
            if ticker not in raw_data or raw_data[ticker].empty:
                continue
            # Nur Tage ohne Schlusskurs entfernen (verhindert Datenverlust bei US/EU-Feiertagen)
            df = raw_data[ticker].dropna(subset=['Close', 'High', 'Low']).copy()
            if len(df) < 200:
                continue

            df = TechnicalIndicators.apply_indicators(df, config['parameters'])
            meta = metadata.get(ticker, {"name": ticker, "sector": "Unbekannt"})

            adv = InvestmentAdvisor.analyze_ticker(ticker, df)
            if adv:
                full_market_overview.append({
                    "ticker": adv['ticker'],
                    "name": meta.get("name", ticker),
                    "sector": meta.get("sector", "Unbekannt"),
                    "price": adv['price'],
                    "1W %": adv['perf']['1W'],
                    "1M %": adv['perf']['1M'],
                    "3M %": adv['perf']['3M'],
                    "1Y %": adv['perf']['1Y'],
                    "rsi": adv['rsi'],
                    "short_term": adv['short_term'][' verdict'],
                    "mid_term": adv['mid_term']['verdict'],
                    "long_term": adv['long_term']['verdict'],
                    "total_score": adv['total_score'],
                    "overall_verdict": adv['overall_verdict'],
                    "stop_loss": adv['stop_loss'],
                    "take_profit": adv['take_profit']
                })

            signal = screener.evaluate(ticker, df)
            if signal:
                signal['name'] = meta.get("name", ticker)
                tech_signals.append(signal)
        except Exception as e:
            logging.error(f"Fehler bei Verarbeitung von {ticker}: {e}")

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "results": full_market_overview
        }, f, indent=2)

    tech_signals = sorted(tech_signals, key=lambda x: x['score'], reverse=True)[:15]
    fund_analyzer = FundamentalAnalyzer(config['parameters'])
    final_signals = fund_analyzer.enrich_and_filter(tech_signals)

    final_signals = sorted(final_signals, key=lambda x: x['score'], reverse=True)
    top_3 = final_signals[:config['parameters']['top_signals_limit']]

    notifier = Notifier(config['notifications'])
    notifier.send_push(top_3)

if __name__ == "__main__":
    main()
