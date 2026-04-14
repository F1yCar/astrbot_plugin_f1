import os
from PIL import Image


def apply_f1_logo(
    canvas,
    logo_path="assets/f1_logo.png",
    max_width_ratio=0.18,
    margin=(24, 20),
    opacity=235,
    position="top-left",
):
    """在画布指定位置叠加 F1 logo（若文件不存在则静默跳过）。"""
    if not os.path.exists(logo_path):
        return False

    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return False

    canvas_w, canvas_h = canvas.size
    target_w = max(120, int(canvas_w * max_width_ratio))
    target_h = int(target_w * logo.height / logo.width)
    logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)

    if opacity < 255:
        r, g, b, a = logo.split()
        a = a.point(lambda p: int(p * (opacity / 255)))
        logo = Image.merge("RGBA", (r, g, b, a))

    if position == "top-left":
        x = margin[0]
        y = margin[1]
    elif position == "bottom-left":
        x = margin[0]
        y = canvas_h - target_h - margin[1]
    elif position == "bottom-right":
        x = canvas_w - target_w - margin[0]
        y = canvas_h - target_h - margin[1]
    else:
        # top-right (默认兜底)
        x = canvas_w - target_w - margin[0]
        y = margin[1]

    canvas.paste(logo, (x, y), logo)
    return True
