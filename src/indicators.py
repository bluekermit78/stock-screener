import pandas as pd

class TechnicalIndicators:
    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @classmethod
    def apply_indicators(cls, df: pd.DataFrame, config: dict) -> pd.DataFrame:
        df['SMA_50'] = df['Close'].rolling(window=config['sma_short']).mean()
        df['SMA_200'] = df['Close'].rolling(window=config['sma_long']).mean()
        df['RSI'] = cls.calculate_rsi(df['Close'], period=config['rsi_period'])
        return df
