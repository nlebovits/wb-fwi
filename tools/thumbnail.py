#!/usr/bin/env python3
"""Render each collection thumbnail from that collection's render.

    python3 tools/thumbnail.py

The method follows the portolan-thumbnails skill
(https://github.com/portolan-sdi/portolan-skills/tree/main/skills/portolan-thumbnails).
That skill draws PMTiles through chiitiler, which has no COG source, so this
script draws the COG itself:

1. Frame the collection bbox to the 3:2 card shape in Web Mercator.
2. Draw the Esri World Light Gray basemap, the first basemap the skill tries.
3. Draw the collection's first render over it, with the browser's ramp for
   its colormap_name, its rescale, and its nodata. The thumbnail shows what
   the browser shows.
4. Fail when fewer than MIN_DATA_FRACTION of the pixels show data. This is
   the skill's blank probe. A person still looks at the image.

Run tools/build.py first. The script reads each COG from staging/. Run
tools/build.py again afterwards, so file:size and file:checksum match.
"""
from __future__ import annotations

import io
import json
import math
import sys
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
STAGING = ROOT / "staging"

WIDTH, HEIGHT = 900, 600
MARGIN = 0.02
BASEMAP_ZOOM = 2
BASEMAP = ("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/"
           "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}")
USER_AGENT = "wb-fwi-thumbnail (+https://github.com/nlebovits/wb-fwi)"
MIN_DATA_FRACTION = 0.10

R = 6378137.0
HALF = math.pi * R


def mx(lon: float) -> float:
    return math.radians(lon) * R


def my(lat: float) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)
    return R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def frame(bbox: list[float]) -> tuple[float, float, float, float]:
    """Pad the bbox to 3:2 in Web Mercator, inside the world."""
    west, south, east, north = bbox
    x0, x1, y0, y1 = mx(west), mx(east), my(south), my(north)
    dx, dy = (x1 - x0) * MARGIN, (y1 - y0) * MARGIN
    x0, x1, y0, y1 = x0 - dx, x1 + dx, y0 - dy, y1 + dy
    x0, x1 = max(x0, -HALF), min(x1, HALF)
    target = WIDTH / HEIGHT
    if (x1 - x0) / (y1 - y0) > target:
        pad = ((x1 - x0) / target - (y1 - y0)) / 2
        y0, y1 = y0 - pad, y1 + pad
    else:
        pad = ((y1 - y0) * target - (x1 - x0)) / 2
        x0, x1 = x0 - pad, x1 + pad
    shift = (HALF - y1) if y1 > HALF else ((-HALF - y0) if y0 < -HALF else 0.0)
    return x0, y0 + shift, x1, y1 + shift


def basemap() -> np.ndarray:
    """The world at BASEMAP_ZOOM as one RGB array, in Web Mercator."""
    count = 2 ** BASEMAP_ZOOM
    world = Image.new("RGB", (256 * count, 256 * count))
    for x in range(count):
        for y in range(count):
            url = BASEMAP.format(z=BASEMAP_ZOOM, x=x, y=y)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                tile = Image.open(io.BytesIO(response.read())).convert("RGB")
            world.paste(tile, (256 * x, 256 * y))
    return np.asarray(world).transpose(2, 0, 1)


# The ramps the Portolan browser draws for a render's colormap_name, as
# [t, [r, g, b]] stops. Copied from src/utils/renders.js in portolan-browser,
# so the thumbnail matches the map.
RAMPS = {
    "rdylgn": [
        (0.0, (215, 25, 28)),
        (0.7, (254, 195, 121)),
        (0.8, (243, 250, 187)),
        (0.9, (207, 236, 176)),
        (1.0, (51, 160, 44)),
    ],
}


def colorize(values: np.ndarray, render: dict) -> np.ndarray:
    """RGBA from the render's named ramp and rescale. Nodata stays clear."""
    stops = RAMPS[render["colormap_name"]]
    low, high = render["rescale"][0]
    t = np.nan_to_num(np.clip((values - low) / ((high - low) or 1), 0, 1))
    positions = [stop for stop, _ in stops]
    rgba = np.zeros((4,) + values.shape, dtype=np.uint8)
    for channel in range(3):
        ramp = [color[channel] for _, color in stops]
        rgba[channel] = np.round(np.interp(t, positions, ramp)).astype(np.uint8)
    rgba[3] = np.where(np.isfinite(values), 255, 0)
    nodata = render.get("nodata")
    for value in nodata if isinstance(nodata, list) else [nodata]:
        if value is not None:
            rgba[3][values == value] = 0
    return rgba


def render_one(path: Path, world: np.ndarray) -> int:
    collection = json.loads(path.read_text())
    render = next(iter(collection["renders"].values()))
    asset = collection["assets"][render["assets"][0]]
    source = STAGING / path.parent.name / asset["href"].removeprefix("./")
    x0, y0, x1, y1 = frame(collection["extent"]["spatial"]["bbox"][0])
    target = from_bounds(x0, y0, x1, y1, WIDTH, HEIGHT)

    world_transform = from_bounds(-HALF, -HALF, HALF, HALF, world.shape[2], world.shape[1])
    base = np.zeros((3, HEIGHT, WIDTH), dtype=np.uint8)
    for band in range(3):
        reproject(world[band], base[band], src_transform=world_transform,
                  src_crs="EPSG:3857", dst_transform=target, dst_crs="EPSG:3857",
                  resampling=Resampling.bilinear)

    values = np.full((HEIGHT, WIDTH), np.nan, dtype="float32")
    with rasterio.open(source) as src:
        reproject(rasterio.band(src, 1), values, dst_transform=target,
                  dst_crs="EPSG:3857", dst_nodata=np.nan,
                  resampling=Resampling.nearest)
    overlay = colorize(values, render)

    alpha = overlay[3:4].astype("float32") / 255.0
    image = (overlay[:3] * alpha + base * (1 - alpha)).astype(np.uint8)
    fraction = float((overlay[3] > 0).mean())
    output = path.parent / "thumbnail.png"
    if fraction < MIN_DATA_FRACTION:
        print(f"FAIL: {output.relative_to(ROOT)} blank probe. {fraction:.1%} of "
              f"pixels show data, the floor is {MIN_DATA_FRACTION:.0%}")
        return 1
    Image.fromarray(image.transpose(1, 2, 0)).save(output, optimize=True)
    print(f"wrote {output.relative_to(ROOT)}: {fraction:.1%} of pixels show data")
    return 0


def main() -> int:
    world = basemap()
    failures = sum(render_one(path, world)
                   for path in sorted(CATALOG.glob("*/collection.json")))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
