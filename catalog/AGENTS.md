# World Bank global wildfire hazard
<!-- vale Google.Exclamation = NO -->
<!-- vale Microsoft.Negative = NO -->

Read this before you query the catalog. The facts here come from a source
or from the published COGs. The HTML comment beside each fact identifies the
CI check that tests it, in
[tests/test_agent_claims.py](https://github.com/nlebovits/wb-fwi/blob/main/tests/test_agent_claims.py).
<!-- guidance -->

## Contents

The catalog root is `https://data.source.coop/portolan-mirrors/wb-fwi/catalog.json`.
It contains three collections, one per return period. Each collection
contains one single-band COG. <!-- check: catalog_root -->

| Collection | File | Return period |
|---|---|---|
| `fwi-rp2` | `csiro_wf_max_fwi_rp2.tif` | 2 years |
| `fwi-rp10` | `csiro_wf_max_fwi_rp10.tif` | 10 years |
| `fwi-rp30` | `csiro_wf_max_fwi_rp30.tif` | 30 years |
<!-- check: collection_table -->

The URL pattern is
`https://data.source.coop/portolan-mirrors/wb-fwi/<collection>/<file>`.
<!-- check: url_pattern -->

Each cell stores the yearly maximum Fire Weather Index (FWI) at noon local time that is
expected once in the return period.
<!-- quote: pdf | 13 | Modelled yearly maximum 12 noon FWI for return period intervals of 2, 10 and 30 years -->
<!-- quote: pdf | 10 | daily FWI calculations for 12 noon local time -->

CSIRO fit a GEV distribution to the annual maxima of daily FWI from GFWED,
from January 1, 1981 to December 31, 2016.
<!-- quote: pdf | 10 | January 1st 1981 to December 31st 2016 -->
<!-- quote: pdf | 11 | The annual extreme of FWI, denoted by x, is assumed to follow the GEV distribution -->

FWI has no unit. Read it against the thresholds below, not as a physical
quantity.
<!-- quote: pdf | 9 | has no inherent units associated with it -->

## Joins

The three COGs share one grid, so a cell index in one file is the same cell
in the others. Read them as three layers of one array.
<!-- check: same_grid -->

## Quirks that produce wrong answers

**Zero means masked or no fire weather.** GFWED masks large water bodies and
arid regions with no vegetation. Those cells hold 0, and the files declare
no other marker for them. <!-- quote: pdf | 10 | Data were masked (by the GFWED) for significant water bodies and arid regions with no -->
Zero marks masked cells in the mid-Pacific, the central Sahara, and central
Greenland. Exclude zeros before you average, or the ocean pulls every mean
toward 0. <!-- check: masked_zero -->

**Coastal cells are often masked.** A 0.5° cell that is mostly sea holds 0.
The Sydney sample points 151.2°E 33.9°S and 150.7°E 33.75°S
return 0 in all three files. The point 150.3°E 33.7°S, further inland, returns 47.27,
60.07, and 64.76. <!-- check: sydney_cells -->
Sample a land cell nearby, or aggregate over an area, before you report 0 for
a coastal place.

**The declared nodata value never occurs.** Each file declares nodata
-3.4028230607370965e+38, and no cell holds it. <!-- check: nodata_unused -->

**Values stop at 300.0.** The maximum in each file is exactly 300.0. 1, 23,
and 34 cells hold 300.0 in the 2, 10, and 30-year files. <!-- check: cap_300 -->
The technical basis does not explain the cap. Treat 300.0 as a lower bound.

**A few cells decrease with the return period.** A longer return period
should give a value at least as high. 1 cell is lower at 10 years than at 2
years. 69 cells are lower at 30 years than at 10 years. 18 cells are lower at
30 years than at 2 years. <!-- check: non_monotonic -->

**The catalog page summary lists the wrong return periods.** The World Bank
dataset summary says 2, 5 and 30 years. <!-- quote: wb | description | for three return period scenarios: once in 2, 5 and 30 years -->
The files and the resource descriptions say 2, 10, and 30 years.
<!-- quote: wb | resources | for return period of once in 10 years -->

**The grid edge confuses some map clients.** The grid starts at longitude
-180.3125, west of the antimeridian. The Portolan data browser draws the COGs
shifted and stretched, as the
[browser issue](https://github.com/portolan-sdi/portolan-browser/issues/78)
records. The bytes are correct. Read them with GDAL or rasterio
for analysis. <!-- check: grid_west_edge -->

## Hazard thresholds

ThinkHazard! classifies wildfire hazard by combining the three return
periods. The thresholds come from Table 3 of the technical basis.
<!-- quote: pdf | 17 | Table 3 Mapping of frequency (RPI) and intensity (FWI) to generate final ThinkHazard! wildfire categories -->

| Class | Rule |
|---|---|
| High | FWI > 30 at 2 years |
| Medium | FWI > 20 at 10 years, and not High |
| Low | FWI > 15 at 30 years, and not Medium or High |
| Very Low | FWI > 0 at 30 years, and no higher class |
<!-- check: hazard_table -->

ThinkHazard! reports a class per administrative unit. This catalog holds the
grids, not the per-unit classes.
<!-- quote: pdf | 8 | the scale of administrative units used in ThinkHazard! -->

The browser colors run from green at FWI 0 to red at FWI 50 and above, the
color scale of Figure 4 in the technical basis. The colors show the FWI value,
not the hazard classes. <!-- check: render_ramp -->
<!-- quote: pdf | 13 | Figure 4: Modelled yearly maximum 12 noon FWI for return period intervals of 2, 10 and 30 years. FWI is colour coded from green (FWI = 0) to red (FWI = 50). -->

## Recipes

Each recipe runs in CI against the COGs. Its printed output must equal the
block that follows it. Install `rasterio` and `numpy` first.
<!-- guidance -->

Classify every cell with the Table 3 rules, then count the cells per class:
<!-- quote: pdf | 17 | The final integrated intensity and frequency classes are specified in Table 3 -->

```python
import numpy as np
import rasterio

BASE = "https://data.source.coop/portolan-mirrors/wb-fwi"
fwi = {}
for rp in (2, 10, 30):
    url = f"{BASE}/fwi-rp{rp}/csiro_wf_max_fwi_rp{rp}.tif"
    with rasterio.open(url) as src:
        fwi[rp] = src.read(1)

hazard = np.full(fwi[2].shape, "masked", dtype=object)
hazard[fwi[30] > 0] = "very low"
hazard[fwi[30] > 15] = "low"
hazard[fwi[10] > 20] = "medium"
hazard[fwi[2] > 30] = "high"
for name in ("high", "medium", "low", "very low", "masked"):
    print(name, int((hazard == name).sum()))
```

```text
high 28379
medium 10216
low 7365
very low 7733
masked 138547
```

These are cell counts on a 0.5° grid. Cells near the poles cover less area
than cells near the equator, so do not read the counts as land area.
<!-- check: grid_resolution -->

## Structure

Each collection stores its COG as a collection-level asset, with no items.
Assets and structural links resolve relative to the object that carries
them. The catalog and each collection carry a `self` link to their
published URL. <!-- check: self_links -->
