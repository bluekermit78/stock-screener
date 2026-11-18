import os
import json
import uuid
from datetime import datetime, date
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "data", "derivatives_portfolio.json")

class DerivativesPortfolio:
    @staticmethod
    def load_data() -> dict:
        if os.path.exists(PORTFOLIO_PATH):
            try:
                with open(PORTFOLIO_PATH, "r") as f:
                    data = json.load(f)
                    if "capital" not in data:
                        data["capital"] = 10000.0
                    if "positions" not in data:
                        data["positions"] = []
                    return data
            except Exception:
                pass
        return {"capital": 10000.0, "positions": []}

    @staticmethod
    def save_data(data: dict):
        os.makedirs(os.path.dirname(PORTFOLIO_PATH), exist_ok=True)
        with open(PORTFOLIO_PATH, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def add_position(cls, pos: dict):
        data = cls.load_data()
        pos["id"] = str(uuid.uuid4())[:8]
        pos["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        data["positions"].append(pos)
        cls.save_data(data)

    @classmethod
    def save_edited_positions(cls, edited_rows: list, eur_usd: float = 1.08):
        data = cls.load_data()
        pos_map = {p.get("id"): p for p in data.get("positions", [])}
        deleted_ids = set()

        for row in edited_rows:
            pid = row.get("id")
            if not pid or pid not in pos_map:
                continue
            if row.get("delete", False):
                deleted_ids.add(pid)
                continue

            p = pos_map[pid]
            old_sl_u = float(p.get("sl_underlying", 90.0))
            old_cert_sl = float(row.get("_orig_cert_sl_eur", 0.0))

            p["wkn"] = str(row.get("wkn", p.get("wkn", "-"))).strip()
            p["direction"] = str(row.get("direction", p.get("direction", "Long")))
            p["status"] = str(row.get("status", p.get("status", "Aktiv")))
            p["shares"] = int(row.get("shares", p.get("shares", 1)))
            p["entry_cert_eur"] = float(row.get("entry_cert_eur", p.get("entry_cert_eur", 1.0)))
            p["entry_underlying"] = float(row.get("entry_underlying", p.get("entry_underlying", 100.0)))
            p["tp1_underlying"] = float(row.get("tp1_underlying", p.get("tp1_underlying", 110.0)))
            p["tp2_underlying"] = float(row.get("tp2_underlying", p.get("tp2_underlying", 120.0)))
            p["ko_barrier"] = float(row.get("initial_ko", p.get("ko_barrier", 80.0)))
            p["ratio"] = float(row.get("ratio", p.get("ratio", 0.1)))
            p["max_hold_days"] = int(row.get("max_hold_days", p.get("max_hold_days", 10)))

            cur = p.get("currency", "$")
            fx = eur_usd if cur == "$" else 1.0
            is_long = p["direction"].lower().startswith("long")

            if p["entry_cert_eur"] > 0:
                p["initial_leverage"] = round(((p["entry_underlying"] / fx) * p["ratio"]) / p["entry_cert_eur"], 2)

            # Prüfen, ob der Nutzer den aktuellen Live-Scheinpreis (€) zur Kalibrierung angepasst hat
            old_live_cert = float(row.get("_orig_current_cert_eur", 0.0))
            new_live_cert = float(row.get("current_cert_eur", old_live_cert))
            curr_u = float(row.get("current_underlying", p["entry_underlying"]))
            if abs(new_live_cert - old_live_cert) >= 0.005:
                try:
                    buy_dt = datetime.strptime(p.get("buy_date", date.today().isoformat()), "%Y-%m-%d").date()
                    d_held = max(0, (date.today() - buy_dt).days)
                except Exception:
                    d_held = 0
                fin_r = float(p.get("fin_rate_pa", 7.5)) / 100.0
                d_shift = (p["ko_barrier"] * fin_r) / 365.0
                a_ko = (p["ko_barrier"] + d_shift * d_held) if is_long else (p["ko_barrier"] - d_shift * d_held)
                live_intr = ((curr_u - a_ko) * p["ratio"] / fx) if is_long else ((a_ko - curr_u) * p["ratio"] / fx)
                p["premium_eur"] = round(new_live_cert - max(0.0, live_intr), 3)
            elif "premium_eur" not in p:
                intr = (abs(p["entry_underlying"] - p["ko_barrier"]) * p["ratio"]) / fx
                p["premium_eur"] = round(p["entry_cert_eur"] - intr, 3)

            new_sl_u = float(row.get("sl_underlying", old_sl_u))
            new_cert_sl = float(row.get("cert_sl_eur", old_cert_sl))

            # Prüfen, ob der Nutzer den Stop-Preis des Zertifikats (€) in der Tabelle geändert hat
            if abs(new_cert_sl - old_cert_sl) >= 0.005 and abs(new_sl_u - old_sl_u) < 0.005:
                try:
                    buy_dt = datetime.strptime(p.get("buy_date", date.today().isoformat()), "%Y-%m-%d").date()
                    days_held = max(0, (date.today() - buy_dt).days)
                except Exception:
                    days_held = 0
                fin_rate_pa = float(p.get("fin_rate_pa", 7.5)) / 100.0
                daily_shift = (p["ko_barrier"] * fin_rate_pa) / 365.0
                adj_ko = (p["ko_barrier"] + daily_shift * days_held) if is_long else (p["ko_barrier"] - daily_shift * days_held)
                prem = max(0.0, float(p.get("premium_eur", 0.03)))
                sl_dist_u = (max(0.0, new_cert_sl - prem) * fx) / p["ratio"]
                p["sl_underlying"] = round(adj_ko + sl_dist_u if is_long else adj_ko - sl_dist_u, 2)
            else:
                p["sl_underlying"] = round(new_sl_u, 2)

        data["positions"] = [pos_map.get(p.get("id"), p) for p in data.get("positions", []) if p.get("id") not in deleted_ids]
        cls.save_data(data)

    @classmethod
    def update_position_status(cls, pos_id: str, action: str, new_sl_underlying: float = None):
        data = cls.load_data()
        for p in data["positions"]:
            if p.get("id") == pos_id:
                if action == "partial_50":
                    p["shares"] = max(1, int(p["shares"] // 2))
                    p["status"] = "Teilverkauf (Free-Ride)"
                    p["sl_underlying"] = p["entry_underlying"]
                elif action == "move_sl_be":
                    p["sl_underlying"] = p["entry_underlying"]
                elif action == "update_sl" and new_sl_underlying is not None:
                    p["sl_underlying"] = float(new_sl_underlying)
                elif action == "close":
                    p["status"] = "Geschlossen"
                elif action == "delete":
                    data["positions"] = [x for x in data["positions"] if x.get("id") != pos_id]
                    break
        cls.save_data(data)

    @staticmethod
    def get_next_earnings_days(ticker: str) -> int | None:
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                edates = cal['Earnings Date']
                if edates:
                    next_d = edates[0]
                    if hasattr(next_d, 'date'):
                        next_d = next_d.date()
                    delta = (next_d - date.today()).days
                    if delta >= -1:
                        return delta
        except Exception:
            pass
        return None

    @classmethod
    def evaluate_position(cls, pos: dict, current_underlying: float, eur_usd: float, total_capital: float, earnings_days: int = None) -> dict:
        is_long = pos.get("direction", "Long").lower().startswith("long")
        cur = pos.get("currency", "$")
        fx = eur_usd if cur == "$" else 1.0
        ratio = float(pos.get("ratio", 0.1))
        shares = int(pos.get("shares", 1))
        entry_cert_eur = float(pos.get("entry_cert_eur", 1.0))
        entry_underlying = float(pos.get("entry_underlying", current_underlying))
        initial_ko = float(pos.get("ko_barrier", current_underlying * 0.85))
        premium_eur = float(pos.get("premium_eur", 0.03))
        sl_underlying = float(pos.get("sl_underlying", current_underlying * 0.95))
        tp1_underlying = float(pos.get("tp1_underlying", current_underlying * 1.05))
        tp2_underlying = float(pos.get("tp2_underlying", current_underlying * 1.10))
        max_hold_days = int(pos.get("max_hold_days", 10))
        fin_rate_pa = float(pos.get("fin_rate_pa", 7.5)) / 100.0

        try:
            buy_dt = datetime.strptime(pos.get("buy_date", date.today().isoformat()), "%Y-%m-%d").date()
            days_held = max(0, (date.today() - buy_dt).days)
        except Exception:
            days_held = 0

        daily_ko_shift = (initial_ko * fin_rate_pa) / 365.0
        adjusted_ko = round(initial_ko + (daily_ko_shift * days_held), 2) if is_long else round(initial_ko - (daily_ko_shift * days_held), 2)

        ko_dist_abs = (current_underlying - adjusted_ko) if is_long else (adjusted_ko - current_underlying)
        ko_dist_pct = round((ko_dist_abs / current_underlying) * 100, 2) if current_underlying > 0 else 0.0

        if ko_dist_abs <= 0:
            current_cert_eur = 0.001
            real_leverage = 0.0
        else:
            intrinsic_eur = (ko_dist_abs * ratio) / fx
            current_cert_eur = round(max(0.01, intrinsic_eur + premium_eur), 2)
            underlying_eur = current_underlying / fx
            real_leverage = round((underlying_eur * ratio) / current_cert_eur, 2) if current_cert_eur > 0 else 0.0

        sl_dist = (sl_underlying - adjusted_ko) if is_long else (adjusted_ko - sl_underlying)
        cert_sl_eur = round(max(0.01, ((sl_dist * ratio) / fx) + max(0.0, premium_eur)), 2) if sl_dist > 0 else 0.01

        tp1_dist = (tp1_underlying - adjusted_ko) if is_long else (adjusted_ko - tp1_underlying)
        cert_tp1_eur = round(max(0.01, ((tp1_dist * ratio) / fx) + max(0.0, premium_eur)), 2)

        tp2_dist = (tp2_underlying - adjusted_ko) if is_long else (adjusted_ko - tp2_underlying)
        cert_tp2_eur = round(max(0.01, ((tp2_dist * ratio) / fx) + max(0.0, premium_eur)), 2)

        invested_eur = round(shares * entry_cert_eur, 2)
        current_val_eur = round(shares * current_cert_eur, 2)
        pnl_eur = round(current_val_eur - invested_eur, 2)
        pnl_pct = round(((current_cert_eur / entry_cert_eur) - 1.0) * 100, 1) if entry_cert_eur > 0 else 0.0

        initial_risk_eur = round(shares * max(0.0, entry_cert_eur - cert_sl_eur), 2)
        depot_risk_pct = round((initial_risk_eur / total_capital) * 100, 2) if total_capital > 0 else 0.0

        risk_per_share = max(0.01, entry_cert_eur - cert_sl_eur)
        reward_per_share = max(0.0, cert_tp2_eur - entry_cert_eur)
        crv = round(reward_per_share / risk_per_share, 2)

        init_lev = float(pos.get("initial_leverage", real_leverage))
        status = pos.get("status", "Aktiv")

        matrix_scenario = "🟢 Planmäßig (Halten)"
        matrix_action = "Stop-Loss bei Scalable aktiv lassen & Basiswert-Alarme überwachen."
        urgency = "normal"

        sl_broken = (is_long and current_underlying <= sl_underlying) or (not is_long and current_underlying >= sl_underlying)
        if ko_dist_pct <= 0:
            matrix_scenario = "💀 KNOCK-OUT EREIGNIS"
            matrix_action = "Barriere berührt! Zertifikat ist ausgestoppt."
            urgency = "critical"
        elif sl_broken:
            matrix_scenario = "🚨 SZENARIO B: HARD EXIT (Stop-Loss gerissen!)"
            matrix_action = f"Basiswert ({current_underlying:.2f} {cur}) hat deinen Stop-Loss ({sl_underlying:.2f} {cur} / Schein {cert_sl_eur:.2f} €) unterschritten! Sofort verkaufen!"
            urgency = "critical"
        elif ko_dist_pct < 3.5:
            matrix_scenario = "🚨 SZENARIO B: AKUTE KO-GEFAHR (<3.5%)"
            matrix_action = f"Nur noch {ko_dist_pct}% bis zur Barriere ({adjusted_ko:.2f} {cur})! Exponentielles Totalverlustrisiko – sofort glattstellen!"
            urgency = "critical"
        elif earnings_days is not None and 0 <= earnings_days <= 5:
            matrix_scenario = f"⚠️ SZENARIO C: EARNINGS-WARNUNG (in {earnings_days} Tagen)"
            matrix_action = "Quartalszahlen stehen unmittelbar bevor! Hohes Overnight-Gap-Risiko – Position vor den Zahlen glattstellen oder halbieren."
            urgency = "warning"
        elif days_held >= max_hold_days and pnl_pct < 15.0:
            matrix_scenario = f"⏰ SZENARIO C: ZEIT-STOPP ({days_held}/{max_hold_days} Tage)"
            matrix_action = f"Trade stagniert seit {days_held} Tagen (Finanzierungskosten fressen Barriere auf). Kapital freimachen!"
            urgency = "warning"
        elif (is_long and current_underlying >= tp2_underlying) or (not is_long and current_underlying <= tp2_underlying):
            matrix_scenario = "🏆 SZENARIO A: HAUPTZIEL 2 ERREICHT"
            matrix_action = f"Basiswert hat Hauptziel 2 ({tp2_underlying:.2f} {cur}) erreicht! Kompletten Gewinn sichern oder engen Trailing-Stopp setzen."
            urgency = "success"
        elif status == "Aktiv" and (pnl_pct >= 100.0 or (is_long and current_underlying >= tp1_underlying) or (not is_long and current_underlying <= tp1_underlying)):
            matrix_scenario = "💰 SZENARIO A: 100%-REGEL / ZIEL 1 (Free-Ride!)"
            matrix_action = f"Position liegt +{pnl_pct:.1f}% im Gewinn bzw. am Ziel 1! Jetzt 50% ({shares // 2} Stück) verkaufen, um deinen gesamten Einsatz vom Tisch zu nehmen."
            urgency = "success"
        elif pnl_pct >= 35.0 and real_leverage < max(3.0, init_lev * 0.55):
            matrix_scenario = f"🔄 SZENARIO A: HEBEL-KOMPRESSION ({real_leverage:.1f}x vs. {init_lev:.1f}x)"
            matrix_action = f"Durch den Gewinn ist der Hebel von {init_lev:.1f}x auf {real_leverage:.1f}x gefallen, während {current_val_eur:.0f} € im Risiko stehen. Gewinne sichern oder in höheren Strike rollen!"
            urgency = "success"
        elif pnl_pct >= 25.0 and ((is_long and sl_underlying < entry_underlying) or (not is_long and sl_underlying > entry_underlying)):
            matrix_scenario = "📈 SZENARIO A: TRAILING-STOPP NACHZIEHEN"
            matrix_action = f"Solider Buchgewinn (+{pnl_pct:.1f}%). Ziehe den Stop-Loss auf deinen Einstiegskurs ({entry_underlying:.2f} {cur} / {entry_cert_eur:.2f} € = Break-Even) nach!"
            urgency = "info"

        return {
            "id": pos.get("id"),
            "ticker": pos.get("ticker"),
            "name": pos.get("name", pos.get("ticker")),
            "wkn": pos.get("wkn", "-"),
            "issuer": pos.get("issuer", "-"),
            "direction": "Long" if is_long else "Short",
            "status": status,
            "buy_date": pos.get("buy_date"),
            "days_held": days_held,
            "max_hold_days": max_hold_days,
            "shares": shares,
            "ratio": ratio,
            "currency": cur,
            "entry_underlying": entry_underlying,
            "current_underlying": round(current_underlying, 2),
            "sl_underlying": sl_underlying,
            "tp1_underlying": tp1_underlying,
            "tp2_underlying": tp2_underlying,
            "initial_ko": initial_ko,
            "adjusted_ko": adjusted_ko,
            "ko_dist_pct": ko_dist_pct,
            "initial_leverage": init_lev,
            "real_leverage": real_leverage,
            "entry_cert_eur": entry_cert_eur,
            "current_cert_eur": current_cert_eur,
            "cert_sl_eur": cert_sl_eur,
            "cert_tp1_eur": cert_tp1_eur,
            "cert_tp2_eur": cert_tp2_eur,
            "invested_eur": invested_eur,
            "current_val_eur": current_val_eur,
            "pnl_eur": pnl_eur,
            "pnl_pct": pnl_pct,
            "initial_risk_eur": initial_risk_eur,
            "depot_risk_pct": depot_risk_pct,
            "crv": crv,
            "earnings_days": earnings_days,
            "matrix_scenario": matrix_scenario,
            "matrix_action": matrix_action,
            "urgency": urgency
        }
