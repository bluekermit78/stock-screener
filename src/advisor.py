import pandas as pd

class InvestmentAdvisor:
    @staticmethod
    def _calc_return(series: pd.Series, days: int) -> float:
        if len(series) <= days:
            return 0.0
        return round(((series.iloc[-1] / series.iloc[-1 - days]) - 1) * 100, 2)

    @classmethod
    def analyze_ticker(cls, ticker: str, df: pd.DataFrame, fund_data: dict = None) -> dict:
        if df.empty or len(df) < 200:
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(latest['Close'])
        atr = float(latest['ATR']) if pd.notna(latest['ATR']) else close * 0.02

        # Performance-Kennzahlen (Handelstage: 5=1W, 21=1M, 63=3M, 126=6M, 252=1Y)
        perf = {
            "1W": cls._calc_return(df['Close'], 5),
            "1M": cls._calc_return(df['Close'], 21),
            "3M": cls._calc_return(df['Close'], 63),
            "6M": cls._calc_return(df['Close'], 126),
            "1Y": cls._calc_return(df['Close'], min(252, len(df) - 1))
        }

        # 1. KURZFRISTIG (1 - 4 Wochen: Swing-Trading / Rebound & Momentum)
        st_score = 50
        st_reasons = []
        if latest['RSI'] < 32:
            st_score += 25
            st_reasons.append(f"RSI überverkauft ({latest['RSI']:.1f})")
        elif latest['RSI'] > 70:
            st_score -= 20
            st_reasons.append(f"RSI überkauft ({latest['RSI']:.1f})")

        if close <= latest['BB_Lower'] * 1.01:
            st_score += 20
            st_reasons.append("Am unteren Bollinger-Band (Rebound-Chance)")

        if prev['MACD_Hist'] < 0 and latest['MACD_Hist'] > 0:
            st_score += 20
            st_reasons.append("Frisches bullisches MACD-Crossover")
        elif latest['MACD'] > latest['MACD_Signal']:
            st_score += 10
            st_reasons.append("MACD positiv")

        if close > latest['EMA_20']:
            st_score += 10
            st_reasons.append("Kurs über EMA 20")

        # 2. MITTELFRISTIG (1 - 6 Monate: Positions-Trading / Trendfolge)
        mt_score = 50
        mt_reasons = []
        if close > latest['SMA_50']:
            mt_score += 15
            mt_reasons.append("Über SMA 50")
        else:
            mt_score -= 10

        if latest['SMA_50'] > df['SMA_50'].iloc[-10]:
            mt_score += 15
            mt_reasons.append("SMA 50 steigt")

        if perf["3M"] > 5.0:
            mt_score += 15
            mt_reasons.append(f"Starkes 3M-Momentum (+{perf['3M']}%)")
        elif perf["3M"] < -10.0:
            mt_score -= 15

        if 45 <= latest['RSI'] <= 65 and close > latest['SMA_50']:
            mt_score += 10
            mt_reasons.append("Gesunder Trend-RSI")

        # 3. LANGFRISTIG (6+ Monate: Strategisches Investment & Fundamental)
        lt_score = 50
        lt_reasons = []
        if close > latest['SMA_200']:
            lt_score += 20
            lt_reasons.append("Über SMA 200 (Primärtrend intakt)")
        else:
            lt_score -= 15
            lt_reasons.append("Unter SMA 200")

        if latest['SMA_50'] > latest['SMA_200']:
            lt_score += 15
            lt_reasons.append("Golden-Cross-Struktur (SMA 50 > SMA 200)")

        if fund_data:
            pe = fund_data.get('pe')
            fcf_yield = fund_data.get('fcf_yield')
            rev_growth = fund_data.get('rev_growth')
            if pe and 0 < pe < 22:
                lt_score += 10
                lt_reasons.append(f"Attraktives KGV ({pe:.1f})")
            if fcf_yield and fcf_yield > 4.0:
                lt_score += 15
                lt_reasons.append(f"Hohe FCF-Rendite ({fcf_yield:.1f}%)")
            if rev_growth and rev_growth > 0.08:
                lt_score += 10
                lt_reasons.append(f"Umsatzwachstum +{rev_growth*100:.1f}%")

        st_score = max(0, min(100, st_score))
        mt_score = max(0, min(100, mt_score))
        lt_score = max(0, min(100, lt_score))
        total_score = round((st_score * 0.35) + (mt_score * 0.35) + (lt_score * 0.30), 1)

        # Risikomanagement (ATR-basiert)
        stop_loss = round(close - (2.0 * atr), 2)
        take_profit = round(close + (3.5 * atr), 2)

        return {
            "ticker": ticker,
            "price": round(close, 2),
            "currency": "€" if ticker.endswith(".DE") else "$",
            "rsi": round(float(latest['RSI']), 1),
            "perf": perf,
            "short_term": {"score": st_score, " verdict": cls._verdict(st_score), "reasons": st_reasons},
            "mid_term": {"score": mt_score, "verdict": cls._verdict(mt_score), "reasons": mt_reasons},
            "long_term": {"score": lt_score, "verdict": cls._verdict(lt_score), "reasons": lt_reasons},
            "total_score": total_score,
            "overall_verdict": cls._verdict(total_score),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": round(atr, 2)
        }

    @staticmethod
    def _verdict(score: float) -> str:
        if score >= 75:
            return "🟢 Starker Kauf"
        elif score >= 60:
            return "🟢 Kauf"
        elif score >= 45:
            return "🟡 Halten"
        else:
            return "🔴 Verkauf / Meiden"
