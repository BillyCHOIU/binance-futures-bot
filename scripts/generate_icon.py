"""FluxBot icon: AI robot face + fintech accents. Outputs PNG/ICO + desktop preview."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def draw(size: int) -> Image.Image:
    """
    深色圆角底 + 立体机器人头（大眼睛/天线/耳部）
    胸口小能量条暗示交易/数据，整体 AI 感优先。
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = float(size)

    def r(a, b, c, e):
        return [int(a * s), int(b * s), int(c * s), int(e * s)]

    def rr(box, rad, **kw):
        d.rounded_rectangle(box, radius=max(1, int(rad * s)), **kw)

    # —— 底板 ——
    rr(r(0.02, 0.02, 0.98, 0.98), 0.22, fill=(10, 14, 28, 255))
    # 内圈微光
    rr(r(0.07, 0.07, 0.93, 0.93), 0.19, fill=(18, 28, 52, 255))

    # 角落点缀（电路感）
    cyan = (56, 189, 248, 220)
    for cx, cy in ((0.14, 0.14), (0.86, 0.14), (0.14, 0.86), (0.86, 0.86)):
        x, y = int(cx * s), int(cy * s)
        rad = max(2, size // 40)
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=cyan)

    # —— 天线 ——
    ax, ay = size // 2, int(0.14 * s)
    d.line([(ax, int(0.22 * s)), (ax, ay)], fill=(148, 197, 255, 255), width=max(2, size // 36))
    d.ellipse(
        [ax - size // 18, ay - size // 18, ax + size // 18, ay + size // 18],
        fill=(34, 211, 238, 255),
    )
    d.ellipse(
        [ax - size // 36, ay - size // 36, ax + size // 36, ay + size // 36],
        fill=(224, 252, 255, 255),
    )

    # —— 头 ——
    head = r(0.18, 0.24, 0.82, 0.72)
    rr(head, 0.16, fill=(36, 52, 88, 255))
    # 高光边
    rr(head, 0.16, outline=(96, 165, 250, 200), width=max(2, size // 48))

    # 侧耳
    ear_w = 0.07
    for ex in (0.12, 0.81):
        rr(r(ex, 0.38, ex + ear_w, 0.58), 0.04, fill=(45, 70, 120, 255))
        d.ellipse(
            r(ex + 0.015, 0.44, ex + ear_w - 0.015, 0.52),
            fill=(56, 189, 248, 255),
        )

    # —— 面罩/眼区 ——
    rr(r(0.26, 0.34, 0.74, 0.54), 0.08, fill=(12, 20, 38, 255))

    # 双眼（大，AI感）
    eye_y0, eye_y1 = 0.38, 0.50
    for ex0, ex1 in ((0.30, 0.46), (0.54, 0.70)):
        rr(r(ex0, eye_y0, ex1, eye_y1), 0.06, fill=(8, 145, 178, 255))
        # 瞳孔亮点
        px = (ex0 + ex1) / 2
        py = (eye_y0 + eye_y1) / 2
        pr = 0.035
        d.ellipse(r(px - pr, py - pr, px + pr, py + pr), fill=(165, 243, 252, 255))
        d.ellipse(
            r(px - pr * 0.45, py - pr * 0.55, px - pr * 0.05, py - pr * 0.15),
            fill=(255, 255, 255, 230),
        )

    # 中间传感器
    d.ellipse(r(0.46, 0.40, 0.54, 0.48), fill=(125, 211, 252, 255))

    # 嘴：数据条 / 微笑折线
    mouth_y = 0.60
    pts = [
        (0.34 * s, mouth_y * s),
        (0.42 * s, 0.64 * s),
        (0.50 * s, 0.60 * s),
        (0.58 * s, 0.64 * s),
        (0.66 * s, 0.60 * s),
    ]
    d.line(pts, fill=(103, 232, 249, 255), width=max(2, size // 32), joint="curve")

    # —— 身体/底座小块（机器人下颚） ——
    rr(r(0.30, 0.70, 0.70, 0.86), 0.08, fill=(30, 48, 80, 255))
    rr(r(0.30, 0.70, 0.70, 0.86), 0.08, outline=(59, 130, 246, 180), width=max(1, size // 64))

    # 胸口能量条（3格，交易/算力感）
    bar_cols = [(46, 214, 163, 255), (56, 189, 248, 255), (167, 139, 250, 255)]
    for i, col in enumerate(bar_cols):
        x0 = 0.36 + i * 0.10
        rr(r(x0, 0.75, x0 + 0.08, 0.82), 0.02, fill=col)

    # 颈连线
    d.rectangle(r(0.46, 0.68, 0.54, 0.72), fill=(70, 110, 180, 255))

    return img


def save_ico(path: Path, images: list[Image.Image], sizes: list[int]) -> None:
    # Pillow: 用最大图为主 + append
    images[-1].save(
        path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )


def main() -> None:
    sizes_png = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    imgs = {s: draw(s) for s in sizes_png}

    imgs[1024].save(OUT / "fluxbot_icon.png")
    imgs[512].save(OUT / "fluxbot_icon_512.png")
    imgs[256].save(OUT / "fluxbot_icon_256.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_imgs = [imgs[s] for s in ico_sizes]
    ico_path = OUT / "fluxbot.ico"
    save_ico(ico_path, ico_imgs, ico_sizes)

    # 桌面预览（你点名的路径）
    preview = Path(r"C:\Users\user\Desktop\FluxBot_icon_preview.png")
    imgs[512].save(preview)

    print("PNG 1024:", OUT / "fluxbot_icon.png", (OUT / "fluxbot_icon.png").stat().st_size)
    print("ICO:", ico_path, ico_path.stat().st_size)
    print("Preview:", preview, preview.stat().st_size)


if __name__ == "__main__":
    main()
