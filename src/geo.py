"""Données cartographiques (Natural Earth) et projection Web Mercator."""
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import requests
from PIL import Image

DATA = Path(__file__).resolve().parent.parent / "data"
GEOJSON_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
RASTER_URL = "https://naturalearth.s3.amazonaws.com/50m_raster/NE1_50M_SR_W.zip"
FONT_URLS = {
    "Poppins-ExtraBold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-ExtraBold.ttf",
    "Poppins-SemiBold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-SemiBold.ttf",
}


def _download(url: str) -> bytes:
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    return r.content


def ensure_data() -> None:
    DATA.mkdir(exist_ok=True)
    geo = DATA / "countries.geojson"
    if not geo.exists():
        print("Téléchargement des frontières...")
        geo.write_bytes(_download(GEOJSON_URL))
    tif = DATA / "relief.tif"
    if not tif.exists():
        print("Téléchargement du fond satellite/relief (~90 Mo)...")
        with zipfile.ZipFile(io.BytesIO(_download(RASTER_URL))) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".tif"))
            tif.write_bytes(z.read(name))
    for fname, url in FONT_URLS.items():
        f = DATA / fname
        if not f.exists():
            try:
                f.write_bytes(_download(url))
            except Exception as e:  # police de secours utilisée plus tard
                print(f"Police {fname} indisponible ({e})")


def merc_y(lat: float) -> float:
    lat = max(-85.0, min(85.0, lat))
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def inv_merc_y(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


class World:
    def __init__(self) -> None:
        ensure_data()
        Image.MAX_IMAGE_PIXELS = None
        self.raster = np.asarray(Image.open(DATA / "relief.tif").convert("RGB"))
        self.rh, self.rw = self.raster.shape[:2]
        self.countries: dict[str, list] = {}
        self._index: dict[str, str] = {}
        data = json.loads((DATA / "countries.geojson").read_text())
        for f in data["features"]:
            p = f["properties"]
            geom = f["geometry"]
            polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
            rings = [poly[0] for poly in polys]  # anneaux extérieurs uniquement
            key = p["ADM0_A3"]
            self.countries[key] = rings
            for k in (p.get("ISO_A3"), p.get("ISO_A3_EH"), p.get("NAME"), p.get("NAME_LONG"), p.get("ADMIN"), p.get("NAME_FR")):
                if k and k != "-99":
                    self._index[str(k).lower()] = key

    def resolve(self, ident: str) -> str | None:
        return self._index.get(ident.lower()) or (ident.upper() if ident.upper() in self.countries else None)

    def rings(self, ident: str):
        k = self.resolve(ident)
        return self.countries[k] if k else []

    def bbox(self, idents):
        lons, lats = [], []
        for i in idents:
            # ignore les îles lointaines : on ne garde que les 3 plus grands anneaux
            rings = sorted(self.rings(i), key=len, reverse=True)[:3]
            for ring in rings:
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
        if not lons:
            return None
        return min(lons), min(lats), max(lons), max(lats)

    def centroid(self, ident: str):
        rings = self.rings(ident)
        if not rings:
            return None
        ring = max(rings, key=len)
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def sample(self, cx: float, cy: float, width: float, W: int, H: int) -> np.ndarray:
        """Fond relief pour une vue Mercator centrée (cx, cy) de largeur `width` (unités mercator)."""
        height = width * H / W
        xs = cx + (np.arange(W) / W - 0.5) * width
        ys = cy + (0.5 - np.arange(H) / H) * height
        lon = np.degrees(xs)
        lat = inv_merc_y(ys)
        cols = np.clip(((lon + 180) / 360 * self.rw).astype(int), 0, self.rw - 1)
        rows = np.clip(((90 - lat) / 180 * self.rh).astype(int), 0, self.rh - 1)
        return self.raster[np.ix_(rows, cols)]
