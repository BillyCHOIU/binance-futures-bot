from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# 保证项目根在 path（开发模式）
if not getattr(sys, "frozen", False):
    _DEV_ROOT = Path(__file__).resolve().parents[1]
    if str(_DEV_ROOT) not in sys.path:
        sys.path.insert(0, str(_DEV_ROOT))

import customtkinter as ctk
from dotenv import load_dotenv, set_key

from app.config_loader import load_config
from app.engine import TradingEngine
from app.gui_icon import apply_window_icon
from app.paths import app_dir, ensure_user_files

ENV_PATH = app_dir() / ".env"


class FluxBotApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ensure_user_files()
        self.cfg = load_config()
        global ENV_PATH
        ENV_PATH = app_dir() / ".env"
        title = (self.cfg.get("gui") or {}).get("title") or "FluxBot"
        appearance = (self.cfg.get("gui") or {}).get("appearance") or "dark"
        ctk.set_appearance_mode(appearance)
        ctk.set_default_color_theme("blue")

        self.title(title)
        self.geometry("960x720")
        self.minsize(860, 640)
        apply_window_icon(self)

        self.engine = TradingEngine(on_log=self._append_log_threadsafe)
        self._build()
        self._load_env_fields()
        self._append_log("欢迎使用 FluxBot。请先填 API（仅合约交易权限，禁止提现），建议先 Testnet。")
        self._append_log("风险提示：合约交易可能导致本金全部损失。机器人不保证盈利。")
        self._append_log(
            "【舆情】API密钥下方有蓝色拨动开关「启用舆情门控」——默认已开，"
            "不是方框勾选。开着时 X/Reddit/公告 会限制多空方向。"
        )

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkLabel(
            self,
            text="FluxBot · 舆情定方向 · 指标过滤 · 硬风控",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        form = ctk.CTkFrame(self)
        form.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="API Key").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.key_entry = ctk.CTkEntry(form, placeholder_text="BINANCE_API_KEY", show="*")
        self.key_entry.grid(row=0, column=1, padx=8, pady=6, sticky="ew")

        ctk.CTkLabel(form, text="API Secret").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        self.secret_entry = ctk.CTkEntry(form, placeholder_text="BINANCE_API_SECRET", show="*")
        self.secret_entry.grid(row=1, column=1, padx=8, pady=6, sticky="ew")

        self.testnet_var = ctk.BooleanVar(value=True)
        self.testnet_sw = ctk.CTkSwitch(form, text="使用 Testnet（强烈建议先开）", variable=self.testnet_var)
        self.testnet_sw.grid(row=2, column=0, columnspan=2, padx=8, pady=6, sticky="w")

        # 舆情：显眼分区（开关不是方框勾选，是左右拨动）
        news_box = ctk.CTkFrame(form, border_width=1)
        news_box.grid(row=3, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
        news_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            news_box,
            text="舆情方向（X / Reddit / 公告 / 媒体）",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
        self.news_var = ctk.BooleanVar(value=True)
        self.news_sw = ctk.CTkSwitch(
            news_box,
            text="启用舆情门控（开=舆情定多空方向；关=纯技术策略）",
            variable=self.news_var,
            command=self._on_news_toggle,
        )
        self.news_sw.grid(row=1, column=0, padx=10, pady=(2, 4), sticky="w")
        self.news_hint = ctk.CTkLabel(
            news_box,
            text="默认：已开启。这是「拨动开关」，不是方框打勾。开着时所有策略都会吃 X/Reddit/公告 方向。",
            text_color="gray",
            wraplength=820,
            justify="left",
        )
        self.news_hint.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="w")

        # 单仓 / 多仓
        pos_row = ctk.CTkFrame(form, fg_color="transparent")
        pos_row.grid(row=4, column=0, columnspan=2, padx=8, pady=6, sticky="ew")
        self.multi_pos_var = ctk.BooleanVar(value=False)
        self.multi_pos_sw = ctk.CTkSwitch(
            pos_row,
            text="允许多仓（关闭=严格单仓）",
            variable=self.multi_pos_var,
            command=self._on_pos_mode_change,
        )
        self.multi_pos_sw.pack(side="left")
        ctk.CTkLabel(pos_row, text="  上限").pack(side="left", padx=(12, 4))
        self.max_pos_var = ctk.StringVar(value="3")
        self.max_pos_menu = ctk.CTkOptionMenu(
            pos_row,
            values=["2", "3", "4", "5"],
            variable=self.max_pos_var,
            width=70,
            command=lambda _v: self._apply_position_limit(),
        )
        self.max_pos_menu.pack(side="left")
        self.max_pos_menu.configure(state="disabled")
        ctk.CTkLabel(pos_row, text="（建议新手保持单仓）", text_color="gray").pack(side="left", padx=8)

        # 杠杆
        lev_row = ctk.CTkFrame(form, fg_color="transparent")
        lev_row.grid(row=5, column=0, columnspan=2, padx=8, pady=6, sticky="ew")
        ctk.CTkLabel(lev_row, text="杠杆倍数").pack(side="left")
        max_lev = int((self.cfg.get("trading") or {}).get("max_leverage", 10))
        max_lev = max(1, min(max_lev, 20))
        lev_values = [str(i) for i in range(1, max_lev + 1)]
        default_lev = str(int((self.cfg.get("trading") or {}).get("leverage", 5)))
        if default_lev not in lev_values:
            default_lev = "5" if "5" in lev_values else lev_values[0]
        self.leverage_var = ctk.StringVar(value=default_lev)
        self.leverage_menu = ctk.CTkOptionMenu(
            lev_row,
            values=lev_values,
            variable=self.leverage_var,
            width=80,
            command=lambda _v: self._apply_leverage(),
        )
        self.leverage_menu.pack(side="left", padx=8)
        ctk.CTkLabel(
            lev_row,
            text=f"x  （最高 {max_lev}x，杠杆越高爆仓风险越大）",
            text_color="gray",
        ).pack(side="left")
        self._max_lev_ui = max_lev

        # 策略选择
        strat_row = ctk.CTkFrame(form, fg_color="transparent")
        strat_row.grid(row=6, column=0, columnspan=2, padx=8, pady=6, sticky="ew")
        ctk.CTkLabel(strat_row, text="交易策略").pack(side="left")
        self._strategy_id_by_label: dict[str, str] = {}
        labels: list[str] = []
        for sid, label, _desc in self.engine.list_strategies():
            # 显示名唯一
            display = label if label not in labels else f"{label} ({sid})"
            labels.append(display)
            self._strategy_id_by_label[display] = sid
        active_id = getattr(self.engine, "strategy_id", "trend_ema")
        active_label = next(
            (lab for lab, sid in self._strategy_id_by_label.items() if sid == active_id),
            labels[0] if labels else "EMA趋势",
        )
        self.strategy_var = ctk.StringVar(value=active_label)
        self.strategy_menu = ctk.CTkOptionMenu(
            strat_row,
            values=labels or ["EMA趋势"],
            variable=self.strategy_var,
            width=180,
        )
        self.strategy_menu.pack(side="left", padx=8)
        ctk.CTkButton(strat_row, text="应用策略", width=80, command=self.apply_strategy).pack(
            side="left", padx=4
        )
        ctk.CTkButton(strat_row, text="重载", width=60, command=self.reload_strategies).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            strat_row, text="策略文件夹", width=90, command=self.open_strategies_folder
        ).pack(side="left", padx=4)

        btns = ctk.CTkFrame(self)
        btns.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        for i in range(5):
            btns.grid_columnconfigure(i, weight=1)

        self.btn_save = ctk.CTkButton(btns, text="保存 Key", command=self.save_keys)
        self.btn_save.grid(row=0, column=0, padx=6, pady=8, sticky="ew")

        self.btn_connect = ctk.CTkButton(btns, text="连接交易所", command=self.connect)
        self.btn_connect.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        self.btn_start = ctk.CTkButton(btns, text="启动机器人", fg_color="#1f6aa5", command=self.start_bot)
        self.btn_start.grid(row=0, column=2, padx=6, pady=8, sticky="ew")

        self.btn_stop = ctk.CTkButton(btns, text="停止", fg_color="#6b2d2d", command=self.stop_bot)
        self.btn_stop.grid(row=0, column=3, padx=6, pady=8, sticky="ew")

        self.btn_close = ctk.CTkButton(btns, text="全部平仓", fg_color="#8B4513", command=self.close_all)
        self.btn_close.grid(row=0, column=4, padx=6, pady=8, sticky="ew")

        self.status = ctk.CTkLabel(self, text="状态: 未连接", anchor="w")
        self.status.grid(row=4, column=0, padx=16, pady=(0, 4), sticky="ew")

        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13))
        self.log_box.grid(row=3, column=0, padx=16, pady=8, sticky="nsew")
        self.log_box.configure(state="disabled")

        self.btn_news = ctk.CTkButton(self, text="立即刷新舆情摘要", command=self.refresh_news)
        self.btn_news.grid(row=5, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _load_env_fields(self) -> None:
        load_dotenv(ENV_PATH)
        k = os.getenv("BINANCE_API_KEY", "")
        s = os.getenv("BINANCE_API_SECRET", "")
        t = os.getenv("USE_TESTNET", "true").lower() in {"1", "true", "yes", "y"}
        if k:
            self.key_entry.insert(0, k)
        if s:
            self.secret_entry.insert(0, s)
        self.testnet_var.set(t)

        multi = os.getenv("ALLOW_MULTI_POSITION", "false").lower() in {"1", "true", "yes", "y"}
        max_p = os.getenv("MAX_POSITIONS", "3").strip() or "3"
        if max_p not in {"2", "3", "4", "5"}:
            max_p = "3"
        self.multi_pos_var.set(multi)
        self.max_pos_var.set(max_p)
        self._on_pos_mode_change()
        self._apply_position_limit()

        lev = os.getenv("LEVERAGE", "").strip()
        if not lev:
            lev = str(int((self.cfg.get("trading") or {}).get("leverage", 5)))
        max_lev = getattr(self, "_max_lev_ui", 10)
        try:
            lev_i = max(1, min(int(lev), max_lev))
        except ValueError:
            lev_i = 5
        self.leverage_var.set(str(lev_i))
        self._apply_leverage()

    def _on_news_toggle(self) -> None:
        on = self.news_var.get()
        self.engine.news_enabled = on
        if hasattr(self, "log_box"):
            self._append_log("舆情门控: " + ("已开启（X/Reddit/公告定方向）" if on else "已关闭（纯技术）"))

    def _on_pos_mode_change(self) -> None:
        if self.multi_pos_var.get():
            self.max_pos_menu.configure(state="normal")
        else:
            self.max_pos_menu.configure(state="disabled")
        self._apply_position_limit()

    def _apply_position_limit(self) -> None:
        if self.multi_pos_var.get():
            try:
                n = int(self.max_pos_var.get())
            except ValueError:
                n = 3
            n = max(2, min(n, 5))
        else:
            n = 1
        self.engine.set_position_limit(n)
        mode = "单仓" if n == 1 else f"多仓上限 {n}"
        if hasattr(self, "log_box"):
            self._append_log(f"持仓模式: {mode}")

    def _apply_leverage(self) -> None:
        try:
            lev = int(self.leverage_var.get())
        except ValueError:
            lev = 5
        max_lev = getattr(self, "_max_lev_ui", 10)
        lev = max(1, min(lev, max_lev))
        self.leverage_var.set(str(lev))
        self.engine.set_leverage(lev)
        if hasattr(self, "log_box"):
            self._append_log(f"杠杆倍数: {lev}x")

    def _refresh_strategy_menu(self) -> None:
        self._strategy_id_by_label = {}
        labels: list[str] = []
        for sid, label, _desc in self.engine.list_strategies():
            display = label if label not in labels else f"{label} ({sid})"
            labels.append(display)
            self._strategy_id_by_label[display] = sid
        if not labels:
            labels = ["EMA趋势"]
            self._strategy_id_by_label["EMA趋势"] = "trend_ema"
        self.strategy_menu.configure(values=labels)
        active_id = getattr(self.engine, "strategy_id", "trend_ema")
        for lab, sid in self._strategy_id_by_label.items():
            if sid == active_id:
                self.strategy_var.set(lab)
                break
        else:
            self.strategy_var.set(labels[0])

    def apply_strategy(self) -> None:
        label = self.strategy_var.get()
        sid = self._strategy_id_by_label.get(label, "trend_ema")
        try:
            # 切换时带上 config 里该策略的 presets
            from app.strategy.registry import catalog, resolve_active_from_config
            import yaml
            from app.paths import app_dir

            cfg_path = app_dir() / "config.yaml"
            cfg = {}
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            cfg.setdefault("strategy", {})["active"] = sid
            _aid, params = resolve_active_from_config(cfg)
            # 若 presets 无，用内置 defaults
            if not params:
                meta = catalog().get(sid) or {}
                params = dict(meta.get("defaults") or {})
            self.engine.set_strategy(sid, params)
            self._save_strategy_to_config(sid)
            name = getattr(self.engine.strategy, "name", sid)
            self._append_log(f"当前策略: {name} ({sid})")
            self._set_status(f"状态: 策略 → {name}")
        except Exception as e:
            self._append_log(f"切换策略失败: {e}")

    def reload_strategies(self) -> None:
        try:
            self.engine.reload_strategy()
            self._refresh_strategy_menu()
            self._append_log("已重载策略列表/插件")
            self.apply_strategy()
        except Exception as e:
            self._append_log(f"重载失败: {e}")

    def open_strategies_folder(self) -> None:
        from app.strategy.registry import strategies_dir
        import subprocess

        d = strategies_dir()
        self._append_log(f"策略目录: {d}")
        try:
            os.startfile(str(d))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", str(d)])

    def _save_strategy_to_config(self, strategy_id: str) -> None:
        from app.config_loader import save_config_patch

        save_config_patch({"strategy": {"active": strategy_id}})

    def _append_log_threadsafe(self, msg: str) -> None:
        self.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def save_keys(self) -> None:
        key = self.key_entry.get().strip()
        secret = self.secret_entry.get().strip()
        testnet = self.testnet_var.get()
        if not ENV_PATH.exists():
            ENV_PATH.write_text("", encoding="utf-8")
        set_key(str(ENV_PATH), "BINANCE_API_KEY", key)
        set_key(str(ENV_PATH), "BINANCE_API_SECRET", secret)
        set_key(str(ENV_PATH), "USE_TESTNET", "true" if testnet else "false")
        set_key(
            str(ENV_PATH),
            "ALLOW_MULTI_POSITION",
            "true" if self.multi_pos_var.get() else "false",
        )
        set_key(str(ENV_PATH), "MAX_POSITIONS", self.max_pos_var.get().strip() or "3")
        set_key(str(ENV_PATH), "LEVERAGE", self.leverage_var.get().strip() or "5")
        self._apply_position_limit()
        self._apply_leverage()
        self._append_log("已保存到 .env（请勿分享该文件）")

    def connect(self) -> None:
        def job() -> None:
            try:
                self.save_keys()
                key = self.key_entry.get().strip()
                secret = self.secret_entry.get().strip()
                testnet = self.testnet_var.get()
                self.engine.connect(key, secret, testnet)
                self.after(0, lambda: self._set_status(f"状态: 已连接 | testnet={testnet}"))
            except Exception as e:
                self._append_log_threadsafe(f"连接失败: {e}")
                self.after(0, lambda: self._set_status(f"状态: 连接失败 — {e}"))

        threading.Thread(target=job, daemon=True).start()

    def start_bot(self) -> None:
        self.engine.news_enabled = self.news_var.get()
        self._apply_position_limit()
        self._apply_leverage()
        self.apply_strategy()

        def job() -> None:
            try:
                if not self.engine.exchange:
                    key = self.key_entry.get().strip()
                    secret = self.secret_entry.get().strip()
                    self.engine.connect(key, secret, self.testnet_var.get())
                self.engine.start()
                lim = self.engine.risk.max_positions
                mode = "单仓" if lim <= 1 else f"多仓≤{lim}"
                lev = self.engine.leverage
                sn = getattr(self.engine.strategy, "name", self.engine.strategy_id)
                self.after(
                    0,
                    lambda: self._set_status(f"状态: 运行中 | {mode} | {lev}x | {sn}"),
                )
            except Exception as e:
                self._append_log_threadsafe(f"启动失败: {e}")

        threading.Thread(target=job, daemon=True).start()

    def stop_bot(self) -> None:
        self.engine.stop()
        self._set_status("状态: 已停止")

    def close_all(self) -> None:
        def job() -> None:
            try:
                self.engine.close_all()
            except Exception as e:
                self._append_log_threadsafe(f"平仓失败: {e}")

        threading.Thread(target=job, daemon=True).start()

    def refresh_news(self) -> None:
        def job() -> None:
            try:
                self.engine.news.refresh(force=True)
                g = self.engine.news.global_sentiment()
                self._append_log_threadsafe(f"全局舆情: {g}")
                for line in self.engine.news.latest_brief():
                    self._append_log_threadsafe("  " + line)
            except Exception as e:
                self._append_log_threadsafe(f"舆情刷新失败: {e}")

        threading.Thread(target=job, daemon=True).start()


def main() -> None:
    app = FluxBotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
