import os
import re
import json
import uuid
import subprocess
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "data", "derivatives_portfolio.json")
STAMMDATEN_CACHE_PATH = os.path.join(BASE_DIR, "data", "derivate_stammdaten_cache.json")


@dataclass
class DerivateSpec:
    isin: str
    underlying_symbol: str
    direction: str
    strike: float
    knock_out: Optional[float]
    ratio: float
    fx_eur_per_quote: float = 1.0


@dataclass
class ExitTranche:
    scenario: str
    target_underlying_price: float
    estimated_cert_price: float
    limit_price: float
    sell_quantity: int
    expected_proceeds_eur: float


class DerivativesPortfolio:
    @staticmethod
    def load_data() -> dict:
        if os.path.exists(PORTFOLIO_PATH):
            try:
                with open(PORTFOLIO_PATH, "r") as f:
                    data = json.load(f)
                    data.setdefault("capital", 10000.0)
                    data.setdefault("positions", [])
                    return data
            except Exception:
                pass
        return {"capital": 10000.0, "positions": []}

    @staticmethod
    def save_data(data: dict):
        os.makedirs(os.path.dirname(PORTFOLIO_PATH), exist_ok=True)
        with open(PORTFOLIO_PATH, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_spec_cache() -> dict[str, dict]:
        if os.path.exists(STAMMDATEN_CACHE_PATH):
            with open(STAMMDATEN_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @staticmethod
    def save_spec_cache(cache: dict[str, dict]) -> None:
        os.makedirs(os.path.dirname(STAMMDATEN_CACHE_PATH), exist_ok=True)
        with open(STAMMDATEN_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    @classmethod
    def fetch_derivate_spec_by_isin(cls, isin: str, eur_usd: float = 1.08) -> Optional[DerivateSpec]:
        isin_clean = str(isin).strip().upper()
        if not isin_clean:
            return None
        cache = cls.load_spec_cache()
        if isin_clean in cache:
            cached = dict(cache[isin_clean])
            is_de = cached.get("underlying_symbol", "").endswith(".DE")
            cached["fx_eur_per_quote"] = round(1.0 / eur_usd, 6) if (not is_de and eur_usd > 0) else 1.0
            return DerivateSpec(**cached)

        url = f"https://api.onvista.de/api/v1/derivatives/{isin_clean}/snapshot"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            strike = float(data.get("strikePrice") or data.get("exercisePrice") or 0.0)
            ko_raw = data.get("knockOut") or data.get("barrier")
            knock_out = float(ko_raw) if ko_raw is not None else None
            ratio = float(data.get("subscriptionRatio") or data.get("ratio") or 0.1)
            raw_dir = str(data.get("direction") or data.get("type") or "LONG").upper()
            direction = "SHORT" if ("SHORT" in raw_dir or "PUT" in raw_dir) else "LONG"
            underlying = str((data.get("underlying") or {}).get("symbol") or "UNKNOWN").upper()
            fx = round(1.0 / eur_usd, 6) if (not underlying.endswith(".DE") and eur_usd > 0) else 1.0
            if strike > 0:
                spec = DerivateSpec(isin_clean, underlying, direction, strike, knock_out, ratio, fx)
                cache[isin_clean] = asdict(spec)
                cls.save_spec_cache(cache)
                return spec
        except Exception:
            pass
        return None

    @classmethod
    def run_sc_json(cls, args: list[str]):
        if args[:2] == ["broker", "holdings"]:
            remote_args = ["holdings"]
        elif args[:3] == ["broker", "trade", "sell"]:
            remote_args = ["preview-sell"] + [a for a in args[3:] if a != "--json"]
        else:
            raise ValueError(f"Nicht freigegebener Remote-Befehl: {args}")
        cmd = ["ssh", "-i", "/root/.ssh/id_ed25519_sc", "-o", "BatchMode=yes", "scbot@192.168.78.130", "/opt/sc-wrapper/run_sc.sh"] + remote_args
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)

    @staticmethod
    def _parse_sc_derivative_name(name: str, isin: str) -> dict:
        text = str(name or "").strip()
        upper = text.upper()
        direction = "SHORT" if " SHORT " in f" {upper} " else "LONG"

        ko_match = re.search(r"(?:LONG|SHORT)\s+([0-9]+(?:[.,][0-9]+)?)", text, flags=re.IGNORECASE)
        ko_val = float(ko_match.group(1).replace(",", ".")) if ko_match else None

        is_usd = ("$" in text) or ("USD" in upper)
        underlying_map = {
            "SKYWORKS SOLUTIONS": ("SWKS", "$"),
            "NVIDIA": ("NVDA", "$"),
            "WEST PHARMACEUTIC": ("WST", "$"),
            "WEST PHARMACEUTICAL": ("WST", "$"),
        }
        ticker = isin
        cur = "$" if is_usd else "€"
        for key, (sym, c) in underlying_map.items():
            if key in upper:
                ticker = sym
                cur = c
                break

        known_issuers = ("HSBC", "BNP", "MS", "MORGAN STANLEY", "VONTOBEL", "CITI", "SOCIETE GENERALE", "SG", "DZ BANK", "UBS")
        issuer = "Scalable Sync"
        parts = text.split()
        if parts and parts[-1].upper() in {i.upper() for i in known_issuers}:
            issuer = parts[-1]

        return {
            "ticker": ticker,
            "direction": direction,
            "ko_barrier": ko_val,
            "currency": cur,
            "issuer": issuer,
        }

    @classmethod
    def sync_holdings_from_sc(cls, eur_usd: float = 1.08) -> tuple[int, list[str]]:
        holdings_data = cls.run_sc_json(["broker", "holdings"])
        warnings: list[str] = []

        res_obj = ((holdings_data.get("data") or {}).get("result")) if isinstance(holdings_data, dict) else {}
        raw_positions = res_obj.get("items", []) if isinstance(res_obj, dict) else []

        port = cls.load_data()
        existing = {
            str(p.get("wkn", "")).strip().upper()
            for p in port.get("positions", [])
            if p.get("status") != "Geschlossen"
        }

        added_count = 0
        for item in raw_positions:
            if not isinstance(item, dict):
                continue
            isin = str(item.get("isin") or item.get("wkn") or "").strip().upper()
            try:
                qty = int(float(item.get("quantity") or 0))
            except Exception:
                qty = 0

            if not isin or qty <= 0 or isin in existing:
                continue

            entry_cert = float(
                item.get("fifo_price")
                if item.get("fifo_price") is not None
                else item.get("quote_mid_price")
                or 1.0
            )
            name_str = str(item.get("name") or isin).strip()
            parsed = cls._parse_sc_derivative_name(name_str, isin)
            spec = cls.fetch_derivate_spec_by_isin(isin, eur_usd=eur_usd)

            is_long = (spec.direction == "LONG") if spec else (parsed["direction"] == "LONG")
            ticker = spec.underlying_symbol if (spec and spec.underlying_symbol != "UNKNOWN") else parsed["ticker"]
            cur = "€" if ticker.endswith(".DE") else parsed["currency"]
            fx = eur_usd if cur == "$" else 1.0
            ratio = spec.ratio if spec else 0.01

            ko_val = (
                spec.knock_out
                if (spec and spec.knock_out is not None)
                else (parsed["ko_barrier"] if parsed["ko_barrier"] is not None else round(entry_cert * 10.0, 2))
            )
            init_u = round(ko_val * (1.08 if is_long else 0.92), 2) if ko_val else round(entry_cert * 10.0, 2)

            port["positions"].append({
                "id": str(uuid.uuid4())[:8],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "ticker": ticker,
                "name": name_str,
                "wkn": isin,
                "issuer": parsed["issuer"],
                "direction": "Long" if is_long else "Short",
                "buy_date": date.today().isoformat(),
                "shares": qty,
                "entry_cert_eur": round(entry_cert, 2),
                "entry_underlying": init_u,
                "sl_underlying": round(init_u * (0.96 if is_long else 1.04), 2),
                "tp1_underlying": round(init_u * (1.05 if is_long else 0.95), 2),
                "tp2_underlying": round(init_u * (1.12 if is_long else 0.88), 2),
                "ko_barrier": ko_val,
                "ratio": ratio,
                "initial_leverage": round(((init_u / fx) * ratio) / max(0.01, entry_cert), 2),
                "premium_eur": 0.03,
                "currency": cur,
                "max_hold_days": 10,
                "fin_rate_pa": 7.5,
                "status": "Aktiv",
            })
            existing.add(isin)
            added_count += 1

        if added_count > 0:
            cls.save_data(port)
        return added_count, warnings

    @staticmethod
    def calc_intrinsic_cert_price(spec: DerivateSpec, underlying_price: float) -> float:
        if spec.knock_out is not None:
            if spec.direction == "LONG" and underlying_price <= spec.knock_out:
                return 0.0
            if spec.direction == "SHORT" and underlying_price >= spec.knock_out:
                return 0.0
        diff = max(0.0, underlying_price - spec.strike) if spec.direction == "LONG" else max(0.0, spec.strike - underlying_price)
        return round(diff * spec.ratio * spec.fx_eur_per_quote, 2)

    @classmethod
    def build_three_scenario_tranches(
        cls, total_qty: int, spec: DerivateSpec, current_underlying: float,
        scenario_moves_pct: tuple[float, float, float] = (-0.03, 0.05, 0.12),
        tranche_shares: tuple[float, float, float] = (0.30, 0.40, 0.30),
    ) -> list[ExitTranche]:
        if total_qty <= 0:
            return []
        sign = 1.0 if spec.direction == "LONG" else -1.0
        labels = ["Szenario 1: Schutz / Stopp-Zone", "Szenario 2: Teilgewinnmitnahme", "Szenario 3: Zielkurs"]
        q1, q2 = int(total_qty * tranche_shares[0]), int(total_qty * tranche_shares[1])
        q3 = max(0, total_qty - q1 - q2)
        tranches = []
        for label, move, qty in zip(labels, scenario_moves_pct, [q1, q2, q3]):
            if qty <= 0:
                continue
            target_u = round(current_underlying * (1.0 + sign * move), 4)
            theo_price = cls.calc_intrinsic_cert_price(spec, target_u)
            limit_price = max(0.01, round(theo_price * 0.99, 2))
            tranches.append(ExitTranche(label, target_u, theo_price, limit_price, qty, round(limit_price * qty, 2)))
        return tranches

    @classmethod
    def preview_tranche_orders(cls, isin: str, available_qty: int, tranches: list[ExitTranche]) -> list[dict]:
        if sum(t.sell_quantity for t in tranches) > available_qty:
            raise ValueError("Overselling verhindert: Geplante Verkaufsmenge übersteigt den Bestand.")
        previews = []
        for tranche in tranches:
            if tranche.sell_quantity <= 0:
                continue
            cmd = ["sc", "broker", "trade", "sell", "--isin", isin, "--quantity", str(tranche.sell_quantity),
                   "--order-type", "limit", "--limit-price", f"{tranche.limit_price:.2f}", "--json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(proc.stdout)
            cid = data.get("confirmationId") or data.get("confirmId") or data.get("previewId") or ""
            previews.append({"scenario": tranche.scenario, "isin": isin, "quantity": tranche.sell_quantity,
                             "limit_price": tranche.limit_price, "confirm_id": str(cid), "cmd": cmd, "raw": data})
        return previews

    @staticmethod
    def confirm_preview_order(preview_item: dict, auto_confirm: bool = False) -> str:
        if not auto_confirm:
            return "Freigabe gesperrt (auto_confirm=False)."
        cid = preview_item.get("confirm_id", "").strip()
        if not cid:
            return "Keine gültige Preview-ID vorhanden."
        proc = subprocess.run(preview_item["cmd"] + ["--confirm", cid], capture_output=True, text=True, check=True)
        return proc.stdout.strip() or "Order bestätigt."

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
            p["wkn"] = str(row.get("wkn", p.get("wkn", "-"))).strip()
            p["direction"] = str(row.get("direction", p.get("direction", "Long")))
            p["status"] = str(row.get("status", p.get("status", "Aktiv")))
            p["shares"] = int(row.get("shares", p.get("shares", 1)))
            p["entry_cert_eur"] = float(row.get("entry_cert_eur", p.get("entry_cert_eur", 1.0)))
            p["entry_underlying"] = float(row.get("entry_underlying", p.get("entry_underlying", 100.0)))
            p["sl_underlying"] = float(row.get("sl_underlying", p.get("sl_underlying", 90.0)))
            p["tp1_underlying"] = float(row.get("tp1_underlying", p.get("tp1_underlying", 110.0)))
            p["tp2_underlying"] = float(row.get("tp2_underlying", p.get("tp2_underlying", 120.0)))
            p["ko_barrier"] = float(row.get("initial_ko", p.get("ko_barrier", 80.0)))
            p["ratio"] = float(row.get("ratio", p.get("ratio", 0.1)))
            p["max_hold_days"] = int(row.get("max_hold_days", p.get("max_hold_days", 10)))
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
                elif action == "delete":
                    data["positions"] = [x for x in data["positions"] if x.get("id") != pos_id]
                    break
        cls.save_data(data)

    @staticmethod
    def get_next_earnings_days(ticker: str) -> int | None:
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict) and 'Earnings Date' in cal and cal['Earnings Date']:
                next_d = cal['Earnings Date'][0]
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
        ratio, shares = float(pos.get("ratio", 0.1)), int(pos.get("shares", 1))
        entry_cert_eur = float(pos.get("entry_cert_eur", 1.0))
        entry_underlying = float(pos.get("entry_underlying", current_underlying))
        initial_ko = float(pos.get("ko_barrier", current_underlying * 0.85))
        premium_eur = float(pos.get("premium_eur", 0.03))
        sl_u, tp1_u, tp2_u = float(pos.get("sl_underlying", current_underlying * 0.95)), float(pos.get("tp1_underlying", current_underlying * 1.05)), float(pos.get("tp2_underlying", current_underlying * 1.10))
        max_hold_days = int(pos.get("max_hold_days", 10))
        fin_rate_pa = float(pos.get("fin_rate_pa", 7.5)) / 100.0
        try:
            days_held = max(0, (date.today() - datetime.strptime(pos.get("buy_date", date.today().isoformat()), "%Y-%m-%d").date()).days)
        except Exception:
            days_held = 0
        shift = (initial_ko * fin_rate_pa) / 365.0
        adjusted_ko = round(initial_ko + shift * days_held if is_long else initial_ko - shift * days_held, 2)
        ko_dist_abs = (current_underlying - adjusted_ko) if is_long else (adjusted_ko - current_underlying)
        ko_dist_pct = round((ko_dist_abs / current_underlying) * 100, 2) if current_underlying > 0 else 0.0
        if ko_dist_abs <= 0:
            current_cert_eur, real_leverage = 0.001, 0.0
        else:
            current_cert_eur = round(max(0.01, ((ko_dist_abs * ratio) / fx) + premium_eur), 2)
            real_leverage = round(((current_underlying / fx) * ratio) / current_cert_eur, 2) if current_cert_eur > 0 else 0.0
        cert_sl_eur = round(max(0.01, ((((sl_u - adjusted_ko) if is_long else (adjusted_ko - sl_u)) * ratio) / fx) + premium_eur), 2)
        cert_tp1_eur = round(max(0.01, ((((tp1_u - adjusted_ko) if is_long else (adjusted_ko - tp1_u)) * ratio) / fx) + premium_eur), 2)
        cert_tp2_eur = round(max(0.01, ((((tp2_u - adjusted_ko) if is_long else (adjusted_ko - tp2_u)) * ratio) / fx) + premium_eur), 2)
        invested_eur = round(shares * entry_cert_eur, 2)
        current_val_eur = round(shares * current_cert_eur, 2)
        pnl_eur = round(current_val_eur - invested_eur, 2)
        pnl_pct = round(((current_cert_eur / entry_cert_eur) - 1.0) * 100, 1) if entry_cert_eur > 0 else 0.0
        initial_risk_eur = round(shares * max(0.0, entry_cert_eur - cert_sl_eur), 2)
        depot_risk_pct = round((initial_risk_eur / total_capital) * 100, 2) if total_capital > 0 else 0.0
        crv = round(max(0.0, cert_tp2_eur - entry_cert_eur) / max(0.01, entry_cert_eur - cert_sl_eur), 2)
        init_lev, status = float(pos.get("initial_leverage", real_leverage)), pos.get("status", "Aktiv")
        matrix_scenario, matrix_action, urgency = "🟢 Planmäßig (Halten)", "Stop-Loss bei Scalable aktiv lassen.", "normal"
        sl_broken = (is_long and current_underlying <= sl_u) or (not is_long and current_underlying >= sl_u)
        if ko_dist_pct <= 0:
            matrix_scenario, matrix_action, urgency = "💀 KNOCK-OUT EREIGNIS", "Barriere berührt!", "critical"
        elif sl_broken or ko_dist_pct < 3.5:
            matrix_scenario, matrix_action, urgency = "🚨 SZENARIO B: HARD EXIT / KO-NAHE", f"Stop-Loss ({sl_u:.2f} {cur}) gerissen oder KO-Abstand ({ko_dist_pct}%) kritisch!", "critical"
        elif (earnings_days is not None and 0 <= earnings_days <= 5) or (days_held >= max_hold_days and pnl_pct < 15.0):
            matrix_scenario, matrix_action, urgency = "⚠️ SZENARIO C: EVENT- / ZEIT-EXIT", "Earnings in <=5 Tagen oder Zeit-Stopp erreicht – Gap-/Zinsrisiko prüfen!", "warning"
        elif pnl_pct >= 100.0 or ((is_long and current_underlying >= tp1_u) or (not is_long and current_underlying <= tp1_u)):
            matrix_scenario, matrix_action, urgency = "💰 SZENARIO A: 100%-REGEL / ZIEL 1", "50% verkaufen (Free-Ride) & Stop-Loss auf Einstieg nachziehen!", "success"
        return {
            "id": pos.get("id"), "ticker": pos.get("ticker"), "name": pos.get("name", pos.get("ticker")),
            "wkn": pos.get("wkn", "-"), "direction": "Long" if is_long else "Short", "status": status,
            "days_held": days_held, "max_hold_days": max_hold_days, "shares": shares, "ratio": ratio, "currency": cur,
            "entry_underlying": entry_underlying, "current_underlying": round(current_underlying, 2),
            "sl_underlying": sl_u, "tp1_underlying": tp1_u, "tp2_underlying": tp2_u,
            "initial_ko": initial_ko, "adjusted_ko": adjusted_ko, "ko_dist_pct": ko_dist_pct,
            "initial_leverage": init_lev, "real_leverage": real_leverage,
            "entry_cert_eur": entry_cert_eur, "current_cert_eur": current_cert_eur,
            "cert_sl_eur": cert_sl_eur, "cert_tp1_eur": cert_tp1_eur, "cert_tp2_eur": cert_tp2_eur,
            "invested_eur": invested_eur, "current_val_eur": current_val_eur,
            "pnl_eur": pnl_eur, "pnl_pct": pnl_pct, "initial_risk_eur": initial_risk_eur,
            "depot_risk_pct": depot_risk_pct, "crv": crv, "earnings_days": earnings_days,
            "matrix_scenario": matrix_scenario, "matrix_action": matrix_action, "urgency": urgency
        }
