"""Full regression: unit paths + public market + optional read-only live connect. No real orders."""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

errors: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        errors.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    section("1) Core modules")
    try:
        from app.paths import ensure_user_files, strategies_dir, assets_dir
        from app.config_loader import load_config, setup_logging
        from app.storage import Store
        from app.risk import RiskManager
        from app.exchange import positions_match, symbol_base
        from app.strategy.registry import list_strategy_choices, build_strategy, BUILTIN
        from app.news.scoring import score_text
        from app.engine import TradingEngine, BracketBook
        from app.gui_icon import resolve_icon_path
        from app.main import FluxBotApp

        ensure_user_files()
        setup_logging()
        cfg = load_config()
        check("paths", ensure_user_files().exists() and strategies_dir().exists())
        check("config", "trading" in cfg and "risk" in cfg)
        check("icon", resolve_icon_path() is not None)
        check("gui", FluxBotApp is not None)

        db = Path(tempfile.gettempdir()) / "fluxbot_regression.db"
        if db.exists():
            db.unlink()
        st = Store(db)
        st.log_event("reg", "ok")
        check("store", len(st.recent_events(1)) >= 1)
        db.unlink(missing_ok=True)

        rm = RiskManager.from_config(cfg)
        rm.on_equity(1000)
        check("risk_open", rm.can_open(0)[0] is True)
        check("symbol_helpers", symbol_base("ETH/USDT:USDT") == "ETH" and positions_match("ETH/USDT:USDT", "ETH/USDT:USDT"))
        check("strategies", len(list_strategy_choices()) >= 3)
        check("score", score_text("etf approved") > 0 and score_text("hacked") < 0)

        eng = TradingEngine(on_log=lambda m: None)
        check("engine", eng.strategy is not None and isinstance(eng.brackets, BracketBook))
        for sid in BUILTIN:
            eng.set_strategy(sid)
            check(f"switch_{sid}", eng.strategy_id == sid)
    except Exception as e:
        traceback.print_exc()
        check("core_import", False, str(e))
        print("---")
        print(f"RESULT: FAIL {errors}")
        return 1

    section("2) Public market OHLCV")
    try:
        import ccxt

        ex = ccxt.binanceusdm({"enableRateLimit": True})
        ohlcv = ex.fetch_ohlcv("BTC/USDT:USDT", "15m", limit=120)
        check("public_ohlcv", len(ohlcv) >= 100, str(len(ohlcv)))
        ticker = ex.fetch_ticker("BTC/USDT:USDT")
        check("public_ticker", float(ticker.get("last") or 0) > 0)

        # signal smoke on live candles
        for sid in BUILTIN:
            stgy = build_strategy(sid, {}, lambda m: None)
            sig = stgy.evaluate("BTC/USDT:USDT", ohlcv, "BOTH", False)
            check(f"live_sig_{sid}", sig.action in ("open_long", "open_short", "hold"), sig.action)
    except Exception as e:
        traceback.print_exc()
        check("public_market", False, str(e))

    section("3) Backtest (sample window)")
    try:
        from scripts.backtest import fetch_ohlcv, run_backtest

        bars = fetch_ohlcv(limit=400)
        check("backtest_bars", len(bars) >= 200, str(len(bars)))
        for sid in BUILTIN:
            r = run_backtest(sid, bars, sentiment="BOTH")
            check(
                f"backtest_{sid}",
                r["trades"] >= 0 and r["max_drawdown"] >= 0,
                str(r),
            )
            print(
                f"  {sid}: trades={r['trades']} win={r['win_rate']:.1%} "
                f"ret={r['total_return']:+.2%} mdd={r['max_drawdown']:.2%}"
            )
        print("  (历史回测≠未来收益)")
    except Exception as e:
        traceback.print_exc()
        check("backtest", False, str(e))

    section("4) Read-only live account (NO ORDERS)")
    key = os.getenv("BINANCE_API_KEY", "").strip()
    secret = os.getenv("BINANCE_API_SECRET", "").strip()
    use_testnet = os.getenv("USE_TESTNET", "true").strip().lower() in {"1", "true", "yes", "y"}
    if not key or not secret:
        print("SKIP  no API keys in .env")
        check("live_readonly_skipped", True)
    else:
        try:
            from app.exchange.binance_f import BinanceFutures

            # Prefer testnet if flagged; if live keys, still read-only only
            client = BinanceFutures(key, secret, testnet=use_testnet, on_log=lambda m: print("  ", m))
            eq = client.fetch_equity()
            check("live_equity_read", eq >= 0, str(eq))
            poss = client.fetch_positions(None)
            check("live_positions_read", isinstance(poss, list), str(len(poss)))
            # one public private-mixed call
            o = client.fetch_ohlcv("BTC/USDT:USDT", "15m", limit=10)
            check("live_ohlcv_auth", len(o) >= 1)
            print(f"  testnet={use_testnet} equity≈{eq:.4f} positions={len(poss)}")
            print("  NO create_order called (safety)")
        except Exception as e:
            traceback.print_exc()
            check("live_readonly", False, str(e))

    section("5) Packaging artifacts check")
    # after build these should exist; before build just report
    dist_exe = ROOT / "dist" / "FluxBot" / "FluxBot.exe"
    setup = ROOT / "dist" / "FluxBot-Setup.exe"
    check("has_spec", (ROOT / "FluxBot.spec").exists())
    check("has_make_setup", (ROOT / "make_setup.py").exists())
    if dist_exe.exists():
        check("dist_exe_present", dist_exe.stat().st_size > 1_000_000)
    else:
        print("INFO  dist exe not built yet (will build next)")
    if setup.exists():
        check("setup_present", setup.stat().st_size > 10_000_000)
    else:
        print("INFO  setup not built yet (will build next)")

    print("\n---")
    if errors:
        print(f"RESULT: FAIL {errors}")
        return 1
    print("RESULT: ALL PASS (full regression, no orders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
