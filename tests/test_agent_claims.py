#!/usr/bin/env python3
"""Every claim in a published AGENTS.md is tested.

A guide marks each claim with an HTML comment in the same block:

    <!-- check: NAME -->                   a function in CHECKS measures the COGs
    <!-- quote: SOURCE | WHERE | TEXT -->   TEXT occurs in a pinned source

A check returns the strings the block must contain, rendered from the data.
The measured values live in the data and in the prose, never in this file,
so a changed file or an edited sentence fails the gate. A check in a
collection guide reads that collection's COG. A check in the catalog guide
reads all three.

A quote names its source. `pdf | N` is page N of the technical basis PDF
file, counted from 1. The printed page labels differ by two. The PDF is
pinned by SHA-256 in tools/sources.json. `wb | FIELD` is a field of the
World Bank dataset page: `description` or `resources`.

More rules:

- Every block outside headings and fences carries a marker. A block that
  only tells the reader what to do carries <!-- guidance --> instead.
- Every number in a block's prose occurs in one of its quotes or in the
  output of one of its checks. An edited number fails the gate.
- A marker names a check that exists, and every check is used.
- Every python fence runs, and its output equals the text fence after it.

The gate reads the COGs in staging/, so run tools/build.py first. Set
CLAIMS_LIVE=1 to read the published objects instead, and to compare their
bytes with file:size and file:checksum in the STAC JSON.

Run: python3 tests/test_agent_claims.py
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from functools import cache
from pathlib import Path

import numpy as np
import rasterio
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
STAGING = ROOT / "staging"
SOURCES = json.loads((ROOT / "tools" / "sources.json").read_text())
LIVE = os.environ.get("CLAIMS_LIVE") == "1"
USER_AGENT = "wb-fwi-claims (+https://github.com/nlebovits/wb-fwi)"

sys.path.insert(0, str(ROOT / "tools"))
from publish import load_config  # noqa: E402

PUBLIC_BASE = load_config()["public_base"].rstrip("/")
RETURN_PERIODS = tuple(sorted(e["return_period"] for e in SOURCES["files"]))

MARKER = re.compile(r"<!--\s*(check|quote):\s*(.*?)\s*-->", re.S)
GUIDANCE = re.compile(r"<!--\s*guidance\s*-->")
# Vale control comments, such as <!-- vale Google.Exclamation = NO -->.
VALE = re.compile(r"<!--\s*vale\b[^>]*-->")
FENCE = re.compile(r"^```(\w*)\n(.*?)^```\s*$", re.M | re.S)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fmt(value: float) -> str:
    """A float as Python writes it, without a trailing .0."""
    return repr(float(value)).removesuffix(".0")


def periods_phrase() -> str:
    *head, last = RETURN_PERIODS
    return ", ".join(str(p) for p in head) + f", and {last}"


# --- the data ----------------------------------------------------------------

def collection_id(rp: int) -> str:
    return f"fwi-rp{rp}"


@cache
def collection(rp: int) -> dict:
    return json.loads((CATALOG / collection_id(rp) / "collection.json").read_text())


def source_entry(rp: int) -> dict:
    return next(e for e in SOURCES["files"] if e["return_period"] == rp)


def data_name(rp: int) -> str:
    return collection(rp)["assets"]["data"]["href"].removeprefix("./")


def published_url(rp: int) -> str:
    return f"{PUBLIC_BASE}/{collection_id(rp)}/{data_name(rp)}"


def location(rp: int) -> str:
    if LIVE:
        return published_url(rp)
    return str(STAGING / collection_id(rp) / data_name(rp))


@cache
def grid(rp: int) -> np.ndarray:
    with rasterio.open(location(rp)) as src:
        return src.read(1)


@cache
def profile(rp: int) -> dict:
    with rasterio.open(location(rp)) as src:
        return dict(src.profile) | {"bounds": src.bounds, "epsg": src.crs.to_epsg(),
                                    "count": src.count}


def sample(rp: int, lon: float, lat: float) -> float:
    with rasterio.open(location(rp)) as src:
        return float(next(src.sample([(lon, lat)]))[0])


def periods(rp: int | None) -> tuple[int, ...]:
    """The return periods a check reads: its own, or all three in the root."""
    return RETURN_PERIODS if rp is None else (rp,)


def needs_collection(rp: int | None, name: str) -> int:
    assert rp is not None, f"{name} belongs in a collection guide"
    return rp


# --- checks: each returns the strings its block must contain ------------------

def check_catalog_root(rp: int | None) -> list[str]:
    root = json.loads((CATALOG / "catalog.json").read_text())
    self_href = next(l["href"] for l in root["links"] if l["rel"] == "self")
    assert self_href == f"{PUBLIC_BASE}/catalog.json", self_href
    children = [l["href"] for l in root["links"] if l["rel"] == "child"]
    assert children == [f"./{collection_id(p)}/collection.json" for p in RETURN_PERIODS]
    for p in RETURN_PERIODS:
        assert profile(p)["count"] == 1, f"{collection_id(p)} has more than one band"
        assets = [a for a in collection(p)["assets"].values() if "data" in a["roles"]]
        assert len(assets) == 1, f"{collection_id(p)} has {len(assets)} data assets"
    return [f"`{self_href}`",
            f"It contains {NUMBER_WORDS[len(children)]} collections, one per return period",
            "Each collection contains one single-band COG"]


def check_collection_table(rp: int | None) -> list[str]:
    return [f"| `{collection_id(p)}` | `{data_name(p)}` | {p} years |"
            for p in RETURN_PERIODS]


def check_url_pattern(rp: int | None) -> list[str]:
    for p in RETURN_PERIODS:
        href = collection(p)["assets"]["data"]["href"]
        assert href.startswith("./") and "/" not in href[2:], href
    return [f"`{PUBLIC_BASE}/<collection>/<file>`"]


def check_collection_file(rp: int | None) -> list[str]:
    rp = needs_collection(rp, "collection_file")
    assert data_name(rp) == source_entry(rp)["name"]
    return [f"`{data_name(rp)}`", f"`{published_url(rp)}`",
            f"expected once in {rp} years"]


def check_same_grid(rp: int | None) -> list[str]:
    seen = {(profile(p)["epsg"], profile(p)["width"], profile(p)["height"],
             tuple(profile(p)["transform"])) for p in RETURN_PERIODS}
    assert len(seen) == 1, f"the COGs use {len(seen)} grids"
    return [f"The {NUMBER_WORDS[len(RETURN_PERIODS)]} COGs share one grid"]


def check_grid_shape(rp: int | None) -> list[str]:
    p = profile(needs_collection(rp, "grid_shape"))
    resolution = p["transform"].a
    assert resolution == -p["transform"].e, "cells are not square"
    return [f"EPSG:{p['epsg']}", f"{p['width']} columns by {p['height']} rows",
            f"{fmt(resolution)}° cells"]


def check_grid_bounds(rp: int | None) -> list[str]:
    b = profile(needs_collection(rp, "grid_bounds"))["bounds"]
    return [f"from longitude {fmt(b.left)} to {fmt(b.right)} "
            f"and from latitude {fmt(b.bottom)} to {fmt(b.top)}"]


def check_grid_west_edge(rp: int | None) -> list[str]:
    west = {profile(p)["bounds"].left for p in RETURN_PERIODS}
    assert len(west) == 1 and min(west) < -180, f"west edges {west}"
    return [f"starts at longitude {fmt(west.pop())}, west of the antimeridian"]


def check_grid_resolution(rp: int | None) -> list[str]:
    return [f"{fmt(profile(RETURN_PERIODS[0])['transform'].a)}° grid"]


def check_dtype(rp: int | None) -> list[str]:
    return [f"Data type {profile(needs_collection(rp, 'dtype'))['dtype'].capitalize()}"]


def check_zero_share(rp: int | None) -> list[str]:
    rp = needs_collection(rp, "zero_share")
    return [f"{100 * (grid(rp) == 0).mean():.2f}% of the cells hold 0"]


def check_nonzero_quantiles(rp: int | None) -> list[str]:
    values = grid(needs_collection(rp, "nonzero_quantiles"))
    values = values[values > 0].astype("float64")
    median, p99 = np.percentile(values, [50, 99])
    return [f"{values.size} cells hold a value above 0",
            f"Their median is {median:.2f}", f"their ninety-ninth percentile is {p99:.2f}"]


def check_cap_one(rp: int | None) -> list[str]:
    values = grid(needs_collection(rp, "cap_one"))
    top = float(values.max())
    count = int((values == top).sum())
    noun = "cell holds" if count == 1 else "cells hold"
    return [f"The maximum is exactly {top!r}", f"{count} {noun} it"]


def check_masked_zero(rp: int | None) -> list[str]:
    # Mid-Pacific, central Sahara, and central Greenland: water, arid, and ice.
    for lon, lat in ((-150.0, 0.0), (10.0, 23.0), (-40.0, 72.0)):
        values = [sample(p, lon, lat) for p in RETURN_PERIODS]
        assert values == [0] * len(values), f"{lon}, {lat} is not 0: {values}"
    return ["Those cells hold 0",
            "Zero marks masked cells in the mid-Pacific, the central Sahara, "
            "and central Greenland", "pulls every mean toward 0"]


def check_sydney_cells(rp: int | None) -> list[str]:
    for lon, lat in ((151.2, -33.9), (150.7, -33.75)):
        values = [sample(p, lon, lat) for p in RETURN_PERIODS]
        assert values == [0] * len(values), f"{lon}, {lat} is not masked: {values}"
    inland = [f"{sample(p, 150.3, -33.7):.2f}" for p in RETURN_PERIODS]
    resolution = fmt(profile(RETURN_PERIODS[0])["transform"].a)
    return [f"A {resolution}° cell that is mostly sea holds 0",
            "151.2°E 33.9°S and 150.7°E 33.75°S", "return 0 in all three files",
            "150.3°E 33.7°S", f"{inland[0]}, {inland[1]}, and {inland[2]}"]


def check_nodata_unused(rp: int | None) -> list[str]:
    declared = {profile(p)["nodata"] for p in RETURN_PERIODS}
    assert len(declared) == 1, f"the files declare {declared}"
    nodata = declared.pop()
    for p in RETURN_PERIODS:
        assert not (grid(p) == np.float32(nodata)).any(), f"rp{p} holds nodata"
    return [f"nodata {nodata!r}", "no cell holds it"]


def check_cap_300(rp: int | None) -> list[str]:
    tops = {float(grid(p).max()) for p in RETURN_PERIODS}
    assert len(tops) == 1, f"the maximum differs by file: {tops}"
    top = tops.pop()
    counts = [str(int((grid(p) == top).sum())) for p in RETURN_PERIODS]
    *head, last = counts
    return [f"Values stop at {top!r}", f"exactly {top!r}",
            ", ".join(head) + f", and {last} cells hold {top!r}",
            f"in the {periods_phrase()}-year files", f"Treat {top!r} as a lower bound"]


def check_non_monotonic(rp: int | None) -> list[str]:
    out = []
    for low, high in ((2, 10), (10, 30), (2, 30)):
        n = int((grid(high) < grid(low)).sum())
        noun = "cell is" if n == 1 else "cells are"
        out.append(f"{n} {noun} lower at {high} years than at {low} years")
    return out


def check_render_ramp(rp: int | None) -> list[str]:
    for p in RETURN_PERIODS:
        renders = list(collection(p)["renders"].values())
        assert len(renders) == 1, f"{collection_id(p)} has {len(renders)} renders"
        render = renders[0]
        assert render["assets"] == ["data"], render["assets"]
        assert render["nodata"] == 0, "the render draws the masked cells"
        assert render["colormap_name"] == "rdylgn", render["colormap_name"]
        assert "colormap" not in render, "the render also sets a colormap"
        low, high = render["rescale"][0]
    return [f"green at FWI {fmt(high)} to red at FWI {fmt(low)}"]


def check_self_links(rp: int | None) -> list[str]:
    for path in sorted(CATALOG.rglob("*.json")):
        document = json.loads(path.read_text())
        rel = path.relative_to(CATALOG).as_posix()
        hrefs = [l["href"] for l in document.get("links", []) if l["rel"] == "self"]
        assert hrefs == [f"{PUBLIC_BASE}/{rel}"], f"{rel} self link is {hrefs}"
    for p in RETURN_PERIODS:
        assert not any(l["rel"] == "item" for l in collection(p)["links"])
    return ["carry a `self` link to their published URL",
            "stores its COG as a collection-level asset, with no items"]


# Table 3 of the technical basis, PDF page 17. check_hazard_table proves each
# row against the PDF, the guide's table, and the guide's recipe.
HAZARD_RULES = (
    ("High", 30, 2, "high", ""),
    ("Medium", 20, 10, "medium", ", and not High"),
    ("Low", 15, 30, "low", ", and not Medium or High"),
    ("Very Low", 0, 30, "very low", ", and no higher class"),
)


def check_hazard_table(rp: int | None) -> list[str]:
    page = pdf_pages()[17 - 1]
    guide = (CATALOG / "AGENTS.md").read_text()
    rows = []
    for label, fwi, period, name, rest in HAZARD_RULES:
        source = f"FWI > {fwi} for an RPI of 1:{period} years"
        assert source in page, f"PDF page 17 lacks {source!r}"
        code = f'hazard[fwi[{period}] > {fwi}] = "{name}"'
        assert code in guide, f"the recipe lacks {code!r}"
        rows.append(f"| {label} | FWI > {fwi} at {period} years{rest} |")
    return rows


CHECKS = {name.removeprefix("check_"): fn
          for name, fn in globals().items() if name.startswith("check_")}


# --- quotes ------------------------------------------------------------------

@cache
def pdf_pages() -> list[str]:
    entry = SOURCES["documents"][0]
    cached = ROOT / "sources" / entry["name"]
    body = cached.read_bytes() if cached.exists() else fetch(entry["url"])
    digest = hashlib.sha256(body).hexdigest()
    assert digest == entry["sha256"], f"the PDF changed upstream: {digest}"
    return [normalize(page.extract_text() or "")
            for page in PdfReader(io.BytesIO(body)).pages]


@cache
def wb_fields() -> dict[str, str]:
    page = fetch(SOURCES["dataset_page"]).decode()
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    dataset = json.loads(match.group(1))["props"]["pageProps"]["dataset"]

    def strip(text: str | None) -> str:
        return normalize(re.sub(r"<[^>]+>", " ", html.unescape(text or "")))

    return {
        "description": strip(dataset["identification"]["description"]),
        "resources": " ".join(strip(r.get("description")) for r in dataset["Resources"]),
    }


def verify_quote(spec: str) -> str | None:
    parts = [p.strip() for p in spec.split("|", 2)]
    if len(parts) != 3:
        return f"malformed quote marker: {spec!r}"
    source, where, text = parts
    text = normalize(text)
    if source == "pdf":
        pages = pdf_pages()
        number = int(where)
        if not 1 <= number <= len(pages):
            return f"the PDF has no page {number}"
        if text not in pages[number - 1]:
            found = [i + 1 for i, page in enumerate(pages) if text in page]
            return (f"PDF page {number} lacks {text!r}"
                    + (f". It is on page {found}" if found else ""))
        return None
    if source == "wb":
        fields = wb_fields()
        if where not in fields:
            return f"unknown World Bank field {where!r}"
        if text not in fields[where]:
            return f"World Bank {where} lacks {text!r}"
        return None
    return f"unknown quote source {source!r}"


# --- the guide ---------------------------------------------------------------

def guide_period(path: Path) -> int | None:
    """The return period of a collection guide, or None for the catalog guide."""
    match = re.fullmatch(r"fwi-rp(\d+)", path.parent.name)
    return int(match.group(1)) if match else None


def blocks(text: str) -> list[tuple[int, str]]:
    """Blocks separated by blank lines, outside fences, with line numbers."""
    stripped = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out, start, lines = [], 0, []
    for number, line in enumerate(stripped.split("\n"), 1):
        if line.strip():
            if not lines:
                start = number
            lines.append(line)
        elif lines:
            out.append((start, "\n".join(lines)))
            lines = []
    if lines:
        out.append((start, "\n".join(lines)))
    return out


def prose_of(block: str) -> str:
    """The block without markers, inline code, link targets, and headings."""
    text = GUIDANCE.sub("", MARKER.sub("", block))
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"`[^`]*`", "", text)
    return "\n".join(line for line in text.split("\n") if not line.startswith("#"))


def expected_heading(rp: int | None) -> str:
    """A guide's first heading names the object it describes."""
    if rp is None:
        title = json.loads((CATALOG / "catalog.json").read_text())["title"]
    else:
        title = collection(rp)["title"]
    return f"# {title}"


def check_guide(path: Path, used: set[str], rp: int | None = None) -> list[str]:
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    errors = []
    first = path.read_text().split("\n", 1)[0]
    if first != expected_heading(rp):
        errors.append(f"{rel}:1: the heading is {first!r}, "
                      f"the STAC title gives {expected_heading(rp)!r}")
    for line, block in blocks(path.read_text()):
        block = VALE.sub("", block).strip()
        if not block or all(row.startswith("#") for row in block.split("\n")):
            continue
        markers = MARKER.findall(block)
        body = normalize(GUIDANCE.sub("", MARKER.sub("", block)))
        guidance = bool(GUIDANCE.search(block))
        if not markers and not guidance:
            errors.append(f"{rel}:{line}: a block with no marker: {body[:80]!r}")
            continue
        backing = []
        for kind, spec in markers:
            if kind == "quote":
                backing.append(spec.split("|", 2)[-1])
                problem = verify_quote(spec)
                if problem:
                    errors.append(f"{rel}:{line}: {problem}")
                continue
            if spec not in CHECKS:
                errors.append(f"{rel}:{line}: no check named {spec!r}")
                continue
            used.add(spec)
            try:
                expected = CHECKS[spec](rp)
            except AssertionError as exc:
                errors.append(f"{rel}:{line}: check {spec} fails: {exc}")
                continue
            backing += expected
            for phrase in expected:
                if normalize(phrase) not in body:
                    errors.append(f"{rel}:{line}: check {spec}: the data says "
                                  f"{phrase!r}, the guide does not")
        known = set(NUMBER.findall(" ".join(backing)))
        loose = [n for n in NUMBER.findall(prose_of(block)) if n not in known]
        if loose and not markers:
            errors.append(f"{rel}:{line}: a guidance block states numbers {loose}")
        elif loose:
            errors.append(f"{rel}:{line}: no marker backs the numbers {loose}")
    return errors


def run_recipes(path: Path) -> list[str]:
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    text = path.read_text()
    fences = list(FENCE.finditer(text))
    errors = []
    for index, fence in enumerate(fences):
        if fence.group(1) != "python":
            continue
        line = text.count("\n", 0, fence.start()) + 1
        following = fences[index + 1] if index + 1 < len(fences) else None
        if not following or following.group(1) != "text":
            errors.append(f"{rel}:{line}: a recipe with no expected output fence")
            continue
        code = fence.group(2)
        if not LIVE:
            code = code.replace(f'"{PUBLIC_BASE}', f'"{STAGING}')
        with tempfile.TemporaryDirectory() as scratch:
            result = subprocess.run([sys.executable, "-I", "-c", code],
                                    capture_output=True, text=True, cwd=scratch,
                                    timeout=600)
        if result.returncode != 0:
            errors.append(f"{rel}:{line}: the recipe fails:\n{result.stderr.strip()}")
        elif result.stdout.strip() != following.group(2).strip():
            errors.append(f"{rel}:{line}: the recipe prints\n{result.stdout.strip()}\n"
                          f"the guide shows\n{following.group(2).strip()}")
    return errors


def check_live_bytes() -> list[str]:
    """Each published COG matches file:size and file:checksum in its collection."""
    errors = []
    for p in RETURN_PERIODS:
        asset = collection(p)["assets"]["data"]
        body = fetch(published_url(p))
        digest = "1220" + hashlib.sha256(body).hexdigest()
        if digest != asset["file:checksum"] or len(body) != asset["file:size"]:
            errors.append(f"{collection_id(p)}: the published COG differs from the STAC JSON")
    return errors


def guides() -> list[Path]:
    found = [CATALOG / "AGENTS.md"]
    found += [CATALOG / collection_id(p) / "AGENTS.md" for p in RETURN_PERIODS]
    missing = [str(p.relative_to(ROOT)) for p in found if not p.is_file()]
    assert not missing, f"missing agent guides: {missing}"
    return found


def main() -> int:
    if not LIVE and not all((STAGING / collection_id(p)).is_dir() for p in RETURN_PERIODS):
        print("FAIL: staging/ is empty. Run python3 tools/build.py first.")
        return 1
    used: set[str] = set()
    errors = []
    for guide in guides():
        errors += check_guide(guide, used, guide_period(guide))
        errors += run_recipes(guide)
    unused = sorted(set(CHECKS) - used)
    if unused:
        errors.append(f"checks that no guide uses: {', '.join(unused)}")
    if LIVE:
        errors += check_live_bytes()
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        return 1
    mode = "published objects" if LIVE else "staged COGs"
    print(f"PASS: {len(guides())} guides, {len(used)} checks, against the {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
