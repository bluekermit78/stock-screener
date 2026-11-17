import pandas as pd
import numpy as np

class TechnicalIndicators:
    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @classmethod
    def apply_indicators(cls, df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
        df = df.copy()
        close = df['Close']
        high = df['High']
        low = df['Low']

        # Gleitende Durchschnitte (Kurz-, Mittel-, Langfrist)
        df['EMA_20'] = close.ewm(span=20, adjust=False).mean()
        df['SMA_50'] = close.rolling(window=50).mean()
        df['SMA_200'] = close.rolling(window=200).mean()

        # RSI (14)
        df['RSI'] = cls.calculate_rsi(close, period=14)

        # MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema_12 - ema_26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

        # Bollinger Bänder (20, 2)
        df['BB_Mid'] = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (2 * bb_std)
        df['BB_Lower'] = df['BB_Mid'] - (2 * bb_std)

        # ATR (14) für Volatilität & Stop-Loss-Berechnung
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()

        return df
