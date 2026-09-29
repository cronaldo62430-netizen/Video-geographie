"""Rendu image par image : cartes animées, titres, sous-titres."""
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .geo import DATA, World, merc_y

COLORS = {
    "red": (225, 40, 40), "blue": (35, 110, 235), "green": (40, 165, 75),
    "yellow": (250, 205, 30), "purple": (135, 60, 175), "orange": (250, 130, 25),
}


def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def ease_back(t: float) -> float:
    t = min(1.0, max(0.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def font(bold: bool, size: int):
    for name in (("Poppins-ExtraBold.ttf" if bold else "Poppins-SemiBold.ttf"),):
        p = DATA / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def outlined(draw, xy, text, fnt, fill=(255, 255, 255), stroke=(0, 0, 0), sw=6, anchor="mm"):
    draw.text(xy, text, font=fnt, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def subtitle_chunks(narration: str, max_words=5):
    words = narration.split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.!?…:;,]$", w) and len(cur) >= 2:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


class Renderer:
    def __init__(self, cfg: dict, world: World):
        self.W, self.H, self.fps = cfg["width"], cfg["height"], cfg["fps"]
        self.handle = cfg["channel_handle"]
        self.world = world
        self.f_title = font(True, int(self.W * 0.125))
        self.f_sub = font(False, int(self.W * 0.052))
        self.f_label = font(True, int(self.W * 0.05))
        self.f_handle = font(False, int(self.W * 0.03))
        self._img_cache: dict[str, Image.Image] = {}

    # ---------- préparation d'une scène ----------
    def prepare(self, scene: dict, idx: int, workdir: Path):
        vis = scene.get("visual", {})
        st = {"scene": scene, "vis": vis, "kind": vis.get("type", "map")}
        if st["kind"] == "image":
            p = workdir / f"img{idx:02d}.png"
            if p.exists():
                st["img"] = Image.open(p).convert("RGB")
            else:
                st["kind"] = "map"
                vis = st["vis"] = {"type": "map", "zoom": [], "highlight": []}
        if st["kind"] == "map":
            w = self.world
            bbox = vis.get("bbox") or w.bbox(vis.get("zoom") or [c["country"] for c in vis.get("highlight", [])])
            if bbox is None:
                bbox = (-30, -40, 60, 45)
            lon0, lat0, lon1, lat1 = bbox
            x0, x1 = math.radians(lon0), math.radians(lon1)
            y0, y1 = merc_y(lat0), merc_y(lat1)
            asp = self.H / self.W
            width = max((x1 - x0) * 1.5, (y1 - y0) * 1.5 / asp, math.radians(6))
            st["cx"], st["cy"], st["width"] = (x0 + x1) / 2, (y0 + y1) / 2 - width * asp * 0.04, min(width, 2 * math.pi)
            st["hl"] = [(w.rings(c["country"]), COLORS.get(c.get("color", "red"), COLORS["red"])) for c in vis.get("highlight", [])]
            st["labels"] = []
            for l in vis.get("labels", []):
                c = w.centroid(l["country"])
                if c:
                    st["labels"].append((c[0], c[1], l["text"]))
            st["markers"] = [(m["lon"], m["lat"], m.get("text", "")) for m in vis.get("markers", [])]
        return st

    # ---------- carte ----------
    def _project(self, cx, cy, width, lon, lat):
        height = width * self.H / self.W
        x = (math.radians(lon) - (cx - width / 2)) / width * self.W
        y = ((cy + height / 2) - merc_y(lat)) / height * self.H
        return x, y

    def map_frame(self, st, t, dur) -> Image.Image:
        k = ease_in_out(t / dur)
        width = st["width"] * (1.35 - 0.35 * k)
        cx, cy = st["cx"], st["cy"]
        bg = self.world.sample(cx, cy, width, self.W, self.H).astype(np.float32)
        bg = bg * 0.95
        img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        # frontières discrètes
        for key, rings in self.world.countries.items():
            for ring in rings:
                if len(ring) < 8:
                    continue
                pts = [self._project(cx, cy, width, lon, lat) for lon, lat in ring[::2]]
                xs = [p[0] for p in pts]
                if max(xs) < 0 or min(xs) > self.W:
                    continue
                ys = [p[1] for p in pts]
                if max(ys) < 0 or min(ys) > self.H:
                    continue
                d.line(pts + [pts[0]], fill=(255, 255, 255, 70), width=1)
        # pays surlignés (apparition échelonnée)
        for i, (rings, col) in enumerate(st["hl"]):
            a = ease_out((t - 0.3 - 0.35 * i) / 0.6)
            if a <= 0:
                continue
            for ring in rings:
                pts = [self._project(cx, cy, width, lon, lat) for lon, lat in ring]
                d.polygon(pts, fill=col + (int(200 * a),))
                d.line(pts + [pts[0]], fill=(255, 255, 255, int(255 * a)), width=3)
        img = Image.alpha_composite(img, over)
        d = ImageDraw.Draw(img)
        for i, (lon, lat, txt) in enumerate(st["labels"]):
            a = ease_out((t - 0.6 - 0.3 * i) / 0.4)
            if a > 0:
                x, y = self._project(cx, cy, width, lon, lat)
                outlined(d, (x, y), txt, self.f_label, fill=(255, 255, 255, int(255 * a)), stroke=(0, 0, 0, int(255 * a)), sw=5)
        for i, (lon, lat, txt) in enumerate(st["markers"]):
            a = ease_back((t - 0.5 - 0.3 * i) / 0.4)
            if a > 0:
                x, y = self._project(cx, cy, width, lon, lat)
                r = 11 * a
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 215, 0), outline=(0, 0, 0), width=3)
                outlined(d, (x, y - 34), txt, self.f_label, sw=5)
        return img.convert("RGB")

    # ---------- image IA (Ken Burns) ----------
    def image_frame(self, st, t, dur) -> Image.Image:
        src = st["img"]
        k = t / dur
        z = 1.0 + 0.12 * k
        sw, sh = src.size
        target = self.W / self.H
        cw = sh * target if sw / sh > target else sw
        ch = cw / target
        cw, ch = cw / z, ch / z
        x0 = (sw - cw) / 2 + (sw - cw) * 0.1 * (k - 0.5)
        y0 = (sh - ch) / 2
        return src.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((self.W, self.H), Image.LANCZOS)

    # ---------- surcouches ----------
    def overlays(self, img: Image.Image, st, t, dur) -> Image.Image:
        img = img.convert("RGBA")
        # dégradé bas pour lisibilité des sous-titres
        grad = np.zeros((self.H, self.W, 4), np.uint8)
        start = int(self.H * 0.6)
        ramp = np.linspace(0, 150, self.H - start).astype(np.uint8)
        grad[start:, :, 3] = ramp[:, None]
        img = Image.alpha_composite(img, Image.fromarray(grad, "RGBA"))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # gros titre (pop-in)
        title = st["scene"].get("text")
        if title:
            s = ease_back(t / 0.35)
            tl = Image.new("RGBA", (self.W, int(self.H * 0.3)), (0, 0, 0, 0))
            td = ImageDraw.Draw(tl)
            lines = wrap(td, title, self.f_title, self.W * 0.88)
            lh = self.f_title.size * 1.15
            y0 = tl.height / 2 - lh * (len(lines) - 1) / 2
            for j, ln in enumerate(lines):
                outlined(td, (self.W / 2, y0 + j * lh), ln, self.f_title, sw=8)
            if abs(s - 1) > 1e-3:
                nw, nh = max(1, int(tl.width * s)), max(1, int(tl.height * s))
                tl = tl.resize((nw, nh), Image.BILINEAR)
            else:
                nw, nh = tl.size
            layer.alpha_composite(tl, (int((self.W - nw) / 2), int(self.H * 0.09 + (self.H * 0.3 - nh) / 2)))
        # sous-titres synchronisés
        chunks = subtitle_chunks(st["scene"]["narration"])
        total = sum(len(c) for c in chunks) or 1
        speech = max(0.1, dur - 0.3)
        acc, cur = 0.0, chunks[-1] if chunks else ""
        for c in chunks:
            acc += len(c) / total * speech
            if t <= acc:
                cur = c
                break
        lines = wrap(d, cur, self.f_sub, self.W * 0.86)
        lh = self.f_sub.size * 1.25
        y = self.H * 0.78 - lh * (len(lines) - 1) / 2
        for j, ln in enumerate(lines):
            outlined(d, (self.W / 2, y + j * lh), ln, self.f_sub, sw=6)
        d.text((self.W - 24, self.H - 46), self.handle, font=self.f_handle, fill=(255, 255, 255, 190), anchor="rm")
        return Image.alpha_composite(img, layer).convert("RGB")

    def frame(self, st, t, dur) -> Image.Image:
        base = self.image_frame(st, t, dur) if st["kind"] == "image" else self.map_frame(st, t, dur)
        return self.overlays(base, st, t, dur)

    def outro(self, t, dur) -> Image.Image:
        img = Image.new("RGB", (self.W, self.H), (12, 18, 30))
        d = ImageDraw.Draw(img)
        a = ease_out(t / 0.5)
        col = tuple(int(255 * a) for _ in range(3))
        outlined(d, (self.W / 2, self.H * 0.45), "Abonne-toi", self.f_title, fill=col, stroke=(0, 0, 0), sw=0)
        outlined(d, (self.W / 2, self.H * 0.55), self.handle, self.f_label, fill=col, stroke=(0, 0, 0), sw=0)
        return img
