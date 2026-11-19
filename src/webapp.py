import os
import json
import yaml
from datetime import date
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from indicators import TechnicalIndicators
from advisor import InvestmentAdvisor
from intraday import IntradayAnalyzer
from derivatives import DerivativesAdvisor
from dataclasses import asdict
from portfolio import DerivativesPortfolio, DerivateSpec

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

@st.cache_data(ttl=3600)
def fetch_cached_earnings_days(ticker: str):
    return DerivativesPortfolio.get_next_earnings_days(ticker)

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

def plot_portfolio_overview(evaluated_list: list):
    active = [x for x in evaluated_list if x['status'] != "Geschlossen"]
    if not active:
        return

    fig = make_subplots(
        rows=1, cols=2,
        shared_yaxes=True,
        column_widths=[0.66, 0.34],
        horizontal_spacing=0.05,
        subplot_titles=(
            "🎯 Positions-Radar: 💀 KO (0%) ➔ 🛡️ Stop-Loss ➔ ⚪ Kauf ➔ ⭐ LIVE ➔ 💰 Ziel 1 ➔ 🏆 Ziel 2 (100%)",
            "💶 Aktueller Gewinn / Verlust (€ & %) vs. Geplantes SL-Risiko"
        )
    )

    labels = []
    ko_x, sl_x, entry_x, curr_x, tp1_x, tp2_x = [], [], [], [], [], []
    ko_txt, sl_txt, entry_txt, curr_txt, tp1_txt, tp2_txt = [], [], [], [], [], []
    pnl_vals, pnl_colors, pnl_texts, risk_vals = [], [], [], []

    for ev in reversed(active):
        cur = ev['currency']
        lbl = f"<b>{ev['ticker']}</b> ({ev['wkn']} | {ev['direction']})"
        labels.append(lbl)

        is_long = ev['direction'] == "Long"
        ko = ev['adjusted_ko']
        tp2 = ev['tp2_underlying']
        span = (tp2 - ko) if is_long else (ko - tp2)
        if abs(span) < 1e-6:
            span = 1.0

        def norm(val):
            pct = ((val - ko) / span * 100.0) if is_long else ((ko - val) / span * 100.0)
            return round(max(-15.0, min(130.0, pct)), 1)

        n_ko = 0.0
        n_sl = norm(ev['sl_underlying'])
        n_ent = norm(ev['entry_underlying'])
        n_cur = norm(ev['current_underlying'])
        n_tp1 = norm(ev['tp1_underlying'])
        n_tp2 = 100.0

        # Hintergrund-Leitlinie (0% bis 100%) + Rote Gefahrenzone (KO bis SL)
        fig.add_trace(go.Scatter(
            x=[0, 100], y=[lbl, lbl], mode="lines",
            line=dict(color="#343a40", width=10), showlegend=False, hoverinfo="skip"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=[0, max(0, n_sl)], y=[lbl, lbl], mode="lines",
            line=dict(color="rgba(239, 71, 111, 0.45)", width=10), showlegend=False, hoverinfo="skip"
        ), row=1, col=1)

        ko_x.append(n_ko)
        ko_txt.append(f"KO-Schwelle: {ko:.2f} {cur} (0.00 €) | Puffer: {ev['ko_dist_pct']:.1f}%")

        sl_x.append(n_sl)
        sl_txt.append(f"Stop-Loss: {ev['sl_underlying']:.2f} {cur} (Schein: {ev['cert_sl_eur']:.2f} €)")

        entry_x.append(n_ent)
        entry_txt.append(f"Kaufkurs: {ev['entry_underlying']:.2f} {cur} (Schein: {ev['entry_cert_eur']:.2f} €)")

        curr_x.append(n_cur)
        curr_txt.append(f"LIVE-Stand: {ev['current_underlying']:.2f} {cur} (Schein: {ev['current_cert_eur']:.2f} € | Hebel: {ev['real_leverage']:.1f}x)")

        tp1_x.append(n_tp1)
        tp1_txt.append(f"Ziel 1 (50% Free-Ride): {ev['tp1_underlying']:.2f} {cur} (Schein: {ev['cert_tp1_eur']:.2f} €)")

        tp2_x.append(n_tp2)
        tp2_txt.append(f"Hauptziel 2: {ev['tp2_underlying']:.2f} {cur} (Schein: {ev['cert_tp2_eur']:.2f} €)")

        pnl_vals.append(ev['pnl_eur'])
        pnl_colors.append("#06d6a0" if ev['pnl_eur'] >= 0 else "#ef476f")
        pnl_texts.append(f"{ev['pnl_eur']:+.2f} € ({ev['pnl_pct']:+.1f}%)")
        risk_vals.append(-abs(ev['initial_risk_eur']))

    # Marker für die 6 Schlüsselmarken auf der normierten Skala hinzufügen
    fig.add_trace(go.Scatter(
        x=ko_x, y=labels, mode="markers", name="💀 KO-Schwelle (0%)",
        marker=dict(symbol="x", size=13, color="#ff0055", line=dict(width=2)),
        text=ko_txt, hovertemplate="%{y}<br>%{text}<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=sl_x, y=labels, mode="markers", name="🛡️ Stop-Loss",
        marker=dict(symbol="line-ns", size=18, color="#ff9f1c", line=dict(width=4, color="#ff9f1c")),
        text=sl_txt, hovertemplate="%{y}<br>%{text}<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=entry_x, y=labels, mode="markers", name="⚪ Kaufkurs (Einstieg)",
        marker=dict(symbol="circle-open", size=12, color="#adb5bd", line=dict(width=2.5)),
        text=entry_txt, hovertemplate="%{y}<br>%{text}<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=tp1_x, y=labels, mode="markers", name="💰 Ziel 1 (50% Free-Ride)",
        marker=dict(symbol="diamond", size=12, color="#4cc9f0"),
        text=tp1_txt, hovertemplate="%{y}<br>%{text}<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=tp2_x, y=labels, mode="markers", name="🏆 Hauptziel 2 (100%)",
        marker=dict(symbol="triangle-right", size=13, color="#06d6a0"),
        text=tp2_txt, hovertemplate="%{y}<br>%{text}<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=curr_x, y=labels, mode="markers+text", name="⭐ Aktueller LIVE-Stand",
        marker=dict(symbol="star", size=17, color="#ffd166", line=dict(width=1.5, color="#000000")),
        text=[f"  {ev['current_cert_eur']:.2f}€" for ev in reversed(active)],
        textposition="top center",
        hovertext=curr_txt, hovertemplate="%{y}<br>%{hovertext}<extra></extra>"
    ), row=1, col=1)

    # Rechts: G/V-Balkenchart + geplantes SL-Risiko als Referenz
    fig.add_trace(go.Bar(
        x=pnl_vals, y=labels, orientation="h", name="Aktueller G/V (€)",
        marker_color=pnl_colors, text=pnl_texts, textposition="auto",
        hovertemplate="%{y}<br>Aktueller G/V: %{text}<extra></extra>"
    ), row=1, col=2)

    fig.add_trace(go.Scatter(
        x=risk_vals, y=labels, mode="markers", name="Geplantes Max. SL-Risiko (-€)",
        marker=dict(symbol="line-ns", size=16, color="#ff9f1c", line=dict(width=3, color="#ff9f1c")),
        hovertemplate="%{y}<br>Geplantes Risiko bis SL: %{x:.2f} €<extra></extra>"
    ), row=1, col=2)

    fig.update_xaxes(title_text="Positionsspanne in % (0% = KO-Schwelle | 100% = Hauptziel 2)", range=[-10, 118], zeroline=False, row=1, col=1)
    fig.update_xaxes(title_text="Gewinn / Verlust in Euro (€)", zeroline=True, zerolinewidth=2, zerolinecolor="#adb5bd", row=1, col=2)

    chart_h = max(320, 110 + len(active) * 65)
    fig.update_layout(
        height=chart_h,
        template="plotly_dark",
        margin=dict(l=20, r=20, t=55, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.12, xanchor="left", x=0)
    )
    st.plotly_chart(fig, use_container_width=True)

def render_derivatives_panel(df_hist: pd.DataFrame, sel_data: dict, intra_eval: dict = None, is_intraday_view: bool = False):
    deriv = DerivativesAdvisor.analyze_derivatives(df_hist, sel_data, intra_eval)
    if not deriv:
        return

    cur = sel_data['currency']
    price = deriv['active_price']
    eur_usd = fetch_eur_usd_rate() if cur == "$" else 1.0

    fx_info = f" | **EUR/USD Live:** `{eur_usd:.4f}`" if cur == "$" else ""
    st.info(
        f"🎯 **Optimale Instrumenten-Wahl für {sel_data['name']} ({sel_data['ticker']}):** **{deriv['best_instrument']}**\n\n"
        f"**Begründung:** {deriv['best_reason']}  \n"
        f"**Berechnungsbasis:** **`{price:.2f} {cur}`** *({deriv['price_source']})*{fx_info} | "
        f"**Volatilität (HV20):** `{deriv['hv_20']}%` | **Vola-Ratio (HV20/HV100):** `{deriv['vola_ratio']}` | **Tages-ATR:** `{deriv['atr_pct']}%`"
    )

    d_col1, d_col2, d_col3 = st.columns(3)

    with d_col1:
        if is_intraday_view and deriv['intraday_ko']:
            iko = deriv['intraday_ko']
            st.markdown("##### ⚡ 1. Intraday Knock-Out (Turbo)")
            st.markdown(
                f"- **Ausrichtung:** `{iko['direction']}`\n"
                f"- **Empfohlener Hebel:** **`{iko['leverage']}x`**\n"
                f"- **Max. KO-Schwelle:** `{iko['ko_barrier']:.2f} {cur}` *(Puffer: {iko['dist_pct']}%)*\n"
                f"- **Mentaler Stop-Loss (Aktie):** `{iko['mental_sl']:.2f} {cur}`\n"
                f"- **Intraday-Kursziel (Aktie):** `{iko['target']:.2f} {cur}`"
            )
        else:
            sko = deriv['swing_ko']
            st.markdown("##### 🔥 1. Swing Knock-Out (Open-End Turbo)")
            st.markdown(
                f"- **Ausrichtung:** `{deriv['direction']}`\n"
                f"- **Empfohlener Hebel:** **`{sko['leverage']}x`**\n"
                f"- **Sichere KO-Schwelle (3.2x ATR):** `{sko['ko_barrier']:.2f} {cur}` *(Puffer: {sko['dist_pct']}%)*\n"
                f"- **Mentaler Stop-Loss (2.0x ATR):** `{sko['mental_sl']:.2f} {cur}`\n"
                f"- **Swing-Kursziel (3.5x ATR):** `{sko['target']:.2f} {cur}`"
            )

    with d_col2:
        w = deriv['warrant']
        st.markdown("##### 📜 2. Klassischer Optionsschein (Warrant)")
        st.markdown(
            f"- **Typ:** `{w['type']}`\n"
            f"- **Volatilitäts-Check (Vega):** {w['status']}\n"
            f"- **Empfohlener Basispreis (Strike):** ca. `{w['strike']:.1f} {cur}`\n"
            f"- **Optimales Delta:** `{w['delta']}`\n"
            f"- **Laufzeit-Regel:** {w['min_expiry']}"
        )

    with d_col3:
        f = deriv['faktor']
        st.markdown("##### 🔄 3. Faktor-Zertifikat (Konstanter Hebel)")
        st.markdown(
            f"- **Eignung:** {f['status']}\n"
            f"- **Empfohlener Faktor:** **`{f['recommended_faktor']}`**\n"
            f"- **Wichtige Handelsregel:** {f['note']}"
        )

    st.divider()

    # --- SCALABLE CAPITAL INTERAKTIVER ORDER-ASSISTENT ---
    active_ko = deriv['intraday_ko'] if (is_intraday_view and deriv['intraday_ko']) else deriv['swing_ko']
    default_is_long = "LONG" in active_ko.get('direction', deriv['direction'])
    key_prefix = f"sc_{sel_data['ticker']}_{'intra' if is_intraday_view else 'swing'}"

    st.subheader(f"📱 Scalable Capital Knock-Out Order-Assistent ({sel_data['ticker']} @ {price:.2f} {cur})")
    st.markdown(
        f"**Schritt 1 – Zertifikate-Filter in Scalable Capital öffnen (`Derivate` ➔ `{sel_data['name']}`):**\n"
        f"1. **Richtung wählen:** `{'Long' if default_is_long else 'Short'}` | **Hebel-Filter einstellen:** ca. `{max(2.0, round(active_ko['leverage']-2, 0)):.0f}x bis {round(active_ko['leverage']+2, 0):.0f}x`\n"
        f"2. **Nach Knock-Out-Schwelle in {cur} schauen:** Bei **Long** sollte die KO-Schwelle **unter `{active_ko['ko_barrier']:.2f} {cur}`** liegen (bei Short über `{active_ko['ko_barrier']:.2f} {cur}`).\n"
        f"3. Wähle dein Wunsch-Zertifikat in Scalable aus und trage unten die **KO-Schwelle** sowie den **Briefkurs (Kaufpreis in €)** ein:"
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
            help=f"Steht im Namen des Zertifikats, z. B. 'Long 377,28 Turbo' -> 377.28 {cur}",
            key=f"{key_prefix}_ko"
        )

    smart_default_ratio = 0.01 if price >= 250 else 0.10
    est_intrinsic = max(0.10, (abs(price - user_ko_barrier) * smart_default_ratio) / eur_usd)

    with sc3:
        cert_ask_eur = st.number_input(
            "Aktueller Briefkurs / Kaufpreis (in €):",
            min_value=0.05, max_value=500.0, value=round(est_intrinsic + 0.03, 2), step=0.01,
            help="Der aktuelle Kaufpreis in Euro für 1 Anteil bei Scalable Capital.",
            key=f"{key_prefix}_ask"
        )
    with sc4:
        ratio_choice = st.selectbox(
            "Bezugsverhältnis (Automatisch):",
            ["Automatisch (aus Briefkurs & KO)", "0.01 (1:100, z. B. MSFT/META)", "0.10 (1:10, z. B. NVDA/AAPL)", "1.00 (1:1)"],
            index=0,
            help="Erkennt anhand deines eingegebenen Briefkurses automatisch, ob das Zertifikat das Bezugsverhältnis 0,01, 0,10 oder 1,0 hat.",
            key=f"{key_prefix}_ratio_auto"
        )

    ko_dist_abs = (price - user_ko_barrier) if is_long else (user_ko_barrier - price)
    ko_dist_pct = (ko_dist_abs / price) * 100

    if ko_dist_pct <= 0:
        st.error(f"⚠️ Achtung: Die eingegebene KO-Schwelle ({user_ko_barrier:.2f} {cur}) liegt auf der falschen Seite des aktuellen Kurses ({price:.2f} {cur}) oder wurde bereits erreicht!")
        return

    unscaled_intrinsic_eur = ko_dist_abs / eur_usd
    if ratio_choice.startswith("Automatisch"):
        candidate_ratios = [0.001, 0.01, 0.1, 1.0, 10.0]
        ratio = min(candidate_ratios, key=lambda r: abs((unscaled_intrinsic_eur * r) - (cert_ask_eur * 0.92)))
    else:
        ratio = float(ratio_choice.split()[0])

    stock_price_eur = price / eur_usd
    eff_leverage = round((stock_price_eur * ratio) / cert_ask_eur, 2) if cert_ask_eur > 0 else 1.0
    raw_intrinsic_eur = max(0.0, unscaled_intrinsic_eur * ratio)
    premium_eur = round(cert_ask_eur - raw_intrinsic_eur, 2)

    st.caption(
        f"🔍 **Zertifikate-Check:** Erkanntes Bezugsverhältnis: **`{ratio}`** | "
        f"Realer Effektiv-Hebel: **`{eff_leverage:.2f}x`** | "
        f"Abstand zum Knock-Out: **`{ko_dist_pct:.2f}%`** (`{ko_dist_abs:.2f} {cur}`) | "
        f"Innerer Wert: **`{raw_intrinsic_eur:.2f} €`** (Aufgeld: `{premium_eur:+.2f} €` pro Schein)"
    )

    st.divider()
    st.markdown("**Schritt 3 – Kauf-Parameter (Betrag / Stückzahl & Order-Typ) festlegen:**")
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        sizing_mode = st.selectbox(
            "Wie möchtest du die Größe bestimmen?",
            ["1. Nach maximalem Risiko (in € / 1-2% Regel)", "2. Fester Zielbetrag (Investition in €)", "3. Feste Stückzahl (Anteile)"],
            key=f"{key_prefix}_smode"
        )
    with p_col2:
        if sizing_mode.startswith("1."):
            user_budget_val = st.number_input("Max. erlaubter Verlust bis Stop-Loss (€):", min_value=5.0, max_value=10000.0, value=25.0, step=5.0, key=f"{key_prefix}_rval")
        elif sizing_mode.startswith("2."):
            user_budget_val = st.number_input("Gewünschter Investitionsbetrag (€):", min_value=10.0, max_value=50000.0, value=300.0, step=25.0, key=f"{key_prefix}_ival")
        else:
            user_budget_val = st.number_input("Gewünschte Stückzahl (Anteile):", min_value=1, max_value=50000, value=100, step=10, key=f"{key_prefix}_sval")

    atr_val = float(sel_data['atr'])
    default_sl_stock = float(active_ko['mental_sl']) if (is_long == default_is_long) else round(price - 1.5 * atr_val if is_long else price + 1.5 * atr_val, 2)
    default_tp2_stock = float(active_ko['target']) if (is_long == default_is_long) else round(price + 2.5 * atr_val if is_long else price - 2.5 * atr_val, 2)
    default_tp1_stock = round(price + (default_tp2_stock - price) * 0.55, 2)

    with p_col3:
        sl_input_mode = st.radio(
            "Stop-Loss Vorgabe als:",
            [f"Basiswert ({cur})", "Zertifikat Stop-Preis (€)"],
            horizontal=True,
            key=f"{key_prefix}_slmode"
        )
        default_cert_sl = max(0.01, round(cert_ask_eur - ((abs(price - default_sl_stock) * ratio) / eur_usd), 2))
        if sl_input_mode.startswith("Basiswert"):
            sl_stock = st.number_input(
                f"Stop-Loss im Aktienchart ({cur}):",
                value=float(default_sl_stock), step=0.25,
                help=f"Entspricht ca. {default_cert_sl:.2f} € im Zertifikat.",
                key=f"{key_prefix}_slstock"
            )
        else:
            user_cert_sl = st.number_input(
                "Dein Stop-Preis bei Scalable (€):",
                min_value=0.01, max_value=float(cert_ask_eur), value=float(default_cert_sl), step=0.01,
                help="Der Stop-Loss-Kurs in Euro, den du bei Scalable für das Zertifikat eingibst.",
                key=f"{key_prefix}_slcert"
            )
            cert_diff_eur = max(0.0, cert_ask_eur - user_cert_sl)
            stock_diff_calc = (cert_diff_eur * eur_usd) / ratio if ratio > 0 else 0.0
            sl_stock = round((price - stock_diff_calc) if is_long else (price + stock_diff_calc), 2)
            st.caption(f"↳ Entspricht Basiswert-Stopp bei **`{sl_stock:.2f} {cur}`**")
    with p_col4:
        entry_type = st.selectbox(
            "Einstiegs-Art bei Scalable:",
            ["Sofortkauf (nur LIMIT hinzufügen)", "Breakout-Kauf (STOP + LIMIT hinzufügen)"],
            help="Sofortkauf = Du kaufst jetzt zum aktuellen Kurs mit Limit-Schutz. Breakout-Kauf = Order wird erst ausgelöst, wenn das Zertifikat über den STOP-Preis steigt.",
            key=f"{key_prefix}_etype"
        )

    if (is_long and sl_stock <= user_ko_barrier) or (not is_long and sl_stock >= user_ko_barrier):
        st.warning(
            f"⚠️ Dein gewählter Stop-Loss im Aktienchart ({sl_stock:.2f} {cur}) liegt jenseits der Knock-Out-Schwelle ({user_ko_barrier:.2f} {cur})! "
            f"Das Zertifikat wäre vorher bereits ausgeknockt (Totalverlust). Bitte setze den Stop-Loss näher an den aktuellen Kurs ({price:.2f} {cur})."
        )

    stock_diff_to_sl = abs(price - sl_stock)
    cert_loss_per_share_eur = (stock_diff_to_sl * ratio) / eur_usd
    cert_sl_eur = max(0.01, round(cert_ask_eur - cert_loss_per_share_eur, 2))
    actual_loss_per_share = max(0.01, round(cert_ask_eur - cert_sl_eur, 2))
    cert_loss_pct = (actual_loss_per_share / cert_ask_eur) * 100

    stock_diff_to_tp2 = abs(default_tp2_stock - price)
    cert_gain_per_share_eur = (stock_diff_to_tp2 * ratio) / eur_usd
    cert_tp_eur = round(cert_ask_eur + cert_gain_per_share_eur, 2)
    cert_gain_pct = (cert_gain_per_share_eur / cert_ask_eur) * 100

    if sizing_mode.startswith("1."):
        shares = max(1, int(user_budget_val // actual_loss_per_share))
    elif sizing_mode.startswith("2."):
        shares = max(1, int(user_budget_val // cert_ask_eur))
    else:
        shares = int(user_budget_val)

    total_invest_eur = round(shares * cert_ask_eur, 2)
    total_risk_eur = round(shares * actual_loss_per_share, 2)
    total_profit_eur = round(shares * (cert_tp_eur - cert_ask_eur), 2)

    if entry_type.startswith("Sofortkauf"):
        buy_stop_str = "Nicht aktivieren (leer lassen)"
        buy_limit_eur = round(max(cert_ask_eur + 0.01, cert_ask_eur * 1.01), 2)
        buy_mode_hint = "Schützt dich vor Slippage (max. +1% über Briefkurs statt der 4% Standard-Toleranz)."
    else:
        orb_trigger_stock = intra_eval['orb_high'] if (intra_eval and is_long and intra_eval['orb_high'] > price) else round(price * (1.005 if is_long else 0.995), 2)
        diff_to_trigger = abs(orb_trigger_stock - price)
        trigger_cert_eur = round(cert_ask_eur + ((diff_to_trigger * ratio) / eur_usd), 2)
        buy_stop_str = f"{trigger_cert_eur:.2f} €"
        buy_limit_eur = round(trigger_cert_eur + max(0.02, trigger_cert_eur * 0.01), 2)
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
        sell_sl_limit_eur = max(0.01, round(cert_sl_eur - max(0.01, cert_sl_eur * 0.015), 2))
        st.warning(
            f"**🛡️ B. Eingabe direkt NACH dem Kauf (Verkaufs-Absicherung / Stop-Loss):**\n\n"
            f"- **Stop-Loss STOP-Preis (Auslöser bei Aktie {sl_stock:.2f} {cur}):** **`{cert_sl_eur:.2f} €`** *(-{cert_loss_pct:.1f}%)*\n"
            f"- **Stop-Loss LIMIT-Preis (Mindestverkaufspreis):** **`{sell_sl_limit_eur:.2f} €`** *(Puffer für sichere Ausführung)*\n"
            f"- **Teilverkauf 50% (Free-Ride bei Ziel 1 = {default_tp1_stock:.2f} {cur}) / Hauptziel 2 ({default_tp2_stock:.2f} {cur}):** **`{cert_tp_eur:.2f} €`** *(+{cert_gain_pct:.1f}%)*\n"
            f"- **Dein exaktes Euro-Ergebnis:** Risiko bis Stop-Loss: **`-{total_risk_eur:.2f} €`** | Gewinn am Ziel: **`+{total_profit_eur:.2f} €`**"
        )

    # --- 1-KLICK ÜBERNAHME INS DERIVATE-LOGBUCH (SÄULE 1 & 2) ---
    with st.expander("📌 Diesen Trade nach Kauf direkt in '💼 Mein Derivate-Depot (Logbuch)' übernehmen"):
        l1, l2, l3, l4, l5 = st.columns(5)
        with l1:
            wkn_in = st.text_input("WKN / ISIN (optional):", placeholder="z. B. PC8XYZ", key=f"{key_prefix}_wkn")
        with l2:
            issuer_in = st.selectbox("Emittent:", ["BNP Paribas", "HSBC", "Vontobel", "UniCredit", "Société Générale", "Goldman Sachs"], key=f"{key_prefix}_iss")
        with l3:
            tp1_in = st.number_input(f"Kursziel 1 (50% Teilverkauf, {cur}):", value=float(default_tp1_stock), step=0.5, key=f"{key_prefix}_tp1")
        with l4:
            tp2_in = st.number_input(f"Kursziel 2 (Hauptziel, {cur}):", value=float(default_tp2_stock), step=0.5, key=f"{key_prefix}_tp2")
        with l5:
            max_days_in = st.number_input("Zeit-Stopp (Max. Handelstage):", min_value=1, max_value=90, value=5 if is_intraday_view else 12, key=f"{key_prefix}_mdays")

        if st.button("💾 Trade jetzt im Derivate-Logbuch speichern", key=f"{key_prefix}_save_btn", use_container_width=True):
            DerivativesPortfolio.add_position({
                "ticker": sel_data['ticker'],
                "name": sel_data['name'],
                "wkn": wkn_in.strip().upper() or "KO-TURBO",
                "issuer": issuer_in,
                "direction": "Long" if is_long else "Short",
                "buy_date": date.today().isoformat(),
                "shares": int(shares),
                "entry_cert_eur": float(cert_ask_eur),
                "entry_underlying": float(price),
                "sl_underlying": float(sl_stock),
                "tp1_underlying": float(tp1_in),
                "tp2_underlying": float(tp2_in),
                "ko_barrier": float(user_ko_barrier),
                "ratio": float(ratio),
                "initial_leverage": float(eff_leverage),
                "premium_eur": float(premium_eur),
                "currency": cur,
                "max_hold_days": int(max_days_in),
                "fin_rate_pa": 7.5,
                "status": "Aktiv"
            })
            st.success(f"Trade für {sel_data['ticker']} ({shares} Stück à {cert_ask_eur:.2f} €) wurde im Reiter '💼 Mein Derivate-Depot' gespeichert!")

st.title("🏛️ Persönlicher Aktien- & Derivate-Anlageberater")
st.markdown(
    "Dieses Dashboard kombiniert **technische Chartanalyse**, **Intraday-Signale (VWAP, Pivots, ORB)**, **fundamentale Bewertung**, "
    "den **Scalable Capital Order-Assistenten** und ein **4-Säulen Derivate-Depot-Management**."
)

with st.expander("📖 Lexikon & Methodik: Indikatoren, Intraday-Marken & Das 4-Säulen-Derivate-Management"):
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.markdown("""
        **📈 Swing- & Intraday-Indikatoren**
        * **RSI (14), EMA 20, SMA 50/200, MACD & Bollinger:** Klassische Trend- und Rebound-Indikatoren im Tageschart.
        * **VWAP & Opening Range (ORB):** Institutioneller Tages-Durchschnittspreis und 30-Minuten-Ausbruchsspanne im 5m-Chart.
        * **Floor Pivots ($P, R_1, R_2, S_1, S_2$):** Mathematische Tages-Widerstände und -Unterstützungen aus dem Vortag.
        """)
    with col_g2:
        st.markdown("""
        **🛡️ Säule 1 & 2: Logbuch & Pre-Trade-Regeln**
        * **Basiswert-Entkopplung:** Stop-Loss und Kursziele werden immer im Chart der Aktie festgelegt und erst über das Bezugsverhältnis in Euro-Zertifikatspreise umgerechnet.
        * **1–2 % Risiko-Deckel:** Pro Trade maximal 1–2 % des gesamten Trading-Kapitals bis zum Stop-Loss riskieren.
        * **Barriere-Drift:** Bei Open-End-Turbos verschiebt der Emittent die KO-Schwelle täglich um die Zinskosten (~7,5 % p.a.).
        """)
    with col_g3:
        st.markdown("""
        **🎯 Säule 3 & 4: Die 3-Szenarien-Exit-Matrix**
        * **Szenario A (Gewinn):** Bei **+100 % Gewinn** oder **Ziel 1** werden **50 % verkauft (Free-Ride)**. Sinkt der Real-Hebel stark ab (*Hebel-Kompression*), wird gerollt.
        * **Szenario B (Hard Exit):** Bricht der Basiswert unter den Chart-Stop-Loss, wird sofort verkauft (*No Averaging Down!*).
        * **Szenario C (Time & Event Exit):** Stagniert der Trade über das Zeit-Limit hinaus oder stehen **Quartalszahlen (Earnings)** in <5 Tagen an, wird wegen Overnight-Gap-Gefahr glattgestellt.
        """)

config = load_config()
current_focus_list = [t.strip().upper() for t in config.get('universe', ['AAPL', 'MSFT', 'NVDA', 'CARR', 'SAP.DE', 'SIE.DE'])]

watchlist_results = []
for t in current_focus_list:
    df_t = fetch_single_history(t)
    fund_t = fetch_fundamentals(t)
    res = InvestmentAdvisor.analyze_ticker(t, df_t, fund_t)
    if res:
        res['name'] = fund_t['name']
        res['sector'] = fund_t['sector']
        res['pe'] = round(fund_t['pe'], 1) if fund_t['pe'] else None
        res['fcf_yield'] = round(fund_t['fcf_yield'], 1) if fund_t['fcf_yield'] else None
        watchlist_results.append(res)

if "active_focus_ticker" not in st.session_state or st.session_state["active_focus_ticker"] not in current_focus_list:
    st.session_state["active_focus_ticker"] = current_focus_list[0] if current_focus_list else "AAPL"

tab1, tab_deriv, tab_port, tab2, tab3 = st.tabs([
    "🎯 Meine Fokus-Aktien (Charts & Intraday)",
    "⚡ Derivate & Scalable-Assistent",
    "💼 Mein Derivate-Depot (Logbuch & Exit-Matrix)",
    "🌍 Indizes & Markt-Kompass",
    "🔍 Gesamtmarkt-Screener"
])

with tab1:
    st.subheader("Persönliche Watchlist & Detail-Chartanalyse")
    st.caption(
        "Hier werden deine Fokus-Aktien auf drei Zeitebenen sowie im 5-Minuten-Intraday-Chart analysiert."
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
            selected_ticker = st.selectbox(
                "🔎 Aktie für Chart-Analyse auswählen:",
                current_focus_list,
                index=current_focus_list.index(st.session_state["active_focus_ticker"]),
                key="tab1_ticker_select"
            )
            st.session_state["active_focus_ticker"] = selected_ticker
        with col_mode:
            analysis_mode = st.radio(
                "Chart-Ansicht wählen:",
                ["📊 Multi-Horizont-Analyse (Tageschart)", "⚡ Live Intraday-Cockpit (5-Minuten-Chart)"],
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
                if st.button("🔄 Kursdaten aktualisieren", key="btn_refresh_tab1"):
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

                plot_intraday_chart(df_intra, intra_eval, selected_ticker)
            else:
                st.warning("Für diesen Ticker konnten aktuell keine 5-Minuten-Intraday-Daten geladen werden.")

with tab_deriv:
    st.subheader("⚡ Derivate-Playbook & Scalable Capital Order-Assistent")
    st.caption(
        "Dediziertes Terminal für **Knock-Out-Zertifikate (Turbos), Optionsscheine und Faktor-Zertifikate** auf Echtzeit-Kursbasis (inkl. 1-Klick-Übernahme ins Derivate-Logbuch)."
    )

    if watchlist_results:
        d_top1, d_top2, d_top3 = st.columns([1.2, 1.8, 0.8])
        with d_top1:
            deriv_ticker = st.selectbox(
                "🔎 Fokus-Aktie auswählen:",
                current_focus_list,
                index=current_focus_list.index(st.session_state["active_focus_ticker"]),
                key="tab_deriv_ticker_select"
            )
            st.session_state["active_focus_ticker"] = deriv_ticker
        with d_top2:
            deriv_horizon = st.radio(
                "Handels-Horizont für das Derivat:",
                ["🔥 Swing-Trading (Mehrere Tage bis Wochen / ATR-basiert)", "⚡ Intraday / Daytrading (Heutige Pivots & Opening Range)"],
                horizontal=True
            )
        with d_top3:
            st.write("")
            if st.button("🔄 Live-Kurse aktualisieren", key="btn_refresh_deriv", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        sel_deriv_data = next((item for item in watchlist_results if item['ticker'] == deriv_ticker), None)
        df_hist_deriv = fetch_single_history(deriv_ticker)
        df_intra_deriv, pivots_deriv = fetch_cached_intraday(deriv_ticker, interval="5m", include_prepost=not deriv_ticker.endswith(".DE"))
        intra_eval_deriv = IntradayAnalyzer.evaluate_intraday(df_intra_deriv, pivots_deriv, currency=sel_deriv_data['currency']) if sel_deriv_data else None

        if sel_deriv_data:
            is_intra_mode = deriv_horizon.startswith("⚡")
            render_derivatives_panel(df_hist_deriv, sel_deriv_data, intra_eval=intra_eval_deriv, is_intraday_view=is_intra_mode)
    else:
        st.info("Bitte füge zuerst mindestens eine Fokus-Aktie in Tab 1 hinzu.")

with tab_port:
    st.subheader("💼 Mein Derivate-Depot: 4-Säulen-Logbuch & 3-Szenarien-Exit-Matrix")
    st.caption(
        "Trennt strikt zwischen der Chart-Analyse des Basiswerts und der positionsbezogenen Derivate-Steuerung (inkl. automatischer Zins-Anpassung der KO-Barriere, Hebel-Kompressions-Check und Earnings-Warnung)."
    )

    port_data = DerivativesPortfolio.load_data()
    eur_usd_live = fetch_eur_usd_rate()

    # Kopfzeile: Trading-Kapital (für 1-2% Risiko-Deckel) & Live-Refresh
    top_p1, top_p2, top_p3 = st.columns([1.5, 2.0, 1.0])
    with top_p1:
        new_cap = st.number_input(
            "Gesamtes Trading-Kapital für Derivate (in €):",
            min_value=500.0, max_value=1000000.0, value=float(port_data.get("capital", 10000.0)), step=500.0,
            help="Dient als Basis für die 1%- bis 2%-Risiko-Regel pro Knock-Out-Trade."
        )
        if new_cap != port_data.get("capital"):
            port_data["capital"] = new_cap
            DerivativesPortfolio.save_data(port_data)
    with top_p2:
        st.info(
            f"**🛡️ Dein Pre-Trade Risiko-Deckel (1 % bis 2 % Regel):**  \n"
            f"Maximal erlaubtes Risiko pro Position (Kaufkurs bis Stop-Loss): **`{new_cap*0.01:.0f} €` (1 %)** bis **`{new_cap*0.02:.0f} €` (2 %)**"
        )
    with top_p3:
        st.write("")
        if st.button("🔄 Depot & Live-Kurse prüfen", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    positions = port_data.get("positions", [])
    active_positions = [p for p in positions if p.get("status") != "Geschlossen"]

    # Alle aktiven Positionen live gegen aktuelle 5m-Kurse & Earnings evaluieren
    evaluated_list = []
    for p in active_positions:
        t_sym = p.get("ticker", "AAPL")
        df_i_p, piv_p = fetch_cached_intraday(t_sym, interval="5m", include_prepost=not t_sym.endswith(".DE"))
        if not df_i_p.empty:
            live_u_price = float(df_i_p['Close'].iloc[-1])
        else:
            df_h_p = fetch_single_history(t_sym, period="1mo")
            live_u_price = float(df_h_p['Close'].iloc[-1]) if not df_h_p.empty else float(p.get("entry_underlying", 100.0))

        e_days = fetch_cached_earnings_days(t_sym)
        ev = DerivativesPortfolio.evaluate_position(p, live_u_price, eur_usd_live, new_cap, earnings_days=e_days)
        evaluated_list.append(ev)

    if evaluated_list:
        total_invested = sum(x['invested_eur'] for x in evaluated_list)
        total_current = sum(x['current_val_eur'] for x in evaluated_list)
        total_pnl = total_current - total_invested
        total_pnl_pct = ((total_current / total_invested) - 1.0) * 100 if total_invested > 0 else 0.0
        total_open_risk = sum(x['initial_risk_eur'] for x in evaluated_list)
        total_risk_pct = (total_open_risk / new_cap) * 100 if new_cap > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Gebundenes Kapital (Aktiv)", f"{total_invested:.2f} €", f"{len(evaluated_list)} offene Position(en)", delta_color="off")
        k2.metric("Aktueller Positionswert", f"{total_current:.2f} €", f"{total_pnl:+.2f} € ({total_pnl_pct:+.1f}%)")
        k3.metric("Gesamtes Stop-Loss-Risiko", f"{total_open_risk:.2f} €", f"{total_risk_pct:.2f}% vom Trading-Kapital", delta_color="off")
        min_ko_puffer = min(x['ko_dist_pct'] for x in evaluated_list)
        k4.metric("Kleinster KO-Abstand im Depot", f"{min_ko_puffer:.2f} %", "Unter 5% = erhöhte Vorsicht!", delta_color="off")

        st.divider()
        st.markdown("#### 📊 Visuelles Derivate-Cockpit (Abstand zu KO, Stop-Loss, Live-Stand & Gewinn/Verlust)")
        plot_portfolio_overview(evaluated_list)

        st.divider()
        st.markdown("#### 📋 Säule 1: Das zentrale Derivate-Logbuch (Interaktiv bearbeitbar & Live-Überwachung)")
        st.caption(
            "✏️ **Direkt-Bearbeitung:** Klicke doppelt in eine Zelle mit `✏️`, um Werte nachträglich anzupassen. "
            "Setze links bei **`🗑️`** einen Haken zum Löschen und klicke auf **`💾 Änderungen im Logbuch speichern`**."
        )

        editor_rows = []
        for ev in evaluated_list:
            editor_rows.append({
                "delete": False,
                "id": ev['id'],
                "ticker": ev['ticker'],
                "wkn": ev['wkn'],
                "direction": ev['direction'],
                "status": ev['status'],
                "shares": int(ev['shares']),
                "entry_cert_eur": float(ev['entry_cert_eur']),
                "current_cert_eur": float(ev['current_cert_eur']),
                "_orig_current_cert_eur": float(ev['current_cert_eur']),
                "pnl_display": f"{ev['pnl_eur']:+.2f} € ({ev['pnl_pct']:+.1f}%)",
                "entry_underlying": float(ev['entry_underlying']),
                "current_underlying": float(ev['current_underlying']),
                "cert_sl_eur": float(ev['cert_sl_eur']),
                "_orig_cert_sl_eur": float(ev['cert_sl_eur']),
                "sl_underlying": float(ev['sl_underlying']),
                "tp1_underlying": float(ev['tp1_underlying']),
                "tp2_underlying": float(ev['tp2_underlying']),
                "initial_ko": float(ev['initial_ko']),
                "ko_live_display": f"{ev['adjusted_ko']:.2f} ({ev['ko_dist_pct']:.1f}%)",
                "ratio": float(ev['ratio']),
                "lev_display": f"{ev['initial_leverage']:.1f}x ➔ {ev['real_leverage']:.1f}x",
                "max_hold_days": int(ev['max_hold_days']),
                "matrix_scenario": ev['matrix_scenario']
            })

        edited_log_df = st.data_editor(
            pd.DataFrame(editor_rows),
            column_order=[
                "delete", "ticker", "wkn", "direction", "status", "shares",
                "entry_cert_eur", "current_cert_eur", "pnl_display",
                "entry_underlying", "current_underlying", "cert_sl_eur", "sl_underlying", "tp1_underlying", "tp2_underlying",
                "initial_ko", "ko_live_display", "ratio", "lev_display", "max_hold_days", "matrix_scenario"
            ],
            column_config={
                "delete": st.column_config.CheckboxColumn("🗑️", width="small", help="Anhaken zum Löschen", default=False),
                "id": None,
                "ticker": st.column_config.TextColumn("Ticker", width="small"),
                "wkn": st.column_config.TextColumn("WKN ✏️", width="small"),
                "direction": st.column_config.SelectboxColumn("Typ ✏️", options=["Long", "Short"], width="small", required=True),
                "status": st.column_config.SelectboxColumn("Status ✏️", options=["Aktiv", "Teilverkauf (Free-Ride)", "Geschlossen"], width="small", required=True),
                "shares": st.column_config.NumberColumn("Stück ✏️", min_value=1, max_value=100000, step=1, width="small"),
                "entry_cert_eur": st.column_config.NumberColumn("Kauf (€) ✏️", min_value=0.01, max_value=1000.0, step=0.01, format="%.2f €", width="small"),
                "current_cert_eur": st.column_config.NumberColumn("Live (€) ✏️", min_value=0.01, step=0.01, format="%.2f €", width="small", help="Rechnerischer Live-Preis. Tipp: Überschreibe ihn einmalig mit dem aktuellen Scalable-Geldkurs, um Aufgeld & Spread exakt zu eichen!"),
                "pnl_display": st.column_config.TextColumn("G/V (Live)", width="small"),
                "entry_underlying": st.column_config.NumberColumn("Basis-Kauf ✏️", min_value=0.01, step=0.5, format="%.2f", width="small"),
                "_orig_cert_sl_eur": None,
                "_orig_current_cert_eur": None,
                "current_underlying": st.column_config.NumberColumn("Basis-Live", format="%.2f", width="small"),
                "cert_sl_eur": st.column_config.NumberColumn("SL Schein (€) ✏️", min_value=0.01, step=0.01, format="%.2f €", width="small", help="Stop-Preis des Zertifikats in € bei Scalable (ändert automatisch SL Aktie)"),
                "sl_underlying": st.column_config.NumberColumn("SL (Aktie) ✏️", min_value=0.01, step=0.5, format="%.2f", width="small", help="Chart-Stop-Loss im Basiswert (ändert automatisch SL Schein €)"),
                "tp1_underlying": st.column_config.NumberColumn("Ziel 1 ✏️", min_value=0.01, step=0.5, format="%.2f", width="small"),
                "tp2_underlying": st.column_config.NumberColumn("Ziel 2 ✏️", min_value=0.01, step=0.5, format="%.2f", width="small"),
                "initial_ko": st.column_config.NumberColumn("Start-KO ✏️", min_value=0.01, step=0.5, format="%.2f", width="small"),
                "ko_live_display": st.column_config.TextColumn("KO Heute (Puffer)", width="small"),
                "ratio": st.column_config.SelectboxColumn("Bezug ✏️", options=[0.001, 0.01, 0.1, 1.0, 10.0], width="small", required=True),
                "lev_display": st.column_config.TextColumn("Hebel (Kauf➔Live)", width="small"),
                "max_hold_days": st.column_config.NumberColumn("Max.T ✏️", min_value=1, max_value=365, step=1, width="small"),
                "matrix_scenario": st.column_config.TextColumn("3-Szenarien-Signal", width="medium")
            },
            disabled=["ticker", "pnl_display", "current_underlying", "ko_live_display", "lev_display", "matrix_scenario"],
            use_container_width=True,
            hide_index=True,
            key="portfolio_table_editor"
        )

        if st.button("💾 Änderungen im Logbuch speichern / Ausgewählte (🗑️) löschen", type="primary"):
            DerivativesPortfolio.save_edited_positions(edited_log_df.to_dict("records"), eur_usd=eur_usd_live)
            st.toast("Logbuch erfolgreich aktualisiert!", icon="✅")
            st.rerun()

        st.divider()
        st.markdown("#### 🎯 Säule 3 & 4: Aktive 3-Szenarien-Matrix, TradingView-Alarme & Positions-Steuerung")

        for ev in evaluated_list:
            c_sym = ev['currency']
            box_title = (
                f"**{ev['ticker']} ({ev['name']})** | WKN: `{ev['wkn']}` ({ev['direction']}) | "
                f"**{ev['shares']} Stück** | G/V: **`{ev['pnl_eur']:+.2f} € ({ev['pnl_pct']:+.1f}%)`** | "
                f"**{ev['matrix_scenario']}**"
            )
            with st.expander(box_title, expanded=(ev['urgency'] in ("critical", "warning", "success"))):
                if ev['urgency'] == "critical":
                    st.error(f"**Handlungsanweisung (Szenario B – Hard Exit):** {ev['matrix_action']}")
                elif ev['urgency'] == "warning":
                    st.warning(f"**Handlungsanweisung (Szenario C – Time/Event Exit):** {ev['matrix_action']}")
                elif ev['urgency'] == "success":
                    st.success(f"**Handlungsanweisung (Szenario A – Take-Profit / De-Risking):** {ev['matrix_action']}")
                else:
                    st.info(f"**Status (Planmäßig):** {ev['matrix_action']}")

                w_col1, w_col2 = st.columns(2)
                with w_col1:
                    st.markdown(
                        f"**🔔 Liste 1: Preisalarme im Basiswert-Chart (z. B. TradingView für `{ev['ticker']}`):**\n"
                        f"- **🚨 Hard-Exit Alarm (Stop-Loss):** `{ev['sl_underlying']:.2f} {c_sym}`\n"
                        f"- **💰 50% Free-Ride Alarm (Kursziel 1):** `{ev['tp1_underlying']:.2f} {c_sym}`\n"
                        f"- **🏆 Hauptziel Alarm (Kursziel 2):** `{ev['tp2_underlying']:.2f} {c_sym}`\n"
                        f"- **💀 Angepasste KO-Barriere heute (inkl. Zins-Drift):** `{ev['adjusted_ko']:.2f} {c_sym}` *(Start-KO war {ev['initial_ko']:.2f} {c_sym})*"
                    )
                with w_col2:
                    sl_limit_puffer = max(0.01, round(ev['cert_sl_eur'] * 0.985, 2))
                    st.markdown(
                        f"**📱 Liste 2: Umgerechnete Zertifikats-Preise für Scalable Capital (`{ev['wkn']}`):**\n"
                        f"- **Stop-Loss Order (für alle {ev['shares']} Stück):** STOP **`{ev['cert_sl_eur']:.2f} €`** | LIMIT **`{sl_limit_puffer:.2f} €`**\n"
                        f"- **Limit-Verkauf für erste 50% ({max(1, ev['shares']//2)} Stück bei Ziel 1):** **`{ev['cert_tp1_eur']:.2f} €`**\n"
                        f"- **Limit-Verkauf für Restposition (bei Hauptziel 2):** **`{ev['cert_tp2_eur']:.2f} €`**\n"
                        f"- **Aktueller Real-Hebel:** `{ev['real_leverage']:.2f}x` *(Start-Hebel: {ev['initial_leverage']:.2f}x)*"
                    )

                b1, b2, b3, b4 = st.columns(4)
                with b1:
                    if st.button("💰 50% Teilverkauf buchen (Free-Ride + SL auf Einstieg)", key=f"act_p50_{ev['id']}", use_container_width=True):
                        DerivativesPortfolio.update_position_status(ev['id'], "partial_50")
                        st.rerun()
                with b2:
                    if st.button("🛡️ Stop-Loss auf Break-Even (Einstieg) ziehen", key=f"act_be_{ev['id']}", use_container_width=True):
                        DerivativesPortfolio.update_position_status(ev['id'], "move_sl_be")
                        st.rerun()
                with b3:
                    tr_mode = st.radio("SL-Eingabe:", [f"Aktie ({c_sym})", "Schein (€)"], horizontal=True, key=f"trm_{ev['id']}")
                    if tr_mode.startswith("Aktie"):
                        new_sl_val = st.number_input(f"Neuer SL ({c_sym}):", value=float(ev['sl_underlying']), step=0.5, key=f"inp_sl_{ev['id']}")
                    else:
                        new_cert_sl_in = st.number_input("Neuer SL Schein (€):", min_value=0.01, value=float(ev['cert_sl_eur']), step=0.01, key=f"inp_csl_{ev['id']}")
                        fx_tr = eur_usd_live if c_sym == "$" else 1.0
                        prem_tr = max(0.0, ev['current_cert_eur'] - ((abs(ev['current_underlying'] - ev['adjusted_ko']) * ev['ratio']) / fx_tr))
                        dist_u_tr = (max(0.0, new_cert_sl_in - prem_tr) * fx_tr) / ev['ratio']
                        new_sl_val = round((ev['adjusted_ko'] + dist_u_tr) if ev['direction'] == "Long" else (ev['adjusted_ko'] - dist_u_tr), 2)
                        st.caption(f"↳ Basiswert-SL: `{new_sl_val:.2f} {c_sym}`")
                    if st.button("📈 Neuen SL speichern", key=f"act_sl_{ev['id']}", use_container_width=True):
                        DerivativesPortfolio.update_position_status(ev['id'], "update_sl", new_sl_val)
                        st.rerun()
                with b4:
                    st.write("")
                    if st.button("❌ Position schließen / löschen", key=f"act_del_{ev['id']}", use_container_width=True):
                        DerivativesPortfolio.update_position_status(ev['id'], "delete")
                        st.rerun()
    else:
        st.info("Noch keine offenen Derivate-Positionen im Logbuch. Übernimm einen Trade direkt aus dem Reiter **'⚡ Derivate & Scalable-Assistent'** oder trage ihn unten manuell ein.")

    st.divider()
    active_evals = [x for x in evaluated_list if x.get("status") != "Geschlossen"] if "evaluated_list" in locals() else []
    with st.expander("🔌 Scalable CLI (`sc`) Sync, 3-Tranchen-Matrix & Order-Preview", expanded=False):
        if st.button("📥 Bestand via `sc broker holdings` syncen"):
            try:
                added_n, warns = DerivativesPortfolio.sync_holdings_from_sc(eur_usd=eur_usd_live)
                for w_msg in warns:
                    st.warning(w_msg)
                st.toast(f"SC-Sync: +{added_n} Position(en)", icon="🔄")
                st.rerun()
            except Exception as exc:
                st.error(f"SC-Sync fehlgeschlagen: {exc}")

        if active_evals:
            sel_ev_id = st.selectbox(
                "Position für 3-Tranchen-Matrix & `sc` Preview wählen:",
                options=[x["id"] for x in active_evals],
                format_func=lambda pid: next((f"{x['ticker']} | {x['wkn']} ({x['shares']} Stk.)" for x in active_evals if x["id"] == pid), pid),
                key="sc_tranche_pos_select"
            )
            ev_sel = next(x for x in active_evals if x["id"] == sel_ev_id)
            spec_obj = DerivativesPortfolio.fetch_derivate_spec_by_isin(ev_sel["wkn"], eur_usd=eur_usd_live)
            if not spec_obj:
                fx_val = round(1.0 / eur_usd_live, 6) if (ev_sel["currency"] == "$" and eur_usd_live > 0) else 1.0
                spec_obj = DerivateSpec(ev_sel["wkn"], ev_sel["ticker"], "LONG" if ev_sel["direction"] == "Long" else "SHORT",
                                        float(ev_sel["adjusted_ko"]), float(ev_sel["adjusted_ko"]), float(ev_sel["ratio"]), fx_val)

            tranches = DerivativesPortfolio.build_three_scenario_tranches(int(ev_sel["shares"]), spec_obj, float(ev_sel["current_underlying"]))
            if tranches:
                st.dataframe(pd.DataFrame([asdict(t) for t in tranches]), use_container_width=True, hide_index=True)
                if st.button("🔍 Order-Preview über `sc` erzeugen (ohne --confirm)", key="btn_sc_preview"):
                    try:
                        st.session_state["sc_previews"] = DerivativesPortfolio.preview_tranche_orders(ev_sel["wkn"], int(ev_sel["shares"]), tranches)
                    except Exception as exc:
                        st.error(f"Preview-Fehler: {exc}")

            if st.session_state.get("sc_previews"):
                allow_exec = st.checkbox("Stückzahl & Limit geprüft – Ausführung (--confirm) freigeben", value=False, key="sc_allow_exec")
                for idx, pv in enumerate(st.session_state["sc_previews"]):
                    st.code(f"{pv['scenario']} | {pv['isin']} | {pv['quantity']} Stk. @ {pv['limit_price']:.2f} € | ID: {pv['confirm_id'] or 'n/a'}")
                    if st.button(f"🚀 Bestätigen #{idx+1}", key=f"btn_sc_conf_{idx}", disabled=not allow_exec):
                        st.success(DerivativesPortfolio.confirm_preview_order(pv, auto_confirm=allow_exec))

    st.divider()
    col_chk, col_man = st.columns([1, 1])
    with col_chk:
        st.markdown("#### ✅ Pre-Trade & Wochenend-Review Checkliste")
        st.checkbox("1. Liegt die KO-Barriere deutlich hinter dem charttechnischen Stop-Loss im Basiswert?", value=False, key="chk_1")
        st.checkbox("2. Beträgt das Euro-Risiko bis zum Stop-Loss maximal 1 % bis 2 % meines Trading-Kapitals?", value=False, key="chk_2")
        st.checkbox("3. Stehen in den nächsten 5 Tagen KEINE Quartalszahlen (Earnings) oder Zinsentscheide an?", value=False, key="chk_3")
        st.checkbox("4. Sind die Preisalarme im Basiswert-Chart (SL, Ziel 1, Ziel 2) und der Stop-Loss bei Scalable platziert?", value=False, key="chk_4")
        st.checkbox("5. Wochenend-Review: Haben alle offenen Positionen noch >5 % KO-Abstand und einen gesunden Real-Hebel?", value=False, key="chk_5")

    with col_man:
        with st.expander("➕ Bestehendes Derivat manuell ins Logbuch eintragen"):
            m_c1, m_c2, m_c3 = st.columns(3)
            with m_c1:
                m_ticker = st.text_input("Basiswert-Ticker (z. B. NVDA, MSFT, SAP.DE):", value="NVDA").strip().upper()
                m_wkn = st.text_input("WKN / ISIN:", value="PC8XYZ").strip().upper()
                m_dir = st.selectbox("Richtung:", ["Long", "Short"])
                m_shares = st.number_input("Stückzahl:", min_value=1, value=100, step=10)
            with m_c2:
                m_cur = "€" if m_ticker.endswith(".DE") else "$"
                m_entry_u = st.number_input(f"Kurs Basiswert bei Kauf ({m_cur}):", min_value=0.1, value=150.0, step=1.0)
                m_sl_type = st.radio("Stop-Loss eingeben als:", [f"Chart-SL Basiswert ({m_cur})", "Scalable Stop-Preis (€)"], horizontal=True, key="man_sl_type")
                if m_sl_type.startswith("Chart"):
                    m_sl_u = st.number_input(f"Chart-Stop-Loss Basiswert ({m_cur}):", min_value=0.1, value=144.0, step=0.5)
                else:
                    m_sl_cert_in = st.number_input("Scalable Stop-Preis Zertifikat (€):", min_value=0.01, value=1.50, step=0.05)
                    m_sl_u = None
                m_tp1_u = st.number_input(f"Kursziel 1 (50% Exit, {m_cur}):", min_value=0.1, value=158.0, step=0.5)
                m_tp2_u = st.number_input(f"Kursziel 2 (Hauptziel, {m_cur}):", min_value=0.1, value=166.0, step=0.5)
            with m_c3:
                m_ko = st.number_input(f"KO-Barriere bei Kauf ({m_cur}):", min_value=0.1, value=130.0, step=0.5)
                m_entry_cert = st.number_input("Kaufkurs Zertifikat (€):", min_value=0.01, value=2.05, step=0.05)
                m_ratio = st.selectbox("Bezugsverhältnis:", [0.10, 0.01, 1.00], index=0)
                m_bdate = st.date_input("Kaufdatum:", value=date.today())

            if st.button("➕ Manuelle Position speichern", use_container_width=True):
                fx_m = eur_usd_live if m_cur == "$" else 1.0
                init_lev_m = round(((m_entry_u / fx_m) * m_ratio) / m_entry_cert, 2) if m_entry_cert > 0 else 5.0
                intr_m = (abs(m_entry_u - m_ko) * m_ratio) / fx_m
                prem_m = round(m_entry_cert - intr_m, 2)
                if m_sl_u is None:
                    diff_eur_m = max(0.0, m_entry_cert - m_sl_cert_in)
                    diff_u_m = (diff_eur_m * fx_m) / m_ratio
                    m_sl_u = round((m_entry_u - diff_u_m) if m_dir == "Long" else (m_entry_u + diff_u_m), 2)
                DerivativesPortfolio.add_position({
                    "ticker": m_ticker,
                    "name": m_ticker,
                    "wkn": m_wkn,
                    "issuer": "Manuell",
                    "direction": m_dir,
                    "buy_date": m_bdate.isoformat(),
                    "shares": int(m_shares),
                    "entry_cert_eur": float(m_entry_cert),
                    "entry_underlying": float(m_entry_u),
                    "sl_underlying": float(m_sl_u),
                    "tp1_underlying": float(m_tp1_u),
                    "tp2_underlying": float(m_tp2_u),
                    "ko_barrier": float(m_ko),
                    "ratio": float(m_ratio),
                    "initial_leverage": float(init_lev_m),
                    "premium_eur": float(prem_m),
                    "currency": m_cur,
                    "max_hold_days": 10,
                    "fin_rate_pa": 7.5,
                    "status": "Aktiv"
                })
                st.success("Position erfolgreich ins Logbuch aufgenommen!")
                st.rerun()

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
