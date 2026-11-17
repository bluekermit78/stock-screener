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
        * **⚡ Kurzfristig (1–4 Wochen / Swing-Trade):** Fokus auf überverkaufte Situationen (RSI < 32), Kontakte am unteren Bollinger-Band und frische MACD-Kaufsignale. Ideal für taktische Einstiege.
        * **🌊 Mittelfristig (1–6 Monate / Positions-Trade):** Bewertet die Trendstabilität über dem 50-Tage-Durchschnitt (SMA 50), dessen Steigung sowie das 3-Monats-Momentum.
        * **🏛️ Langfristig (6+ Monate / Strategisch):** Prüft den großen Primärtrend (SMA 200) kombiniert mit Fundamentaldaten (KGV, Free-Cashflow-Rendite und Umsatzwachstum).
        * **Gesamt-Urteil:** Gewichteter Gesamtwert (35 % Kurzfrist, 35 % Mittelfrist, 30 % Langfrist). Ab **60 Punkten = Kauf**, ab **75 Punkten = Starker Kauf**.
        """)
    with col_g3:
        st.markdown("""
        **🛡️ Risikomanagement & Fundamentaldaten**
        * **ATR (Average True Range, 14 Tage):** Durchschnittliche Tagesschwankung einer Aktie in € oder $. Dient als objektives Maß für die Volatilität.
        * **Stop-Loss (2x ATR):** Empfohlene Absicherungsmarke unterhalb des aktuellen Kurses (zweifache Tagesschwankung), um Verluste bei Trendbrüchen zu begrenzen, ohne durch normales Tagesrauschen ausgestoppt zu werden.
        * **Kursziel (3.5x ATR):** Technisches Gewinnziel für ein attraktives Chance-Risiko-Verhältnis (CRV > 1,75 : 1).
        * **KGV (Kurs-Gewinn-Verhältnis / P/E):** Wie viele Jahre das Unternehmen seinen aktuellen Gewinn erzielen muss, um den Börsenwert zu verdienen (niedriger = günstiger).
        * **FCF-Yield (Free-Cashflow-Rendite):** Freier Mittelzufluss im Verhältnis zum Börsenwert. Werte über 4–5 % zeigen hohe reale Ertragskraft.
        """)

config = load_config()
current_focus_list = [t.strip().upper() for t in config.get('universe', ['AAPL', 'MSFT', 'NVDA', 'SAP.DE', 'SIE.DE'])]

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
                    help="Klicken, um Detaildaten & News auf Yahoo Finance in einem neuen Tab zu öffnen",
                    display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                ),
                "1W %": st.column_config.NumberColumn("1W %", help="Kursentwicklung der letzten 5 Handelstage in %", format="%.2f %%"),
                "1M %": st.column_config.NumberColumn("1M %", help="Kursentwicklung der letzten 21 Handelstage (ca. 1 Monat) in %", format="%.2f %%"),
                "3M %": st.column_config.NumberColumn("3M %", help="Kursentwicklung der letzten 63 Handelstage (Quartal) in %", format="%.2f %%"),
                "1Y %": st.column_config.NumberColumn("1Y %", help="Kursentwicklung der letzten 252 Handelstage (1 Jahr) in %", format="%.2f %%"),
                "Kurzfristig (1-4W)": st.column_config.TextColumn("Kurzfristig (1-4W)", help="Taktische Bewertung auf Basis von RSI, Bollinger-Bändern, EMA 20 und MACD"),
                "Mittelfristig (1-6M)": st.column_config.TextColumn("Mittelfristig (1-6M)", help="Trendfolge-Bewertung auf Basis von SMA 50 und 3-Monats-Momentum"),
                "Langfristig (6M+)": st.column_config.TextColumn("Langfristig (6M+)", help="Strategische Bewertung aus 200-Tage-Linie (SMA 200) und Fundamentaldaten (KGV, Free Cashflow)"),
                "Stop-Loss": st.column_config.TextColumn("Stop-Loss", help="Volatilitätsbasierter Stoppkurs (2x ATR unter aktuellem Kurs)"),
                "Kursziel": st.column_config.TextColumn("Kursziel", help="Technisches Gewinnziel auf Sicht der nächsten Bewegung (3.5x ATR über Kurs)")
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
        "Hier findest du alle knapp 600 Aktien aus S&P 500, DAX 40 und MDAX. "
        "**Tipp:** Setze oder entferne einfach den Haken in der ersten Spalte **'⭐ Fokus'**, um eine Aktie sofort in deine persönliche Watchlist (Tab 1) aufzunehmen oder daraus zu entfernen."
    )
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            batch_data = json.load(f)
        st.caption(f"Letztes automatisches Update: {batch_data.get('timestamp', 'Unbekannt')} | Analysierte Aktien: {len(batch_data.get('results', []))}")
        df_batch = pd.DataFrame(batch_data.get('results', []))
        if not df_batch.empty:
            min_score = st.slider(
                "Mindest-Gesamtscore filtern (ab 60 = Kaufempfehlung, ab 75 = Starker Kauf):",
                0, 100, 60
            )
            filtered_df = df_batch[df_batch['total_score'] >= min_score].sort_values(by="total_score", ascending=False).copy()
            
            # Rohen Ticker merken und Fokus-Status prüfen
            raw_tickers = filtered_df['ticker'].astype(str).str.upper()
            filtered_df.insert(0, 'in_focus', raw_tickers.isin(current_focus_list))
            filtered_df['raw_ticker'] = raw_tickers
            filtered_df['ticker'] = "https://finance.yahoo.com/quote/" + raw_tickers

            edited_df = st.data_editor(
                filtered_df,
                column_config={
                    "in_focus": st.column_config.CheckboxColumn(
                        "⭐ Fokus",
                        help="Anhaken, um diese Aktie direkt in 'Meine Fokus-Aktien' (Tab 1) zu übernehmen oder abzuwählen.",
                        default=False
                    ),
                    "raw_ticker": None,  # Interne Hilfsspalte ausblenden
                    "ticker": st.column_config.LinkColumn(
                        "Ticker (Yahoo Finance)",
                        help="Klicken, um das Wertpapier auf Yahoo Finance in einem neuen Fenster zu öffnen.",
                        display_text=r"https://finance\.yahoo\.com/quote/(.*)"
                    ),
                    "price": st.column_config.NumberColumn("Kurs", help="Letzter Schlusskurs", format="%.2f"),
                    "1W %": st.column_config.NumberColumn("1W %", help="Performance 1 Woche", format="%.2f %%"),
                    "1M %": st.column_config.NumberColumn("1M %", help="Performance 1 Monat", format="%.2f %%"),
                    "3M %": st.column_config.NumberColumn("3M %", help="Performance 3 Monate", format="%.2f %%"),
                    "1Y %": st.column_config.NumberColumn("1Y %", help="Performance 1 Jahr", format="%.2f %%"),
                    "rsi": st.column_config.NumberColumn("RSI (14)", help="Relative Strength Index (<30 überverkauft, >70 überkauft)", format="%.1f"),
                    "short_term": st.column_config.TextColumn("Kurzfristig (1-4W)", help="Einschätzung für 1 bis 4 Wochen"),
                    "mid_term": st.column_config.TextColumn("Mittelfristig (1-6M)", help="Einschätzung für 1 bis 6 Monate"),
                    "long_term": st.column_config.TextColumn("Langfristig (6M+)", help="Einschätzung für 6+ Monate"),
                    "total_score": st.column_config.NumberColumn("Gesamt-Score", help="Gewichteter Score von 0 bis 100", format="%.1f"),
                    "overall_verdict": st.column_config.TextColumn("Gesamt-Urteil", help="Zusammenfassende Handlungsempfehlung"),
                    "stop_loss": st.column_config.NumberColumn("Stop-Loss", help="Empfohlener Stop-Loss (2x ATR)", format="%.2f"),
                    "take_profit": st.column_config.NumberColumn("Kursziel", help="Technisches Kursziel (3.5x ATR)", format="%.2f")
                },
                disabled=[c for c in filtered_df.columns if c != 'in_focus'],
                use_container_width=True,
                hide_index=True,
                key="market_editor"
            )

            # Prüfen, ob der Nutzer einen Haken bei '⭐ Fokus' gesetzt oder entfernt hat
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
