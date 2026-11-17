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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DATA_PATH = os.path.join(BASE_DIR, "data", "latest_analysis.json")

st.set_page_config(page_title="Aktien-Anlageberater & Screener", layout="wide", page_icon="📈")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

@st.cache_data(ttl=900)
def fetch_single_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period)
    if not df.empty:
        df = TechnicalIndicators.apply_indicators(df)
    return df

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
        subplot_titles=(f"{ticker} Kursverlauf & Indikatoren (letzte 180 Handelstage)", "RSI (14)", "MACD (12, 26, 9)")
    )

    fig.add_trace(go.Candlestick(
        x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
        low=df_plot['Low'], close=df_plot['Close'], name="Kurs"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_20'], line=dict(color='#00b4d8', width=1.2), name='EMA 20'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA_50'], line=dict(color='#f77f00', width=1.8), name='SMA 50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA_200'], line=dict(color='#d62828', width=2.2), name='SMA 200'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='gray', dash='dot', width=1), name='BB Upper'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='gray', dash='dot', width=1), name='BB Lower'), row=1, col=1)

    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], line=dict(color='#9b5de5', width=1.5), name='RSI'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    fig.add_trace(go.Bar(x=df_plot.index, y=df_plot['MACD_Hist'], name='MACD Hist', marker_color='#adb5bd'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MACD'], line=dict(color='#0077b6', width=1.5), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['MACD_Signal'], line=dict(color='#fb8500', width=1.5), name='Signal'), row=3, col=1)

    fig.update_layout(height=720, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

st.title("🏛️ Persönlicher Aktien-Anlageberater & Screener")
config = load_config()

tab1, tab2, tab3 = st.tabs([
    "🎯 Meine Fokus-Aktien (Multi-Horizont-Berater)",
    "🌍 Indizes & Markt-Kompass",
    "🔍 Gesamtmarkt-Screener (S&P 500 / DAX / MDAX)"
])

with tab1:
    st.subheader("Persönliche Watchlist & Detail-Chartanalyse")
    col_cfg, col_sel = st.columns([2, 1])
    with col_cfg:
        current_watchlist = ", ".join(config.get('universe', ['AAPL', 'MSFT', 'NVDA', 'SAP.DE', 'SIE.DE']))
        new_watchlist_str = st.text_input("Fokus-Aktien bearbeiten (Komma-getrennt, Xetra mit .DE):", value=current_watchlist)
        if st.button("💾 Watchlist in config.yaml speichern"):
            updated_list = [t.strip().upper() for t in new_watchlist_str.split(",") if t.strip()]
            config['universe'] = updated_list
            save_config(config)
            st.success("Watchlist gespeichert!")

    watchlist = [t.strip().upper() for t in new_watchlist_str.split(",") if t.strip()]
    
    watchlist_results = []
    for t in watchlist:
        df_t = fetch_single_history(t)
        fund_t = fetch_fundamentals(t)
        res = InvestmentAdvisor.analyze_ticker(t, df_t, fund_t)
        if res:
            res['name'] = fund_t['name']
            res['pe'] = round(fund_t['pe'], 1) if fund_t['pe'] else None
            res['fcf_yield'] = round(fund_t['fcf_yield'], 1) if fund_t['fcf_yield'] else None
            watchlist_results.append(res)

    if watchlist_results:
        summary_rows = []
        for r in watchlist_results:
            summary_rows.append({
                "Ticker": f"https://finance.yahoo.com/quote/{r['ticker']}",
                "Name": r['name'],
                "Kurs": f"{r['price']} {r['currency']}",
                "1W %": r['perf']['1W'],
                "1M %": r['perf']['1M'],
                "3M %": r['perf']['3M'],
                "1Y %": r['perf']['1Y'],
                "Kurzfristig (1-4W)": f"{r['short_term'][' verdict']} ({r['short_term']['score']})",
                "Mittelfristig (1-6M)": f"{r['mid_term']['verdict']} ({r['mid_term']['score']})",
                "Langfristig (6M+)": f"{r['long_term']['verdict']} ({r['long_term']['score']})",
                "Gesamt-Urteil": f"{r['overall_verdict']} ({r['total_score']})",
                "Stop-Loss": f"{r['stop_loss']} {r['currency']}",
                "Kursziel": f"{r['take_profit']} {r['currency']}"
            })
        st.dataframe(
            pd.DataFrame(summary_rows),
            column_config={
                "Ticker": st.column_config.LinkColumn(
                    "Ticker",
                    help="Öffnet die Aktie auf Yahoo Finance in einem neuen Tab",
                    display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                )
            },
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        selected_ticker = st.selectbox("🔎 Aktie für tiefe Chart- & Horizont-Analyse auswählen:", watchlist)
        sel_data = next((item for item in watchlist_results if item['ticker'] == selected_ticker), None)

        if sel_data:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Aktueller Kurs", f"{sel_data['price']} {sel_data['currency']}", f"{sel_data['perf']['1M']}% (1M)")
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
                           ("\n".join([f"- {x}" for x in sel_data['long_term']['reasons']]) or "- Fundamentaldaten neutral"))

            plot_chart(fetch_single_history(selected_ticker), selected_ticker)

with tab2:
    st.subheader("Globale Leitindizes im Performance- & Trend-Check")
    indices = {
        "^GSPC": "S&P 500 (USA)",
        "^NDX": "Nasdaq 100 (USA Tech)",
        "^GDAXI": "DAX 40 (Deutschland)",
        "^MDAXI": "MDAX (Deutschland Mid-Caps)",
        "URTH": "MSCI World ETF"
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
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            batch_data = json.load(f)
        st.caption(f"Letztes Update: {batch_data.get('timestamp', 'Unbekannt')} | Analysierte Aktien: {len(batch_data.get('results', []))}")
        df_batch = pd.DataFrame(batch_data.get('results', []))
        if not df_batch.empty:
            min_score = st.slider("Mindest-Gesamtscore filtern:", 0, 100, 60)
            filtered_df = df_batch[df_batch['total_score'] >= min_score].sort_values(by="total_score", ascending=False).copy()
            
            # Ticker in klickbare Yahoo-Finance-URL umwandeln
            filtered_df['ticker'] = "https://finance.yahoo.com/quote/" + filtered_df['ticker'].astype(str)

            st.dataframe(
                filtered_df,
                column_config={
                    "ticker": st.column_config.LinkColumn(
                        "Ticker",
                        help="Öffnet detaillierte Finanzdaten & News auf Yahoo Finance in einem neuen Tab",
                        display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                    )
                },
                use_container_width=True,
                hide_index=True
            )
    else:
        st.info("Noch keine Batch-Daten vorhanden. Führe einmal `python3 src/main.py` aus, um den Gesamtmarkt-Cache zu füllen.")
