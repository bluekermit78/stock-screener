import pandas as pd
import numpy as np

class DerivativesAdvisor:
    @staticmethod
    def analyze_derivatives(df: pd.DataFrame, multi_data: dict, intra_data: dict = None) -> dict:
        if df.empty or len(df) < 30:
            return None

        # Nutze den aktuellsten Intraday-/Pre-Market-Kurs, falls vorhanden; sonst EOD/15m-Kurs
        if intra_data and intra_data.get('price'):
            close = float(intra_data['price'])
            price_source = f"Live Intraday (5m Kerze: {intra_data.get('last_timestamp', 'aktuell')})"
        else:
            close = float(multi_data['price'])
            price_source = "Tageschart (15 Min Cache / letzter regulärer Kurs)"

        atr = float(multi_data['atr'])
        cur = multi_data['currency']
        atr_pct = (atr / close) * 100

        # Historische Volatilität (annualisiert, 20 Tage vs. 100 Tage) für Optionsschein-Prüfung (Vega)
        log_ret = np.log(df['Close'] / df['Close'].shift(1))
        hv_20 = float(log_ret.tail(20).std() * np.sqrt(252) * 100)
        hv_100 = float(log_ret.tail(100).std() * np.sqrt(252) * 100)
        vola_ratio = round(hv_20 / hv_100, 2) if hv_100 > 0 else 1.0

        # Grundrichtung bestimmen (Long vs. Short)
        total_score = multi_data['total_score']
        st_score = multi_data['short_term']['score']
        is_bullish = total_score >= 52 or st_score >= 60
        direction = "LONG (Call / Bull)" if is_bullish else "SHORT (Put / Bear)"

        # --- 1. KNOCK-OUT-ZERTIFIKATE (SWING & INTRADAY) ---
        if is_bullish:
            swing_sl_underlying = round(close - (2.0 * atr), 2)
            swing_ko_barrier = round(close - (3.2 * atr), 2)
            swing_tp_underlying = round(close + (3.5 * atr), 2)
        else:
            swing_sl_underlying = round(close + (2.0 * atr), 2)
            swing_ko_barrier = round(close + (3.2 * atr), 2)
            swing_tp_underlying = round(close - (3.5 * atr), 2)

        ko_distance_pct = abs(close - swing_ko_barrier) / close
        recommended_swing_lev = round(1.0 / ko_distance_pct, 1) if ko_distance_pct > 0 else 5.0
        recommended_swing_lev = min(15.0, max(2.0, recommended_swing_lev))

        # Intraday-Knock-Out mit Sicherheits-Mindestabstand für den mentalen Stop-Loss
        intra_ko_info = {}
        if intra_data and 'pivots' in intra_data:
            piv = intra_data['pivots']
            intra_bull = intra_data['score'] >= 50
            intra_dir = "LONG (Turbo Bull)" if intra_bull else "SHORT (Turbo Bear)"
            min_sl_buffer = max(close * 0.012, 0.6 * atr)  # Mindestens 1,2 % oder 0,6x ATR Abstand

            if intra_bull:
                raw_sl = min(intra_data['orb_low'], piv['S1'])
                intra_sl = min(raw_sl, close - min_sl_buffer)
                intra_ko = round(min(piv['S2'], close - (2.0 * atr), intra_sl - (1.0 * atr)), 2)
                raw_tp = piv['R1'] if close < piv['R1'] * 0.99 else piv['R2']
                intra_tp = max(raw_tp, close + (1.2 * atr))
            else:
                raw_sl = max(intra_data['orb_high'], piv['R1'])
                intra_sl = max(raw_sl, close + min_sl_buffer)
                intra_ko = round(max(piv['R2'], close + (2.0 * atr), intra_sl + (1.0 * atr)), 2)
                raw_tp = piv['S1'] if close > piv['S1'] * 1.01 else piv['S2']
                intra_tp = min(raw_tp, close - (1.2 * atr))

            intra_dist = max(0.015, abs(close - intra_ko) / close)
            intra_lev = min(20.0, max(3.0, round(1.0 / intra_dist, 1)))
            intra_ko_info = {
                "direction": intra_dir,
                "ko_barrier": intra_ko,
                "mental_sl": round(intra_sl, 2),
                "target": round(intra_tp, 2),
                "leverage": intra_lev,
                "dist_pct": round(intra_dist * 100, 2)
            }

        # --- 2. KLASSISCHE OPTIONSSCHEINE (WARRANTS) ---
        warrant_strike = round(close * (0.97 if is_bullish else 1.03), 1)
        if vola_ratio < 0.95:
            warrant_status = "🟢 Günstig (Niedrige Volatilität – Einstieg vor Vola-Anstieg ideal)"
        elif vola_ratio <= 1.20:
            warrant_status = "🟡 Normal (Moderate Aufgelder – Delta ~0.60 wählen)"
        else:
            warrant_status = "🔴 Teuer / Vega-Risiko! (Hohe Volatilität – besser Knock-Out statt Optionsschein nutzen)"

        # --- 3. FAKTOR-ZERTIFIKATE (KONSTANTER HEBEL) ---
        mt_score = multi_data['mid_term']['score']
        if (mt_score >= 70 or mt_score <= 30) and atr_pct < 2.8:
            faktor_status = "🟢 Geeignet (Starker, gleichmäßiger Trend)"
            faktor_lev = "3x bis 4x" if atr_pct > 1.8 else "4x bis 6x"
            faktor_note = "Maximal 3–10 Handelstage halten, solange der Kurs nicht seitwärts pendelt."
        else:
            faktor_status = "⛔ Meiden (Pfadabhängigkeits-Falle / Volatility Drag)"
            faktor_lev = "Max. 2x (besser KO-Zertifikat)"
            faktor_note = "Bei schwankenden oder richtungslosen Kursen frisst die tägliche Hebel-Neufestsetzung das Kapital auf."

        if vola_ratio > 1.15:
            best_instrument = "Knock-Out-Zertifikat (Open-End Turbo)"
            best_reason = "Die aktuelle Schwankungsbreite (Volatilität) ist erhöht – Knock-Outs leiden im Gegensatz zu Optionsscheinen nicht unter teurem Aufgeld (Vega) und haben keine Pfadabhängigkeit."
        elif mt_score >= 75 and atr_pct < 2.2:
            best_instrument = "Faktor-Zertifikat (3x–4x) oder moderater Swing-Knock-Out"
            best_reason = "Starker, sauberer Trend bei moderater Tagesschwankung – idealer Zinseszinseffekt für Trendfolger."
        else:
            best_instrument = "Klassischer Optionsschein (Delta ~0.60) oder Swing-Knock-Out"
            best_reason = "Ruhige Volatilitätsphase (HV20/HV100 = " + str(vola_ratio) + ") erlaubt günstige Einstiege in Optionsscheine ohne Knock-Out-Risiko."

        return {
            "active_price": round(close, 2),
            "price_source": price_source,
            "direction": direction,
            "is_bullish": is_bullish,
            "hv_20": round(hv_20, 1),
            "vola_ratio": vola_ratio,
            "atr_pct": round(atr_pct, 2),
            "best_instrument": best_instrument,
            "best_reason": best_reason,
            "swing_ko": {
                "ko_barrier": swing_ko_barrier,
                "mental_sl": swing_sl_underlying,
                "target": swing_tp_underlying,
                "leverage": recommended_swing_lev,
                "dist_pct": round(ko_distance_pct * 100, 2)
            },
            "intraday_ko": intra_ko_info,
            "warrant": {
                "type": "Call-Optionsschein" if is_bullish else "Put-Optionsschein",
                "status": warrant_status,
                "strike": warrant_strike,
                "delta": "0.55 bis 0.65 (leicht im Geld / ITM)" if is_bullish else "-0.55 bis -0.65 (leicht im Geld / ITM)",
                "min_expiry": "Mindestens 4 bis 6 Monate Restlaufzeit (Theta-Schutz)"
            },
            "faktor": {
                "status": faktor_status,
                "recommended_faktor": faktor_lev,
                "note": faktor_note
            }
        }
