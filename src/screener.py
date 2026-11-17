import pandas as pd
import numpy as np

class MarketScreener:
    def __init__(self, config: dict):
        self.config = config

    def evaluate(self, ticker: str, df: pd.DataFrame) -> dict:
        if df.empty or len(df) < self.config['sma_long']:
            return None
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Beispiel-Strategie: RSI < 30 (überverkauft) oder Kurs kreuzt SMA_50 nach oben
        rsi = latest['RSI']
        close = latest['Close']
        sma_50 = latest['SMA_50']
        
        # Signalstärke-Metrik (je niedriger der RSI, desto stärker das Kaufsignal)
        score = 0
        signal_reason = []

        if rsi < self.config['rsi_oversold']:
            score += (self.config['rsi_oversold'] - rsi)
            signal_reason.append(f"RSI überverkauft ({rsi:.1f})")

        if prev['Close'] < prev['SMA_50'] and close > sma_50:
            score += 20
            signal_reason.append("Durchbruch SMA 50 nach oben")

        if score > 0:
            return {
                "ticker": ticker,
                "price": round(close, 2),
                "score": round(score, 2),
                "reasons": ", ".join(signal_reason)
            }
        return None
