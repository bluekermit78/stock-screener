import yfinance as yf
import pandas as pd
import numpy as np

class IntradayAnalyzer:
    @staticmethod
    def fetch_intraday_data(ticker: str, interval: str = "5m", period: str = "5d") -> tuple[pd.DataFrame, dict]:
        t = yf.Ticker(ticker)
        df_intra = t.history(period=period, interval=interval)
        df_daily = t.history(period="5d", interval="1d")

        if df_intra.empty or len(df_daily) < 2:
            return pd.DataFrame(), {}

        prev_day = df_daily.iloc[-2]
        ph, pl, pc = float(prev_day['High']), float(prev_day['Low']), float(prev_day['Close'])
        pivot = (ph + pl + pc) / 3.0
        r1 = (2 * pivot) - pl
        s1 = (2 * pivot) - ph
        r2 = pivot + (ph - pl)
        s2 = pivot - (ph - pl)

        pivots = {
            "P": round(pivot, 2),
            "R1": round(r1, 2),
            "R2": round(r2, 2),
            "S1": round(s1, 2),
            "S2": round(s2, 2),
            "Prev_Close": round(pc, 2)
        }

        df_intra = df_intra.copy()
        df_intra['Date'] = df_intra.index.date
        df_intra['Typical_Price'] = (df_intra['High'] + df_intra['Low'] + df_intra['Close']) / 3.0
        df_intra['TP_Vol'] = df_intra['Typical_Price'] * df_intra['Volume']

        df_intra['Cum_TP_Vol'] = df_intra.groupby('Date')['TP_Vol'].cumsum()
        df_intra['Cum_Vol'] = df_intra.groupby('Date')['Volume'].cumsum()
        df_intra['VWAP'] = df_intra['Cum_TP_Vol'] / df_intra['Cum_Vol'].replace(0, np.nan)

        df_intra['EMA_9'] = df_intra['Close'].ewm(span=9, adjust=False).mean()
        df_intra['EMA_21'] = df_intra['Close'].ewm(span=21, adjust=False).mean()

        delta = df_intra['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df_intra['RSI'] = 100 - (100 / (1 + rs))

        vol_ma = df_intra['Volume'].rolling(window=20).mean().replace(0, np.nan)
        df_intra['RVOL'] = round(df_intra['Volume'] / vol_ma, 2)

        return df_intra, pivots

    @classmethod
    def evaluate_intraday(cls, df_intra: pd.DataFrame, pivots: dict, currency: str = "$") -> dict:
        if df_intra.empty:
            return None

        latest_date = df_intra['Date'].iloc[-1]
        df_today = df_intra[df_intra['Date'] == latest_date]

        orb_high = float(df_today.iloc[:6]['High'].max()) if len(df_today) >= 6 else float(df_today['High'].max())
        orb_low = float(df_today.iloc[:6]['Low'].min()) if len(df_today) >= 6 else float(df_today['Low'].min())

        last = df_today.iloc[-1]
        price = float(last['Close'])
        vwap = float(last['VWAP']) if pd.notna(last['VWAP']) else price
        ema9 = float(last['EMA_9'])
        ema21 = float(last['EMA_21'])
        rsi = float(last['RSI']) if pd.notna(last['RSI']) else 50.0
        rvol = float(last['RVOL']) if pd.notna(last['RVOL']) else 1.0

        score = 50
        signals = []

        if price > vwap:
            score += 15
            signals.append(f"Kurs über Tages-VWAP ({vwap:.2f} {currency}) – Käufer dominieren")
        else:
            score -= 15
            signals.append(f"Kurs unter Tages-VWAP ({vwap:.2f} {currency}) – Verkaufsdruck")

        if len(df_today) > 6:
            if price > orb_high:
                score += 20
                signals.append(f"ORB-Breakout nach oben (über 30m-Hoch {orb_high:.2f} {currency})")
            elif price < orb_low:
                score -= 20
                signals.append(f"ORB-Breakdown nach unten (unter 30m-Tief {orb_low:.2f} {currency})")
            else:
                signals.append(f"Innerhalb der Opening Range ({orb_low:.2f} – {orb_high:.2f} {currency})")

        if ema9 > ema21:
            score += 10
            signals.append("Kurzfrist-Momentum positiv (EMA 9 > EMA 21)")
        else:
            score -= 10

        if rsi < 30 and price > pivots['S1']:
            score += 15
            signals.append(f"Intraday überverkauft (RSI {rsi:.0f}) nahe Support S1 ({pivots['S1']} {currency})")
        elif rsi > 75:
            score -= 15
            signals.append(f"Intraday heißgelaufen (RSI {rsi:.0f}) – Gewinnmitnahmen drohen")

        if rvol >= 1.5:
            signals.append(f"Hohes relatives Volumen ({rvol:.1f}x Durchschnitt) bestätigt Bewegung")

        score = max(0, min(100, score))
        if score >= 70:
            action = "🟢 Intraday LONG"
            sub_action = f"Momentum / Breakout (Score: {score}/100)"
        elif score >= 55:
            action = "🟢 Leicht Bullisch"
            sub_action = f"Dip an VWAP kaufen (Score: {score}/100)"
        elif score >= 45:
            action = "🟡 Neutral / Range"
            sub_action = f"Seitwärtsbewegung (Score: {score}/100)"
        else:
            action = "🔴 SHORT / Abwarten"
            sub_action = f"Unter VWAP-Tendenz (Score: {score}/100)"

        return {
            "price": round(price, 2),
            "vwap": round(vwap, 2),
            "rsi": round(rsi, 1),
            "rvol": rvol,
            "orb_high": round(orb_high, 2),
            "orb_low": round(orb_low, 2),
            "pivots": pivots,
            "score": score,
            "action": action,
            "sub_action": sub_action,
            "signals": signals,
            "last_timestamp": str(df_today.index[-1])
        }
