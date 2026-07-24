"""Draw a red box on a screenshot to mark the failing element (Pillow).

Playwright gives us the element's bounding_box(); Playwright itself has no
"draw a box" helper, so we composite the rectangle ourselves.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw


def box_element(png_bytes: bytes, box: dict | None) -> bytes:
    """Return a PNG with a red rectangle drawn around `box`
    ({x, y, width, height} from element.bounding_box()). If box is None or
    off-image, returns the original bytes unchanged."""
    if not box:
        return png_bytes
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    except Exception:
        return png_bytes

    x, y = box.get("x", 0), box.get("y", 0)
    w, h = box.get("width", 0), box.get("height", 0)
    if w <= 0 or h <= 0:
        return png_bytes

    draw = ImageDraw.Draw(img)
    # A slight outset + a 4px stroke so the box frames rather than covers.
    pad = 3
    draw.rectangle(
        [max(0, x - pad), max(0, y - pad), x + w + pad, y + h + pad],
        outline=(220, 38, 38), width=4,
    )
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
