import yfinance as yf
import logging

class FundamentalAnalyzer:
    def __init__(self, config: dict):
        self.max_pe = config.get('max_forward_pe', 35.0)
        self.min_fcf_yield = config.get('min_fcf_yield_pct', 2.0)
        self.require_positive_fcf = config.get('require_positive_fcf', True)

    def enrich_and_filter(self, signals: list) -> list:
        logging.info(f"Prüfe Fundamentaldaten für {len(signals)} technische Signale...")
        valid_signals = []

        for sig in signals:
            ticker = sig['ticker']
            try:
                info = yf.Ticker(ticker).info
                forward_pe = info.get('forwardPE')
                trailing_pe = info.get('trailingPE')
                pe = forward_pe if forward_pe is not None else trailing_pe

                fcf = info.get('freeCashflow')
                mcap = info.get('marketCap')
                rev_growth = info.get('revenueGrowth')

                fcf_yield = (fcf / mcap * 100) if (fcf and mcap) else None

                # Harter Filter 1: Negativer Free Cash Flow (optional ausschließen)
                if self.require_positive_fcf and fcf is not None and fcf <= 0:
                    logging.info(f"Sortiere {ticker} aus: Negativer Free Cash Flow ({fcf})")
                    continue

                # Harter Filter 2: KGV zu hoch (oder negativ bei Verlusten)
                if pe is not None and (pe <= 0 or pe > self.max_pe):
                    logging.info(f"Sortiere {ticker} aus: KGV ({pe:.1f}) außerhalb des Rahmens (0 - {self.max_pe})")
                    continue

                # Harter Filter 3: Mindest-FCF-Rendite
                if fcf_yield is not None and fcf_yield < self.min_fcf_yield:
                    logging.info(f"Sortiere {ticker} aus: FCF-Rendite ({fcf_yield:.1f}%) unter Minimum ({self.min_fcf_yield}%)")
                    continue

                # Fundamental-Scoring (Bonus für starke Kennzahlen)
                fund_reasons = []
                if pe is not None:
                    fund_reasons.append(f"KGV: {pe:.1f}")
                    if pe < 20:
                        sig['score'] += 5

                if fcf_yield is not None:
                    fund_reasons.append(f"FCF-Yield: {fcf_yield:.1f}%")
                    if fcf_yield > 5.0:
                        sig['score'] += 10

                if rev_growth is not None and rev_growth > 0:
                    fund_reasons.append(f"Rev-Growth: +{rev_growth*100:.1f}%")
                    if rev_growth > 0.10:
                        sig['score'] += 5

                sig['score'] = round(sig['score'], 2)
                sig['fundamentals'] = " | ".join(fund_reasons) if fund_reasons else "Keine Daten"
                valid_signals.append(sig)

            except Exception as e:
                logging.error(f"Fehler bei Fundamentaldaten für {ticker}: {e}")
                sig['fundamentals'] = "Abruffehler"
                valid_signals.append(sig)

        return valid_signals
