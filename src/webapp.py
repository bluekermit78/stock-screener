import os
import json
import yaml
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from indicators import TechnicalIndicators
from advisor import InvestmentAdvisor
from intraday import IntradayAnalyzer
from derivatives import DerivativesAdvisor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DATA_PATH = os.path.join(BASE_DIR, "data", "latest_analysis.json")

st.set_page_config(page_title="Aktien-Anlageberater & Screener", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .block-container {
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-top: 2rem !important;
        max-width: 100% !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        line-height: 1.3 !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        word-break: break-word !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.85rem !important;
        white-space: normal !important;
    }
</style>
""", unsafe_allow_html=True)

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

def compact_verdict(v: str) -> str:
    if not isinstance(v, str):
        return ""
    return (
        v.replace("Starker Kauf", "Top-Kauf")
         .replace("Verkauf / Meiden", "Meiden")
    )

@st.cache_data(ttl=120)
def fetch_single_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period)
    if not df.empty:
        df = TechnicalIndicators.apply_indicators(df)
    return df

@st.cache_data(ttl=60)
def fetch_cached_intraday(ticker: str, interval: str = "5m", include_prepost: bool = False):
    return IntradayAnalyzer.fetch_intraday_data(ticker, interval=interval, period="5d", include_prepost=include_prepost)

@st.cache_data(ttl=300)
def fetch_eur_usd_rate() -> float:
    try:
        df_fx = yf.Ticker("EURUSD=X").history(period="1d")
        if not df_fx.empty:
            return float(df_fx['Close'].iloc[-1])
    except Exception:
        pass
    return 1.08

@st.cache_data(ttl=3600)
def fetch_fundamentals(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        fcf = info.get('freeCashflow')
        mcap = info.get('marketCap')
        return {
            "name": info.get('shortName', ticker),
            "sector": info.get('sector', 'Index / ETF'),
            "pe": info.get('forwardPE') or info.get('trailingPE'),
            "fcf_yield": (fcf / mcap * 100) if (fcf and mcap) else None,
            "rev_growth": info.get('revenueGrowth')
        }
    except Exception:
        return {"name": ticker, "sector": "n/a", "pe": None, "fcf_yield": None, "rev_growth": None}

def plot_chart(df: pd.DataFrame, ticker: str):
    df_plot = df.tail(180)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(
            f"{ticker} – Kurs, gleitende Durchschnitte & Bollinger-Bänder (180 Handelstage)",
            "RSI (14) – Relative-Stärke-Index (<30 überverkauft, >70 überkauft)",
            "MACD (12, 26, 9) – Trendstärke & Momentum-Wechsel"
        )
    )

    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
        low=df_plot['Low'], close=df_plot['Close'], name="Kurs"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_20'], line=dict(color='#00b4d8', width=1.2), name='EMA 20 (Kurzfrist)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA_50'], line=dict(color='#f77f00', width=1.8), name='SMA 50 (Mittelfrist)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA_200'], line=dict(color='#d62828', width=2.2), name='SMA 200 (Langfrist)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='gray', dash='dot', width=1), name='Bollinger Oben'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='gray', dash='dot', width=1), name='Bollinger Unten'), row=1, col=1)

    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], line=dict(color='#9b5de5', width=1.5), name='RSI (14)'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['MACD_Hist'], name='MACD Histogramm', marker_color='#adb5bd'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MACD'], line=dict(color='#0077b6', width=1.5), name='MACD-Linie'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MACD_Signal'], line=dict(color='#fb8500', width=1.5), name='Signallinie'), row=3, col=1)

    fig.update_layout(height=740, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

def plot_intraday_chart(df_intra: pd.DataFrame, eval_res: dict, ticker: str):
    unique_dates = df_intra['Date'].unique()
    recent_dates = unique_dates[-2:] if len(unique_dates) >= 2 else unique_dates
    df_plot = df_intra[df_intra['Date'].isin(recent_dates)].copy()

    x_labels = df_plot.index.strftime("%d.%m. %H:%M")

    piv = eval_res['pivots']
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(
            f"{ticker} – Intraday (5m Kerzen in deutscher Zeit MEZ) mit Tages-VWAP, EMA 9/21 & Pivot-Marken",
            "Intraday-Volumen",
            "Intraday RSI (14)"
        )
    )

    fig.add_trace(go.Candlestick(
        x=x_labels, open=df_plot['Open'], high=df_plot['High'],
        low=df_plot['Low'], close=df_plot['Close'], name="5m Kurs"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_labels, y=df_plot['VWAP'], line=dict(color='#ffd166', width=2.5), name='VWAP (Institutionell)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_labels, y=df_plot['EMA_9'], line=dict(color='#00b4d8', width=1.3), name='EMA 9'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_labels, y=df_plot['EMA_21'], line=dict(color='#f77f00', width=1.3), name='EMA 21'), row=1, col=1)

    fig.add_hline(y=piv['R1'], line_dash="dot", line_color="#ef476f", annotation_text=f"R1 ({piv['R1']})", row=1, col=1)
    fig.add_hline(y=piv['P'], line_dash="dash", line_color="#adb5bd", annotation_text=f"Pivot ({piv['P']})", row=1, col=1)
    fig.add_hline(y=piv['S1'], line_dash="dot", line_color="#06d6a0", annotation_text=f"S1 ({piv['S1']})", row=1, col=1)
    fig.add_hline(y=eval_res['orb_high'], line_dash="dashdot", line_color="#118ab2", annotation_text=f"ORB High ({eval_res['orb_high']})", row=1, col=1)
    fig.add_hline(y=eval_res['orb_low'], line_dash="dashdot", line_color="#118ab2", annotation_text=f"ORB Low ({eval_res['orb_low']})", row=1, col=1)

    fig.add_trace(go.Bar(x=x_labels, y=df_plot['Volume'], name='Volumen', marker_color='#4cc9f0'), row=2, col=1)

    fig.add_trace(go.Scatter(x=x_labels, y=df_plot['RSI'], line=dict(color='#9b5de5', width=1.5), name='Intraday RSI'), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_xaxes(type='category', nticks=18)
    fig.update_layout(height=740, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

def render_derivatives_panel(df_hist: pd.DataFrame, sel_data: dict, intra_eval: dict = None, is_intraday_view: bool = False):
    deriv = DerivativesAdvisor.analyze_derivatives(df_hist, sel_data, intra_eval)
    if not deriv:
        return

    cur = sel_data['currency']
    price = deriv['active_price']
    eur_usd = fetch_eur_usd_rate() if cur == "$" else 1.0

    st.divider()
    st.markdown(f"#### 🎯 Derivate- & Hebel-Berater für **{sel_data['name']} ({sel_data['ticker']})**")
    fx_info = f" | **EUR/USD Live:** `{eur_usd:.4f}`" if cur == "$" else ""
    st.caption(
        f"**Berechnungsbasis:** **`{price:.2f} {cur}`** *({deriv['price_source']})*{fx_info} | "
        f"**Beste Produktklasse aktuell:** **{deriv['best_instrument']}** — *{deriv['best_reason']}*"
    )

    d_col1, d_col2, d_col3 = st.columns(3)

    with d_col1:
        if is_intraday_view and deriv['intraday_ko']:
            iko = deriv['intraday_ko']
            st.info(
                f"**⚡ 1. Intraday Knock-Out (Turbo)**\n\n"
                f"- **Ausrichtung:** `{iko['direction']}`\n"
                f"- **Empfohlener Hebel:** **`{iko['leverage']}x`**\n"
                f"- **Max. KO-Schwelle:** `{iko['ko_barrier']:.2f} {cur}` *(Puffer: {iko['dist_pct']}%)*\n"
                f"- **Mentaler Stop-Loss (Aktie):** `{iko['mental_sl']:.2f} {cur}`\n"
                f"- **Intraday-Kursziel (Aktie):** `{iko['target']:.2f} {cur}`"
            )
        else:
            sko = deriv['swing_ko']
            st.info(
                f"**🔥 1. Swing Knock-Out (Open-End Turbo)**\n\n"
                f"- **Ausrichtung:** `{deriv['direction']}`\n"
                f"- **Empfohlener Hebel:** **`{sko['leverage']}x`**\n"
                f"- **Sichere KO-Schwelle (3.2x ATR):** `{sko['ko_barrier']:.2f} {cur}` *(Puffer: {sko['dist_pct']}%)*\n"
                f"- **Mentaler Stop-Loss (2.0x ATR):** `{sko['mental_sl']:.2f} {cur}`\n"
                f"- **Swing-Kursziel (3.5x ATR):** `{sko['target']:.2f} {cur}`"
            )

    with d_col2:
        w = deriv['warrant']
        st.warning(
            f"**📜 2. Klassischer Optionsschein (Warrant)**\n\n"
            f"- **Typ:** `{w['type']}`\n"
            f"- **Volatilitäts-Check (Vega):** {w['status']}\n"
            f"- **Empfohlener Basispreis (Strike):** ca. `{w['strike']:.1f} {cur}`\n"
            f"- **Optimales Delta:** `{w['delta']}`\n"
            f"- **Laufzeit-Regel:** {w['min_expiry']}"
        )

    with d_col3:
        f = deriv['faktor']
        st.success(
            f"**🔄 3. Faktor-Zertifikat (Konstanter Hebel)**\n\n"
            f"- **Eignung:** {f['status']}\n"
            f"- **Empfohlener Faktor:** **`{f['recommended_faktor']}`**\n"
            f"- **Wichtige Handelsregel:** {f['note']}"
        )

    # --- SCALABLE CAPITAL INTERAKTIVER ORDER-ASSISTENT ---
    active_ko = deriv['intraday_ko'] if (is_intraday_view and deriv['intraday_ko']) else deriv['swing_ko']
    default_is_long = "LONG" in active_ko.get('direction', deriv['direction'])
    key_prefix = f"sc_{sel_data['ticker']}_{'intra' if is_intraday_view else 'swing'}"

    with st.expander(f"📱 Scalable Capital Knock-Out Order-Assistent (Schritt-für-Schritt Eingabehilfe | Basiswert: {price:.2f} {cur})", expanded=True):
        st.markdown(
            f"**Schritt 1 – Zertifikate-Filter in Scalable Capital öffnen (`Derivate` ➔ `{sel_data['name']}`):**\n"
            f"1. **Richtung wählen:** `{'Long' if default_is_long else 'Short'}` | **Hebel-Filter einstellen:** ca. `{max(2.0, round(active_ko['leverage']-2, 0)):.0f}x bis {round(active_ko['leverage']+2, 0):.0f}x`\n"
            f"2. **Nach Knock-Out-Schwelle in {cur} schauen:** Bei **Long** muss die KO-Schwelle **unter `{active_ko['ko_barrier']:.2f} {cur}`** liegen (bei Short über `{active_ko['ko_barrier']:.2f} {cur}`).\n"
            f"3. Wähle ein Zertifikat (z. B. von BNP, HSBC, Vontobel oder UniCredit) aus der Liste und trage seine **KO-Schwelle** sowie den **Briefkurs (Kaufpreis in €)** hier unten ein:"
        )

        st.divider()
        st.markdown("**Schritt 2 – Eckdaten deines ausgewählten Zertifikats eintragen:**")
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            trade_dir = st.selectbox(
                "Gewählte Richtung bei Scalable:",
                ["Long (Steigende Kurse)", "Short (Fallende Kurse)"],
                index=0 if default_is_long else 1,
                key=f"{key_prefix}_dir"
            )
            is_long = trade_dir.startswith("Long")
        with sc2:
            default_ko = float(active_ko['ko_barrier']) if (is_long == default_is_long) else round(price * (0.88 if is_long else 1.12), 2)
            user_ko_barrier = st.number_input(
                f"KO-Schwelle des Zertifikats (in {cur}):",
                min_value=1.0, max_value=100000.0, value=float(default_ko), step=0.5,
                help=f"Steht im Namen des Zertifikats, z. B. 'NVIDIA Long 130,06 Turbo' -> 130.06 {cur}",
                key=f"{key_prefix}_ko"
            )
        with sc3:
            ratio = st.selectbox(
                "Bezugsverhältnis (Standard 0,10):",
                [0.10, 0.01, 1.00],
                index=0,
                help="Bei fast allen US- und DAX-Aktien (wie Nvidia, Apple, SAP) ist das Bezugsverhältnis 0,10 (10 Zertifikate beziehen sich auf 1 Aktie).",
                key=f"{key_prefix}_ratio"
            )
            # Rechnerischer innerer Wert als sinnvoller Startwert für den Briefkurs
            intrinsic_eur = max(0.15, (abs(price - user_ko_barrier) * ratio) / eur_usd)
        with sc4:
            cert_ask_eur = st.number_input(
                "Aktueller Briefkurs / Kaufpreis (in €):",
                min_value=0.05, max_value=500.0, value=round(intrinsic_eur + 0.04, 2), step=0.05,
                help="Der aktuelle Preis in Euro für 1 Anteil bei Scalable Capital.",
                key=f"{key_prefix}_ask"
            )

        # Berechnung von Effektiv-Hebel, Innerem Wert und Aufgeld
        stock_price_eur = price / eur_usd
        eff_leverage = round((stock_price_eur * ratio) / cert_ask_eur, 2) if cert_ask_eur > 0 else 1.0
        raw_intrinsic_eur = ((price - user_ko_barrier) * ratio / eur_usd) if is_long else ((user_ko_barrier - price) * ratio / eur_usd)
        raw_intrinsic_eur = max(0.0, raw_intrinsic_eur)
        premium_eur = round(cert_ask_eur - raw_intrinsic_eur, 2)
        ko_dist_pct = ((price - user_ko_barrier) / price * 100) if is_long else ((user_ko_barrier - price) / price * 100)

        if ko_dist_pct <= 0:
            st.error(f"⚠️ Achtung: Die eingegebene KO-Schwelle ({user_ko_barrier:.2f} {cur}) wurde beim aktuellen Kurs ({price:.2f} {cur}) bereits erreicht oder verletzt!")
            return

        st.caption(
            f"🔍 **Zertifikate-Check:** Realer Hebel: **`{eff_leverage:.2f}x`** | "
            f"Abstand zum Knock-Out: **`{ko_dist_pct:.2f}%`** (`{abs(price - user_ko_barrier):.2f} {cur}`) | "
            f"Rechnerischer innerer Wert: **`{raw_intrinsic_eur:.2f} €`** (Aufgeld/Finanzierung: `{premium_eur:+.2f} €` pro Schein)"
        )

        st.divider()
        st.markdown("**Schritt 3 – Kauf-Parameter (Betrag / Stückzahl & Order-Typ) festlegen:**")
        p_col1, p_col2, p_col3, p_col4 = st.columns(4)
        with p_col1:
            sizing_mode = st.selectbox(
                "Wie möchtest du die Größe bestimmen?",
                ["1. Nach maximalem Risiko (in €)", "2. Fester Zielbetrag (Investition in €)", "3. Feste Stückzahl (Anteile)"],
                key=f"{key_prefix}_smode"
            )
        with p_col2:
            if sizing_mode.startswith("1."):
                user_budget_val = st.number_input("Max. erlaubter Verlust bis Stop-Loss (€):", min_value=5.0, max_value=10000.0, value=25.0, step=5.0, key=f"{key_prefix}_rval")
            elif sizing_mode.startswith("2."):
                user_budget_val = st.number_input("Gewünschter Investitionsbetrag (€):", min_value=10.0, max_value=50000.0, value=300.0, step=25.0, key=f"{key_prefix}_ival")
            else:
                user_budget_val = st.number_input("Gewünschte Stückzahl (Anteile):", min_value=1, max_value=50000, value=100, step=10, key=f"{key_prefix}_sval")

        # Sinnvolle Vorbelegung für Stop-Loss und Kursziel der Aktie
        atr_val = float(sel_data['atr'])
        default_sl_stock = float(active_ko['mental_sl']) if (is_long == default_is_long) else round(price - 1.5 * atr_val if is_long else price + 1.5 * atr_val, 2)
        default_tp_stock = float(active_ko['target']) if (is_long == default_is_long) else round(price + 2.5 * atr_val if is_long else price - 2.5 * atr_val, 2)

        with p_col3:
            sl_stock = st.number_input(
                f"Dein Stop-Loss im Aktienchart ({cur}):",
                value=float(default_sl_stock), step=0.25,
                help="Kurs der Aktie, bei dem du die Reißleine ziehst (muss vor der KO-Schwelle liegen!).",
                key=f"{key_prefix}_slstock"
            )
        with p_col4:
            entry_type = st.selectbox(
                "Einstiegs-Art bei Scalable:",
                ["Sofortkauf (nur LIMIT hinzufügen)", "Breakout-Kauf (STOP + LIMIT hinzufügen)"],
                help="Sofortkauf = Du kaufst jetzt zum aktuellen Kurs mit Limit-Schutz. Breakout-Kauf = Order wird erst ausgelöst, wenn das Zertifikat über den STOP-Preis steigt.",
                key=f"{key_prefix}_etype"
            )

        # Umrechnung des Aktien-Stop-Loss und Aktien-Kursziels in den Euro-Preis des Zertifikats
        # Preisänderung des Zertifikats in € = (Kursänderung Aktie in USD * Bezugsverhältnis) / EURUSD
        stock_diff_to_sl = abs(price - sl_stock)
        cert_loss_per_share_eur = (stock_diff_to_sl * ratio) / eur_usd
        cert_sl_eur = max(0.01, round(cert_ask_eur - cert_loss_per_share_eur, 2))
        actual_loss_per_share = max(0.01, cert_ask_eur - cert_sl_eur)
        cert_loss_pct = (actual_loss_per_share / cert_ask_eur) * 100

        stock_diff_to_tp = abs(default_tp_stock - price)
        cert_gain_per_share_eur = (stock_diff_to_tp * ratio) / eur_usd
        cert_tp_eur = round(cert_ask_eur + cert_gain_per_share_eur, 2)
        cert_gain_pct = (cert_gain_per_share_eur / cert_ask_eur) * 100

        # Stückzahl und Investitionsbetrag je nach Modus berechnen
        if sizing_mode.startswith("1."):
            shares = max(1, int(user_budget_val // actual_loss_per_share))
        elif sizing_mode.startswith("2."):
            shares = max(1, int(user_budget_val // cert_ask_eur))
        else:
            shares = int(user_budget_val)

        total_invest_eur = round(shares * cert_ask_eur, 2)
        total_risk_eur = round(shares * actual_loss_per_share, 2)
        total_profit_eur = round(shares * cert_gain_per_share_eur, 2)

        # Berechnung für STOP hinzufügen & LIMIT hinzufügen beim Kauf
        if entry_type.startswith("Sofortkauf"):
            buy_stop_str = "Nicht aktivieren (leer lassen)"
            # Enges Kauflimit (+1,0 % bzw. mind. +0,02 € über Briefkurs statt der teuren 4 % Scalable-Automatik)
            buy_limit_eur = round(max(cert_ask_eur + 0.02, cert_ask_eur * 1.01), 2)
            buy_mode_hint = f"Schützt dich vor Slippage (max. +1% über Briefkurs statt der 4% Standard-Toleranz)."
        else:
            # Breakout-Kauf: z. B. Ausbruch über ORB High (oder +0,5 % im Basiswert)
            orb_trigger_stock = intra_eval['orb_high'] if (intra_eval and is_long and intra_eval['orb_high'] > price) else round(price * (1.005 if is_long else 0.995), 2)
            diff_to_trigger = abs(orb_trigger_stock - price)
            trigger_cert_eur = round(cert_ask_eur + ((diff_to_trigger * ratio) / eur_usd), 2)
            buy_stop_str = f"{trigger_cert_eur:.2f} €"
            buy_limit_eur = round(trigger_cert_eur + max(0.03, trigger_cert_eur * 0.01), 2)
            buy_mode_hint = f"Aktiviert den Kauf erst, wenn die Aktie auf {orb_trigger_stock:.2f} {cur} ausbricht."

        st.divider()
        st.markdown("#### ✅ Schritt 4 – Deine exakten Eingabewerte für die Scalable Capital Ordermaske:")

        out1, out2 = st.columns(2)
        with out1:
            st.info(
                f"**🛒 A. Eingabe beim KAUF des Zertifikats:**\n\n"
                f"- **Zielbetrag (Investition):** **`{total_invest_eur:.2f} €`** *(oder exakt **`{shares} Stück`** eingeben)*\n"
                f"- **STOP hinzufügen (Aktivierungskurs):** **`{buy_stop_str}`**\n"
                f"- **LIMIT hinzufügen (Max. Kaufpreis pro Stück):** **`{buy_limit_eur:.2f} €`**\n"
                f"  *({buy_mode_hint})*"
            )
        with out2:
            # Scalable verlangt bei Stop-Loss-Verkaufsorders einen Stop-Preis (Trigger) und ein leicht darunterliegendes Limit
            sell_sl_limit_eur = max(0.01, round(cert_sl_eur - max(0.02, cert_sl_eur * 0.015), 2))
            st.warning(
                f"**🛡️ B. Eingabe direkt NACH dem Kauf (Verkaufs-Absicherung / Stop-Loss):**\n\n"
                f"- **Stop-Loss STOP-Preis (Auslöser bei Aktie {sl_stock:.2f} {cur}):** **`{cert_sl_eur:.2f} €`** *(-{cert_loss_pct:.1f}%)*\n"
                f"- **Stop-Loss LIMIT-Preis (Mindestverkaufspreis):** **`{sell_sl_limit_eur:.2f} €`** *(1,5% Puffer für sichere Ausführung)*\n"
                f"- **Optionales Gewinnziel (Limit-Verkauf bei Aktie {default_tp_stock:.2f} {cur}):** **`{cert_tp_eur:.2f} €`** *(+{cert_gain_pct:.1f}%)*\n"
                f"- **Dein exaktes Euro-Ergebnis:** Risiko bis Stop-Loss: **`-{total_risk_eur:.2f} €`** | Gewinn am Ziel: **`+{total_profit_eur:.2f} €`**"
            )

st.title("🏛️ Persönlicher Aktien- & Derivate-Anlageberater")
st.markdown(
    "Dieses Dashboard kombiniert **technische Chartanalyse**, **Intraday-Signale (VWAP, Pivots, ORB)**, **fundamentale Bewertung** "
    "und einen **Scalable Capital Knock-Out Order-Assistenten** auf Echtzeit-Kursbasis."
)

with st.expander("📖 Lexikon & Methodik: Indikatoren, Intraday-Marken & Scalable-Order-Typen"):
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.markdown("""
        **📈 Swing- & Trend-Indikatoren (Tageschart)**
        * **RSI (Relative Strength Index, 14):** Misst die Dynamik auf einer Skala von 0 bis 100 (**<30** überverkauft, **>70** überkauft).
        * **EMA 20 / SMA 50 / SMA 200:** Gleitende Durchschnittskurse der letzten 20, 50 bzw. 200 Handelstage.
        * **MACD & Bollinger-Bänder:** Zeigen Trendwechsel und statistische Übertreibungen an.
        """)
    with col_g2:
        st.markdown("""
        **⚡ Intraday-Trading-Indikatoren (5-Minuten-Chart)**
        * **VWAP (Volume Weighted Average Price):** Volumengewichteter Durchschnittspreis des heutigen Tages. Kurse **über VWAP** = Bullisch (Long-Bias), **unter VWAP** = Bärisch.
        * **ORB (Opening Range Breakout):** Hoch- und Tiefpunkt der ersten 30 Handelsminuten.
        * **Pivot-Punkte ($P, R_1, R_2, S_1, S_2$):** Aus dem Vortag berechnete Unterstützungs- und Widerstandszonen.
        """)
    with col_g3:
        st.markdown("""
        **📱 Scalable Capital Order-Zusätze erklärt**
        * **LIMIT hinzufügen (beim Kauf):** Legt fest, was du pro Zertifikat maximal bezahlst. Setze immer ein eigenes Limit (ca. 1 % über Briefkurs), statt die 4 %-Standard-Toleranz von Scalable zu nutzen.
        * **STOP hinzufügen (beim Kauf = Stop-Buy):** Nützlich für Ausbrüche (Breakouts). Die Order schläft, bis das Zertifikat auf den STOP-Preis steigt, und kauft erst dann automatisch bis zum LIMIT-Preis.
        * **Stop-Loss Limit (nach dem Kauf):** Sichert deine Position nach unten ab. Fällt der Schein auf den STOP-Kurs, wird er zum LIMIT-Kurs verkauft, bevor ein Knock-Out droht.
        """)

config = load_config()
current_focus_list = [t.strip().upper() for t in config.get('universe', ['AAPL', 'MSFT', 'NVDA', 'CARR', 'SAP.DE', 'SIE.DE'])]

tab1, tab2, tab3 = st.tabs([
    "🎯 Meine Fokus-Aktien (Multi-Horizont, Intraday & Scalable-Assistent)",
    "🌍 Indizes & Markt-Kompass",
    "🔍 Gesamtmarkt-Screener (S&P 500 / DAX / MDAX)"
])

with tab1:
    st.subheader("Persönliche Watchlist, Chartanalyse & Scalable Derivate-Assistent")
    st.caption(
        "Hier werden deine Fokus-Aktien in Echtzeit durchleuchtet – inklusive konkreter Eingabewerte für deine **Scalable Capital Knock-Out-Orders**."
    )

    col_cfg, col_sel = st.columns([2, 1])
    with col_cfg:
        new_watchlist_str = st.text_input(
            "Fokus-Aktien bearbeiten (Komma-getrennt, deutsche Xetra-Aktien mit .DE):",
            value=", ".join(current_focus_list)
        )
        if st.button("💾 Watchlist in config.yaml speichern"):
            updated_list = list(dict.fromkeys([t.strip().upper() for t in new_watchlist_str.split(",") if t.strip()]))
            config['universe'] = updated_list
            save_config(config)
            st.success("Watchlist gespeichert!")
            st.rerun()

    watchlist = [t.strip().upper() for t in new_watchlist_str.split(",") if t.strip()]
    
    watchlist_results = []
    for t in watchlist:
        df_t = fetch_single_history(t)
        fund_t = fetch_fundamentals(t)
        res = InvestmentAdvisor.analyze_ticker(t, df_t, fund_t)
        if res:
            res['name'] = fund_t['name']
            res['sector'] = fund_t['sector']
            res['pe'] = round(fund_t['pe'], 1) if fund_t['pe'] else None
            res['fcf_yield'] = round(fund_t['fcf_yield'], 1) if fund_t['fcf_yield'] else None
            watchlist_results.append(res)

    if watchlist_results:
        summary_rows = []
        for r in watchlist_results:
            summary_rows.append({
                "Ticker": f"https://finance.yahoo.com/quote/{r['ticker']}",
                "Name": r['name'],
                "Sektor": r['sector'],
                "Kurs": f"{r['price']} {r['currency']}",
                "1W": r['perf']['1W'],
                "1M": r['perf']['1M'],
                "3M": r['perf']['3M'],
                "1Y": r['perf']['1Y'],
                "Kurz (1-4W)": f"{compact_verdict(r['short_term'][' verdict'])} ({r['short_term']['score']})",
                "Mittel (1-6M)": f"{compact_verdict(r['mid_term']['verdict'])} ({r['mid_term']['score']})",
                "Lang (6M+)": f"{compact_verdict(r['long_term']['verdict'])} ({r['long_term']['score']})",
                "Urteil": f"{compact_verdict(r['overall_verdict'])} ({r['total_score']})",
                "SL": f"{r['stop_loss']} {r['currency']}",
                "TP": f"{r['take_profit']} {r['currency']}"
            })
        st.dataframe(
            pd.DataFrame(summary_rows),
            column_config={
                "Ticker": st.column_config.LinkColumn(
                    "Ticker", width="small",
                    help="Klicken, um Detaildaten & News auf Yahoo Finance in einem neuen Tab zu öffnen",
                    display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                ),
                "Name": st.column_config.TextColumn("Unternehmen", width="medium", help="Offizieller Firmenname"),
                "Sektor": st.column_config.TextColumn("Sektor", width="medium", help="Wirtschaftszweig / Branche"),
                "Kurs": st.column_config.TextColumn("Kurs", width="small", help="Aktueller Kurs"),
                "1W": st.column_config.NumberColumn("1W", width="small", help="Kursentwicklung 1 Woche in %", format="%.1f%%"),
                "1M": st.column_config.NumberColumn("1M", width="small", help="Kursentwicklung 1 Monat in %", format="%.1f%%"),
                "3M": st.column_config.NumberColumn("3M", width="small", help="Kursentwicklung 3 Monate in %", format="%.1f%%"),
                "1Y": st.column_config.NumberColumn("1Y", width="small", help="Kursentwicklung 1 Jahr in %", format="%.1f%%"),
                "Kurz (1-4W)": st.column_config.TextColumn("Kurz (1-4W)", width="small", help="Taktische Bewertung: RSI, Bollinger-Bänder, EMA 20, MACD"),
                "Mittel (1-6M)": st.column_config.TextColumn("Mittel (1-6M)", width="small", help="Trendfolge-Bewertung: SMA 50 & 3M-Momentum"),
                "Lang (6M+)": st.column_config.TextColumn("Lang (6M+)", width="small", help="Strategische Bewertung: SMA 200 & Fundamentaldaten"),
                "Urteil": st.column_config.TextColumn("Gesamt", width="small", help="Gewichtetes Gesamturteil"),
                "SL": st.column_config.TextColumn("SL", width="small", help="Stop-Loss (2x ATR unter Kurs)"),
                "TP": st.column_config.TextColumn("TP", width="small", help="Technisches Kursziel (3.5x ATR über Kurs)")
            },
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        col_pick, col_mode = st.columns([1, 1.5])
        with col_pick:
            selected_ticker = st.selectbox("🔎 Aktie für Detail- & Derivate-Analyse auswählen:", watchlist)
        with col_mode:
            analysis_mode = st.radio(
                "Analyse-Modus wählen:",
                ["📊 Multi-Horizont & Swing-Derivate (Tageschart)", "⚡ Live Intraday-Cockpit & Daytrading-Turbos (5m-Chart)"],
                horizontal=True
            )

        sel_data = next((item for item in watchlist_results if item['ticker'] == selected_ticker), None)
        df_hist_selected = fetch_single_history(selected_ticker)

        if sel_data and analysis_mode.startswith("📊"):
            df_intra_live, pivots_live = fetch_cached_intraday(selected_ticker, interval="5m", include_prepost=not selected_ticker.endswith(".DE"))
            intra_eval_live = IntradayAnalyzer.evaluate_intraday(df_intra_live, pivots_live, currency=sel_data['currency'])
            live_price_display = intra_eval_live['price'] if intra_eval_live else sel_data['price']

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Aktueller Kurs (Live)", f"{live_price_display} {sel_data['currency']}", f"{sel_data['perf']['1M']}% (1M)")
            c2.metric("Gesamt-Empfehlung", sel_data['overall_verdict'], f"Score: {sel_data['total_score']} / 100")
            c3.metric("Empfohlener Stop-Loss (2x ATR)", f"{sel_data['stop_loss']} {sel_data['currency']}")
            c4.metric("Technisches Kursziel (3.5x ATR)", f"{sel_data['take_profit']} {sel_data['currency']}")

            h1, h2, h3 = st.columns(3)
            with h1:
                st.info(f"**⚡ Kurzfristig (1–4 Wochen): {sel_data['short_term'][' verdict']} ({sel_data['short_term']['score']}/100)**\n\n" +
                        ("\n".join([f"- {x}" for x in sel_data['short_term']['reasons']]) or "- Neutrale Indikatorenlage"))
            with h2:
                st.warning(f"**🌊 Mittelfristig (1–6 Monate): {sel_data['mid_term']['verdict']} ({sel_data['mid_term']['score']}/100)**\n\n" +
                           ("\n".join([f"- {x}" for x in sel_data['mid_term']['reasons']]) or "- Seitwärtstrend"))
            with h3:
                st.success(f"**🏛️ Langfristig (6+ Monate): {sel_data['long_term']['verdict']} ({sel_data['long_term']['score']}/100)**\n\n" +
                           ("\n".join([f"- {x}" for x in sel_data['long_term']['reasons']]) or "- Neutrale Bewertung"))

            render_derivatives_panel(df_hist_selected, sel_data, intra_eval=intra_eval_live, is_intraday_view=False)
            plot_chart(df_hist_selected, selected_ticker)

        elif sel_data and analysis_mode.startswith("⚡"):
            col_hdr, col_pre, col_btn = st.columns([2.5, 1.5, 1])
            with col_hdr:
                st.markdown(f"#### ⚡ Intraday-Trading-Desk: **{sel_data['name']} ({selected_ticker})**")
            with col_pre:
                include_prepost = st.checkbox(
                    "🌅 US Vor-/Nachbörse (ab 10:00 MEZ)",
                    value=not selected_ticker.endswith(".DE"),
                    help="Aktiviert vor- und nachbörsliche 5m-Kerzen (Pre-/After-Market). Besonders nützlich für US-Aktien vor 15:30 Uhr deutscher Zeit."
                )
            with col_btn:
                if st.button("🔄 Kursdaten aktualisieren"):
                    st.cache_data.clear()
                    st.rerun()

            df_intra, pivots = fetch_cached_intraday(selected_ticker, interval="5m", include_prepost=include_prepost)
            intra_eval = IntradayAnalyzer.evaluate_intraday(df_intra, pivots, currency=sel_data['currency'])

            if intra_eval:
                cur = sel_data['currency']
                vwap_diff_pct = round(((intra_eval['price'] / intra_eval['vwap']) - 1) * 100, 2) if intra_eval['vwap'] else 0.0

                ic1, ic2, ic3, ic4 = st.columns(4)
                ic1.metric(
                    "Intraday-Signal (5m)",
                    intra_eval['action'],
                    intra_eval.get('sub_action', f"Score: {intra_eval['score']} / 100"),
                    delta_color="off",
                    help="Kombiniertes Signal aus VWAP-Position, 30m Opening Range Breakout, EMA 9/21 und 5m-RSI."
                )
                ic2.metric(
                    "Kurs vs. Tages-VWAP",
                    f"{intra_eval['price']:.2f} {cur}",
                    f"{vwap_diff_pct:+.2f}% zum VWAP ({intra_eval['vwap']:.2f} {cur})",
                    help="Notiert der Kurs über dem VWAP, haben institutionelle Käufer im heutigen Handelsverlauf das Übergewicht."
                )
                ic3.metric(
                    "Opening Range (erste 30 Min)",
                    f"{intra_eval['orb_low']:.2f} – {intra_eval['orb_high']:.2f} {cur}",
                    f"RVOL: {intra_eval['rvol']}x | RSI(5m): {intra_eval['rsi']}",
                    delta_color="off",
                    help="Spanne der ersten 30 Handelsminuten. Ausbrüche darüber (ORB High) oder darunter (ORB Low) liefern starke Richtungsimpulse."
                )
                ic4.metric(
                    "Tages-Pivot & Schlüsselzonen",
                    f"Pivot: {pivots['P']:.2f} {cur}",
                    f"S1: {pivots['S1']:.2f} | R1: {pivots['R1']:.2f}",
                    delta_color="off",
                    help=f"Klassische Floor-Pivots aus dem Vortag (S2: {pivots['S2']} | S1: {pivots['S1']} | P: {pivots['P']} | R1: {pivots['R1']} | R2: {pivots['R2']})."
                )

                st.info(
                    f"**🎯 Letzte Kerze: {intra_eval['last_timestamp']}**\n\n" +
                    "\n".join([f"- {s}" for s in intra_eval['signals']]) +
                    f"\n\n**📌 Intraday-Fahrplan:** Solange der Kurs über dem **VWAP ({intra_eval['vwap']:.2f} {cur})** bzw. über **Pivot P ({pivots['P']:.2f} {cur})** handelt, liegen die nächsten Tagesziele bei **R1 ({pivots['R1']:.2f} {cur})** und **R2 ({pivots['R2']:.2f} {cur})**. Ein Rückfall unter das **ORB-Tief ({intra_eval['orb_low']:.2f} {cur})** aktiviert die Unterstützung bei **S1 ({pivots['S1']:.2f} {cur})**."
                )

                render_derivatives_panel(df_hist_selected, sel_data, intra_eval=intra_eval, is_intraday_view=True)
                plot_intraday_chart(df_intra, intra_eval, selected_ticker)
            else:
                st.warning("Für diesen Ticker konnten aktuell keine 5-Minuten-Intraday-Daten geladen werden.")

with tab2:
    st.subheader("Globale Leitindizes im Performance- & Trend-Check")
    st.caption(
        "Der Markt-Kompass zeigt dir die Großwetterlage an den Börsen. "
        "Käufe in Einzelaktien und Long-Derivaten haben eine deutlich höhere Trefferquote, wenn auch der übergeordnete Heimatindex im Aufwärtstrend notiert."
    )
    indices = {
        "^GSPC": "S&P 500 (USA Leitindex)",
        "^NDX": "Nasdaq 100 (USA Technologie)",
        "^GDAXI": "DAX 40 (Deutschland Blue Chips)",
        "^MDAXI": "MDAX (Deutschland Mid-Caps)",
        "URTH": "MSCI World (Weltweiter Aktienmarkt)"
    }
    idx_rows = []
    for sym, label in indices.items():
        df_i = fetch_single_history(sym)
        res_i = InvestmentAdvisor.analyze_ticker(sym, df_i)
        if res_i:
            idx_rows.append({
                "Index": label,
                "Symbol": sym,
                "Punkte / Kurs": res_i['price'],
                "1W %": res_i['perf']['1W'],
                "1M %": res_i['perf']['1M'],
                "3M %": res_i['perf']['3M'],
                "6M %": res_i['perf']['6M'],
                "1Y %": res_i['perf']['1Y'],
                "RSI (14)": res_i['rsi'],
                "Kurzfrist-Trend": res_i['short_term'][' verdict'],
                "Mittelfrist-Trend": res_i['mid_term']['verdict'],
                "Langfrist-Trend": res_i['long_term']['verdict']
            })
    st.dataframe(pd.DataFrame(idx_rows), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Gesamtmarkt-Screening (aus dem letzten Batch-Lauf)")
    st.caption(
        "Kompakte Vollbild-Ansicht aller knapp 600 Aktien aus S&P 500, DAX 40 und MDAX. "
        "**Tipp:** Über die erste Spalte **'⭐'** nimmst du jede Aktie per Klick direkt in deine Fokus-Liste (Tab 1) auf."
    )
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            batch_data = json.load(f)
        st.caption(f"Letztes automatisches Update: {batch_data.get('timestamp', 'Unbekannt')} | Analysierte Aktien: {len(batch_data.get('results', []))}")
        df_batch = pd.DataFrame(batch_data.get('results', []))
        if not df_batch.empty:
            if 'name' not in df_batch.columns:
                df_batch['name'] = df_batch['ticker']
            if 'sector' not in df_batch.columns:
                df_batch['sector'] = 'Unbekannt'

            col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 1.6])
            with col_f1:
                search_query = st.text_input("🔎 Suche nach Ticker oder Name (z. B. CARR):", value="")
            with col_f2:
                min_score = st.slider(
                    "Mindest-Score (0 = alle Aktien, ab 60 = Kauf):",
                    0, 100, 0
                )
            with col_f3:
                all_sectors = sorted(df_batch['sector'].dropna().unique().tolist())
                selected_sectors = st.multiselect(
                    "Sektor-Filter (leer = alle):",
                    options=all_sectors,
                    default=[]
                )

            filtered_df = df_batch[df_batch['total_score'] >= min_score].copy()
            if selected_sectors:
                filtered_df = filtered_df[filtered_df['sector'].isin(selected_sectors)]
            if search_query.strip():
                q = search_query.strip().lower()
                filtered_df = filtered_df[
                    filtered_df['ticker'].astype(str).str.lower().str.contains(q) |
                    filtered_df['name'].astype(str).str.lower().str.contains(q)
                ]

            filtered_df = filtered_df.sort_values(by="total_score", ascending=False)
            
            for col in ['short_term', 'mid_term', 'long_term', 'overall_verdict']:
                filtered_df[col] = filtered_df[col].apply(compact_verdict)
            filtered_df['name'] = filtered_df['name'].astype(str).str.slice(0, 22)
            filtered_df['sector'] = filtered_df['sector'].astype(str).str.slice(0, 18)

            raw_tickers = filtered_df['ticker'].astype(str).str.upper()
            filtered_df.insert(0, 'in_focus', raw_tickers.isin(current_focus_list))
            filtered_df['raw_ticker'] = raw_tickers
            filtered_df['ticker'] = "https://finance.yahoo.com/quote/" + raw_tickers

            edited_df = st.data_editor(
                filtered_df,
                column_order=[
                    "in_focus", "ticker", "name", "sector", "price",
                    "1W %", "1M %", "3M %", "1Y %", "rsi",
                    "short_term", "mid_term", "long_term",
                    "total_score", "overall_verdict", "stop_loss", "take_profit"
                ],
                column_config={
                    "in_focus": st.column_config.CheckboxColumn(
                        "⭐", width="small",
                        help="Anhaken, um diese Aktie in 'Meine Fokus-Aktien' (Tab 1) zu übernehmen oder abzuwählen.",
                        default=False
                    ),
                    "raw_ticker": None,
                    "ticker": st.column_config.LinkColumn(
                        "Ticker", width="small",
                        help="Klicken, um das Wertpapier auf Yahoo Finance in einem neuen Tab zu öffnen.",
                        display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                    ),
                    "name": st.column_config.TextColumn("Name", width="small", help="Unternehmensname"),
                    "sector": st.column_config.TextColumn("Sektor", width="small", help="Wirtschaftszweig nach GICS"),
                    "price": st.column_config.NumberColumn("Kurs", width="small", help="Letzter Schlusskurs", format="%.2f"),
                    "1W %": st.column_config.NumberColumn("1W", width="small", help="Performance 1 Woche in %", format="%.1f%%"),
                    "1M %": st.column_config.NumberColumn("1M", width="small", help="Performance 1 Monat in %", format="%.1f%%"),
                    "3M %": st.column_config.NumberColumn("3M", width="small", help="Performance 3 Monate in %", format="%.1f%%"),
                    "1Y %": st.column_config.NumberColumn("1Y", width="small", help="Performance 1 Jahr in %", format="%.1f%%"),
                    "rsi": st.column_config.NumberColumn("RSI", width="small", help="Relative Strength Index (14 Tage)", format="%.0f"),
                    "short_term": st.column_config.TextColumn("Kurz", width="small", help="Kurzfristige Einschätzung (1–4 Wochen)"),
                    "mid_term": st.column_config.TextColumn("Mittel", width="small", help="Mittelfristige Einschätzung (1–6 Monate)"),
                    "long_term": st.column_config.TextColumn("Lang", width="small", help="Langfristige Einschätzung (6+ Monate)"),
                    "total_score": st.column_config.NumberColumn("Score", width="small", help="Gewichteter Gesamt-Score (0–100)", format="%.1f"),
                    "overall_verdict": st.column_config.TextColumn("Urteil", width="small", help="Zusammenfassende Handlungsempfehlung"),
                    "stop_loss": st.column_config.NumberColumn("SL", width="small", help="Stop-Loss (2x ATR unter Kurs)", format="%.2f"),
                    "take_profit": st.column_config.NumberColumn("TP", width="small", help="Kursziel (3.5x ATR über Kurs)", format="%.2f")
                },
                disabled=[c for c in filtered_df.columns if c != 'in_focus'],
                use_container_width=True,
                hide_index=True,
                height=650,
                key="market_editor"
            )

            currently_checked = set(edited_df[edited_df['in_focus']]['raw_ticker'])
            previously_checked_in_view = set(filtered_df[filtered_df['in_focus']]['raw_ticker'])

            if currently_checked != previously_checked_in_view:
                added = currently_checked - previously_checked_in_view
                removed = previously_checked_in_view - currently_checked

                updated_universe = [t for t in current_focus_list if t not in removed]
                for t in added:
                    if t not in updated_universe:
                        updated_universe.append(t)

                config['universe'] = updated_universe
                save_config(config)
                st.toast(f"Fokus-Aktien aktualisiert! (+{len(added)} / -{len(removed)})", icon="✅")
                st.rerun()
    else:
        st.info("Noch keine Batch-Daten vorhanden. Führe einmal `python3 src/main.py` aus, um den Gesamtmarkt-Cache zu füllen.")
