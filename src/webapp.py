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

# Dezentes CSS für kompaktere Seitenränder, damit die Tabelle die volle Bildschirmbreite optimal nutzt
st.markdown("""
<style>
    .block-container {
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-top: 2rem !important;
        max-width: 100% !important;
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

st.title("🏛️ Persönlicher Aktien-Anlageberater & Screener")
st.markdown(
    "Dieses Dashboard kombiniert **technische Chartanalyse** und **fundamentale Unternehmensbewertung**, "
    "um dir über drei Zeithorizonte hinweg objektive Kauf- und Halteempfehlungen sowie konkrete Risikoleitplanken zu liefern."
)

with st.expander("📖 Lexikon & Methodik: Was bedeuten die Abkürzungen, Indikatoren und Zeithorizonte?"):
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.markdown("""
        **📈 Technische Indikatoren**
        * **RSI (Relative Strength Index, 14 Tage):** Misst die Geschwindigkeit von Kursbewegungen auf einer Skala von 0 bis 100. Werte **unter 30** gelten als *überverkauft* (Rebound-Chance), Werte **über 70** als *überkauft* (Rückschlagsgefahr).
        * **EMA 20 / SMA 50 / SMA 200:** Gleitende Durchschnittskurse der letzten 20, 50 bzw. 200 Handelstage. Notiert der Kurs darüber, ist der jeweilige Trend intakt. Kreuzt der SMA 50 den SMA 200 von unten nach oben, spricht man vom bullischen **Golden Cross**.
        * **MACD (Moving Average Convergence Divergence):** Zeigt Schwung- und Trendwechsel an. Steigt das Histogramm über die Nulllinie (MACD kreuzt Signallinie nach oben), entsteht ein Kaufsignal.
        * **Bollinger-Bänder (BB):** Statistische Schwankungsbreite (2 Standardabweichungen) um den 20-Tage-Schnitt. Ein Kontakt mit dem unteren Band deutet oft auf eine kurzfristige Gegenbewegung nach oben hin.
        """)
    with col_g2:
        st.markdown("""
        **⏱️ Die 3 Anlagehorizonte & Scores (0–100 Punkte)**
        * **⚡ Kurz (1–4 Wochen / Swing-Trade):** Fokus auf überverkaufte Situationen (RSI < 32), Kontakte am unteren Bollinger-Band und frische MACD-Kaufsignale. Ideal für taktische Einstiege.
        * **🌊 Mittel (1–6 Monate / Positions-Trade):** Bewertet die Trendstabilität über dem 50-Tage-Durchschnitt (SMA 50), dessen Steigung sowie das 3-Monats-Momentum.
        * **🏛️ Lang (6+ Monate / Strategisch):** Prüft den großen Primärtrend (SMA 200) kombiniert mit Fundamentaldaten (KGV, Free-Cashflow-Rendite und Umsatzwachstum).
        * **Score & Urteil:** Gewichteter Gesamtwert (35 % Kurzfrist, 35 % Mittelfrist, 30 % Langfrist). Ab **60 Punkten = Kauf**, ab **75 Punkten = Top-Kauf**.
        """)
    with col_g3:
        st.markdown("""
        **🛡️ Risikomanagement & Fundamentaldaten**
        * **ATR (Average True Range, 14 Tage):** Durchschnittliche Tagesschwankung einer Aktie in € oder $. Dient als objektives Maß für die Volatilität.
        * **SL (Stop-Loss, 2x ATR):** Empfohlene Absicherungsmarke unterhalb des aktuellen Kurses (zweifache Tagesschwankung), um Verluste bei Trendbrüchen zu begrenzen.
        * **TP (Take-Profit / Kursziel, 3.5x ATR):** Technisches Gewinnziel für ein attraktives Chance-Risiko-Verhältnis (CRV > 1,75 : 1).
        * **KGV (Kurs-Gewinn-Verhältnis / P/E):** Wie viele Jahre das Unternehmen seinen aktuellen Gewinn erzielen muss, um den Börsenwert zu verdienen (niedriger = günstiger).
        * **FCF-Yield (Free-Cashflow-Rendite):** Freier Mittelzufluss im Verhältnis zum Börsenwert. Werte über 4–5 % zeigen hohe reale Ertragskraft.
        """)

config = load_config()
current_focus_list = [t.strip().upper() for t in config.get('universe', ['AAPL', 'MSFT', 'NVDA', 'CARR', 'SAP.DE', 'SIE.DE'])]

tab1, tab2, tab3 = st.tabs([
    "🎯 Meine Fokus-Aktien (Multi-Horizont-Berater)",
    "🌍 Indizes & Markt-Kompass",
    "🔍 Gesamtmarkt-Screener (S&P 500 / DAX / MDAX)"
])

with tab1:
    st.subheader("Persönliche Watchlist & Detail-Chartanalyse")
    st.caption(
        "Hier werden deine ausgewählten Fokus-Aktien in Echtzeit auf drei Zeitebenen durchleuchtet. "
        "Du kannst Aktien unten manuell ergänzen oder direkt im Reiter 'Gesamtmarkt-Screener' per Klick auf den Stern (⭐) übernehmen."
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
        selected_ticker = st.selectbox("🔎 Aktie für tiefe Chart- & Horizont-Analyse auswählen:", watchlist)
        sel_data = next((item for item in watchlist_results if item['ticker'] == selected_ticker), None)

        if sel_data:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Aktueller Kurs",
                f"{sel_data['price']} {sel_data['currency']}",
                f"{sel_data['perf']['1M']}% (1M)",
                help="Letzter Börsenkurs und prozentuale Veränderung auf Sicht von einem Monat."
            )
            c2.metric(
                "Gesamt-Empfehlung",
                sel_data['overall_verdict'],
                f"Score: {sel_data['total_score']} / 100",
                help="Gewichteter Score über alle drei Zeithorizonte (ab 60 = Kauf, ab 75 = Starker Kauf)."
            )
            c3.metric(
                "Empfohlener Stop-Loss (2x ATR)",
                f"{sel_data['stop_loss']} {sel_data['currency']}",
                help=f"Absicherungsmarke auf Basis der aktuellen Tagesschwankung (ATR = {sel_data['atr']} {sel_data['currency']})."
            )
            c4.metric(
                "Technisches Kursziel (3.5x ATR)",
                f"{sel_data['take_profit']} {sel_data['currency']}",
                help="Rechnerisches Kursziel für ein positives Chance-Risiko-Verhältnis von 1,75 : 1."
            )

            h1, h2, h3 = st.columns(3)
            with h1:
                st.info(f"**⚡ Kurzfristig (1–4 Wochen): {sel_data['short_term'][' verdict']} ({sel_data['short_term']['score']}/100)**\n\n" +
                        "*Fokus: Rebound-Chancen, RSI-Extrema & kurzfristiges Momentum*\n\n" +
                        ("\n".join([f"- {x}" for x in sel_data['short_term']['reasons']]) or "- Neutrale Indikatorenlage ohne Extremwerte"))
            with h2:
                st.warning(f"**🌊 Mittelfristig (1–6 Monate): {sel_data['mid_term']['verdict']} ({sel_data['mid_term']['score']}/100)**\n\n" +
                           "*Fokus: Stabilität des 50-Tage-Trends & Quartalsdynamik*\n\n" +
                           ("\n".join([f"- {x}" for x in sel_data['mid_term']['reasons']]) or "- Seitwärtstrend ohne klaren Impuls"))
            with h3:
                st.success(f"**🏛️ Langfristig (6+ Monate): {sel_data['long_term']['verdict']} ({sel_data['long_term']['score']}/100)**\n\n" +
                           "*Fokus: Übergeordneter 200-Tage-Trend & fundamentale Ertragskraft*\n\n" +
                           ("\n".join([f"- {x}" for x in sel_data['long_term']['reasons']]) or "- Neutrale Bewertung"))

            plot_chart(fetch_single_history(selected_ticker), selected_ticker)

with tab2:
    st.subheader("Globale Leitindizes im Performance- & Trend-Check")
    st.caption(
        "Der Markt-Kompass zeigt dir die Großwetterlage an den Börsen. "
        "Käufe in Einzelaktien haben eine deutlich höhere Trefferquote, wenn auch der übergeordnete Heimatindex im Aufwärtstrend notiert."
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
            
            # Kompakte Texte für optimale Bildschirmbreite
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
