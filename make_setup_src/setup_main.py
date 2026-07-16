"""
FluxBot single-file installer.
Run as frozen FluxBot-Setup.exe: extract app to %LOCALAPPDATA%\\FluxBot,
create Desktop shortcut, optional launch.
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    # dev: look next to this file / project
    here = Path(__file__).resolve().parent
    for p in (here / name, here.parent / name, here.parent / "dist" / name):
        if p.exists():
            return p
    return here / name


def install_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FluxBot"


def create_shortcut(target: Path, workdir: Path) -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    link = desktop / "FluxBot.lnk"
    import subprocess

    cmd = (
        f"$ws=New-Object -ComObject WScript.Shell; "
        f"$s=$ws.CreateShortcut('{link}'); "
        f"$s.TargetPath='{target}'; "
        f"$s.WorkingDirectory='{workdir}'; "
        f"$s.Description='FluxBot Binance Futures'; "
        f"$s.Save()"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"创建快捷方式失败: {r.stderr or r.stdout}")
    return link


def do_install(status_cb=None) -> Path:
    def log(msg: str) -> None:
        if status_cb:
            status_cb(msg)
        print(msg)

    payload = resource_path("fluxbot_payload.zip")
    if not payload.exists():
        raise FileNotFoundError(
            f"缺少安装包数据: {payload}\n请先运行 make_setup.py 生成安装程序。"
        )

    dest = install_dir()
    log(f"安装目录: {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    # Preserve existing .env if reinstall
    old_env = dest / ".env"
    env_backup = None
    if old_env.exists():
        env_backup = old_env.read_bytes()
        log("保留已有 .env 密钥配置")

    log("正在解压…")
    with zipfile.ZipFile(payload, "r") as zf:
        zf.extractall(dest)

    if env_backup is not None:
        old_env.write_bytes(env_backup)

    exe = dest / "FluxBot.exe"
    if not exe.exists():
        raise FileNotFoundError("解压后未找到 FluxBot.exe")

    log("创建桌面快捷方式…")
    create_shortcut(exe, dest)
    log("安装完成。")
    return exe


def main_cli() -> None:
    try:
        exe = do_install()
        print(f"OK: {exe}")
        print("桌面快捷方式: FluxBot.lnk")
    except Exception as e:
        print(f"安装失败: {e}")
        input("按回车退出…")
        sys.exit(1)


def main_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("FluxBot 安装程序")
    root.geometry("460x260")
    root.resizable(False, False)

    tk.Label(
        root,
        text="FluxBot · 合约智控",
        font=("Microsoft YaHei UI", 16, "bold"),
    ).pack(pady=(20, 6))
    tk.Label(
        root,
        text="将安装到本机并创建桌面快捷方式\n无需安装 Python",
        font=("Microsoft YaHei UI", 10),
        justify="center",
    ).pack(pady=4)

    status = tk.StringVar(value="点击「安装」开始")
    tk.Label(root, textvariable=status, font=("Consolas", 9), fg="#333").pack(pady=10)

    def on_install() -> None:
        btn.config(state="disabled")
        try:
            def cb(m: str) -> None:
                status.set(m)
                root.update_idletasks()

            exe = do_install(status_cb=cb)
            status.set("安装成功！")
            launch = messagebox.askyesno("完成", "安装成功。\n是否立即启动 FluxBot？")
            if launch:
                os.startfile(str(exe))  # noqa: S606
            root.destroy()
        except Exception as e:
            messagebox.showerror("失败", str(e))
            status.set(f"失败: {e}")
            btn.config(state="normal")

    btn = tk.Button(
        root,
        text="安  装",
        font=("Microsoft YaHei UI", 12, "bold"),
        width=16,
        height=2,
        command=on_install,
        bg="#1f6aa5",
        fg="white",
        activebackground="#155a8a",
        activeforeground="white",
    )
    btn.pack(pady=12)

    tk.Label(
        root,
        text="风险提示：合约交易可能导致本金损失，软件不保证盈利。",
        font=("Microsoft YaHei UI", 8),
        fg="#666",
    ).pack(side="bottom", pady=8)

    root.mainloop()


if __name__ == "__main__":
    # Prefer GUI
    try:
        main_gui()
    except Exception:
        main_cli()
