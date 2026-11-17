import yaml
import logging
from fetcher import DataFetcher
from indicators import TechnicalIndicators
from screener import MarketScreener
from notifier import Notifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)

        tickers = config['universe']
        fetcher = DataFetcher(tickers)
        raw_data = fetcher.fetch_eod_data()

        screener = MarketScreener(config['parameters'])
        signals = []

        for ticker in tickers:
            try:
                df = raw_data[ticker].dropna()
                df = TechnicalIndicators.apply_indicators(df, config['parameters'])
                signal = screener.evaluate(ticker, df)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logging.error(f"Fehler bei Verarbeitung von {ticker}: {e}")

        # Nach Score sortieren und die Top 3 auswählen
        signals = sorted(signals, key=lambda x: x['score'], reverse=True)
        top_3 = signals[:config['parameters']['top_signals_limit']]

        notifier = Notifier(config['notifications'])
        notifier.send_push(top_3)

if __name__ == "__main__":
    main()
