#!/usr/bin/env python3
"""Fetch the World Bank FWI rasters, write COGs, and refresh the STAC fields
that describe the bytes.

    python3 tools/build.py            # fetch, convert, and rewrite the STAC JSON
    python3 tools/build.py --check    # fail when the STAC JSON disagrees with the COGs

The sources are pinned by SHA-256 in tools/sources.json. A changed upstream
file stops the build. Each COG goes to staging/<collection>/, which
tools/upload_data.py uploads and git ignores.

Each return period is one collection with one collection-level COG
(PORTO-CORE-072). The build owns only the measured fields: file:size and
file:checksum, bands, the proj fields, and the spatial extent. Every other
field in the STAC JSON is written by hand. Run tools/thumbnail.py before the
build when a thumbnail changes.

--check compares every measured field except the byte fields of the COGs,
because a different GDAL version writes different bytes for the same pixels.
CLAIMS_LIVE=1 python3 tests/test_agent_claims.py compares those byte fields
with the published objects instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.shutil import copy as rio_copy

ROOT = Path(__file__).resolve().parent.parent
SOURCES = json.loads((ROOT / "tools" / "sources.json").read_text())
SOURCE_DIR = ROOT / "sources"
STAGING = ROOT / "staging"
CATALOG = ROOT / "catalog"
COG_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"

# DEFLATE with the floating-point predictor suits a Float32 grid. NEAREST
# overviews keep every overview value equal to a value in the full grid.
COG_OPTIONS = {
    "compress": "DEFLATE",
    "predictor": 3,
    "level": 9,
    "blocksize": 256,
    "overview_resampling": "NEAREST",
}

# The grid is global and its west edge sits at -180.3125. A STAC bbox is
# WGS84 longitude, so it is clipped to the antimeridian.
LON_LIMIT = 180.0


def collection_id(entry: dict) -> str:
    return f"fwi-rp{entry['return_period']}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(entry: dict) -> Path:
    """Download one pinned source file, or reuse a verified copy."""
    SOURCE_DIR.mkdir(exist_ok=True)
    path = SOURCE_DIR / entry["name"]
    if not path.exists() or sha256(path) != entry["sha256"]:
        print(f"fetch {entry['url']}")
        request = urllib.request.Request(
            entry["url"], headers={"User-Agent": "wb-fwi-build"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    actual = sha256(path)
    if actual != entry["sha256"]:
        sys.exit(
            f"FAIL: {entry['name']} sha256 is {actual}, "
            f"tools/sources.json pins {entry['sha256']}. Upstream changed."
        )
    return path


def statistics(band: np.ndarray, nodata: float | None) -> dict:
    """Statistics over the valid pixels, as GDAL and STAC both name them."""
    valid = np.isfinite(band)
    if nodata is not None:
        valid &= band != np.float32(nodata)
    values = band[valid].astype("float64")
    return {
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "mean": round(float(values.mean()), 6),
        "stddev": round(float(values.std()), 6),
        "valid_percent": round(100.0 * values.size / band.size, 4),
    }


def convert(source: Path, target: Path) -> None:
    """Write a COG with the band statistics embedded (PORTO-FMT-026/027)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source) as src:
        band = src.read(1)
        stats = statistics(band, src.nodata)
        profile = src.profile.copy()
        profile.update(driver="GTiff", tiled=False, compress=None)
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
        with MemoryFile() as memory:
            with memory.open(**profile) as tmp:
                tmp.write(band, 1)
                tmp.update_tags(
                    1,
                    STATISTICS_MINIMUM=repr(stats["minimum"]),
                    STATISTICS_MAXIMUM=repr(stats["maximum"]),
                    STATISTICS_MEAN=repr(stats["mean"]),
                    STATISTICS_STDDEV=repr(stats["stddev"]),
                    STATISTICS_VALID_PERCENT=repr(stats["valid_percent"]),
                )
            with memory.open() as tmp:
                rio_copy(tmp, target, driver="COG", **COG_OPTIONS)


def file_fields(path: Path) -> dict:
    return {"file:size": path.stat().st_size, "file:checksum": "1220" + sha256(path)}


def pinned(entry: dict) -> dict:
    return {"file:size": entry["size"], "file:checksum": "1220" + entry["sha256"]}


def measure(path: Path) -> dict:
    """Every field the STAC JSON states about one COG."""
    with rasterio.open(path) as src:
        band = src.read(1)
        transform = src.transform
        return {
            **file_fields(path),
            "proj:code": f"EPSG:{src.crs.to_epsg()}",
            "proj:shape": [src.height, src.width],
            "proj:transform": [transform.a, transform.b, transform.c,
                               transform.d, transform.e, transform.f],
            "bands": [{
                "data_type": src.dtypes[0],
                "nodata": src.nodata,
                "statistics": statistics(band, src.nodata),
                "raster:spatial_resolution": transform.a,
            }],
            "bounds": list(src.bounds),
        }


def stac_bbox(bounds: list[float]) -> list[float]:
    """Clip to WGS84 longitude. A grid 360° wide covers every longitude,
    because the strip west of -180 is the strip east of 179.6875."""
    west, south, east, north = bounds
    if east - west >= 2 * LON_LIMIT:
        return [-LON_LIMIT, south, LON_LIMIT, north]
    return [max(west, -LON_LIMIT), south, min(east, LON_LIMIT), north]


def apply(path: Path, entry: dict, fields: dict) -> dict:
    """The collection with the measured fields replaced."""
    collection = json.loads(path.read_text())
    assets = collection["assets"]
    data = assets["data"]
    if data["href"] != f"./{entry['name']}":
        sys.exit(f"FAIL: {path} data href is {data['href']}, not ./{entry['name']}")
    for key in ("file:size", "file:checksum", "proj:code", "proj:shape",
                "proj:transform", "bands"):
        data[key] = fields[key]
    if assets["source"]["href"] != entry["url"]:
        sys.exit(f"FAIL: {path} source href is not {entry['url']}")
    assets["source"].update(pinned(entry))
    for document in SOURCES["documents"]:
        asset = next(a for a in assets.values() if a["href"] == document["url"])
        asset.update(pinned(document))
    thumbnail = path.parent / "thumbnail.png"
    if thumbnail.exists():
        assets["thumbnail"].update(file_fields(thumbnail))
    collection["extent"]["spatial"]["bbox"] = [stac_bbox(fields["bounds"])]
    return collection


def comparable(document: dict) -> str:
    """The document without the byte fields of the COG. GDAL writes different
    bytes for the same pixels in different versions."""
    copy = json.loads(json.dumps(document))
    for asset in copy.get("assets", {}).values():
        if asset.get("type") == COG_TYPE:
            asset.pop("file:size", None)
            asset.pop("file:checksum", None)
    return json.dumps(copy, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="fail when the STAC JSON disagrees with the COGs")
    args = parser.parse_args()

    stale = []
    for entry in SOURCES["files"]:
        cid = collection_id(entry)
        target = STAGING / cid / entry["name"]
        convert(fetch(entry), target)
        print(f"built {target.relative_to(ROOT)}")
        path = CATALOG / cid / "collection.json"
        collection = apply(path, entry, measure(target))
        if args.check:
            if comparable(json.loads(path.read_text())) != comparable(collection):
                stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n")

    if args.check:
        if stale:
            print("FAIL: run python3 tools/build.py. Stale: " + ", ".join(stale))
            return 1
        print("PASS: the STAC JSON matches the built COGs")
        return 0
    print("wrote the measured fields into the STAC JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
