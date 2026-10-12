# Wildfire hazard: FWI, 2-year return period
<!-- vale Google.Exclamation = NO -->
<!-- vale Microsoft.Negative = NO -->

Read the [catalog guide](../AGENTS.md) first. It lists the quirks that all
three files share, the hazard thresholds, and a recipe that combines the
return periods. The facts below come from this collection's COG. The HTML
comment beside each fact identifies the CI check that tests it.
<!-- guidance -->

## The file

The `data` asset is `csiro_wf_max_fwi_rp2.tif`, at
`https://data.source.coop/portolan-mirrors/wb-fwi/fwi-rp2/csiro_wf_max_fwi_rp2.tif`.
Each cell stores the yearly maximum FWI at noon local time expected once in 2 years.
<!-- check: collection_file -->
<!-- quote: pdf | 13 | Modelled yearly maximum 12 noon FWI for return period intervals -->
<!-- quote: pdf | 10 | daily FWI calculations for 12 noon local time -->

## The grid

- CRS EPSG:4326, 720 columns by 267 rows, 0.5° cells. <!-- check: grid_shape -->
- The grid runs from longitude -180.3125 to 179.6875 and from latitude -58.25
  to 75.25. <!-- check: grid_bounds -->
- Data type Float32. <!-- check: dtype -->

## The values

72.07% of the cells hold 0. Those cells are masked, or they have no fire
weather. <!-- check: zero_share -->

53694 cells hold a value above 0. Their median is 33.98, and their ninety-ninth percentile
is 165.11. <!-- check: nonzero_quantiles -->

The maximum is exactly 300.0, and 1 cell holds it. <!-- check: cap_one -->

## Recipe

This recipe runs in CI against the COG. Its printed output must equal the
block that follows it. Install `rasterio` first.
<!-- guidance -->

```python
import rasterio

URL = ("https://data.source.coop/portolan-mirrors/wb-fwi"
       "/fwi-rp2/csiro_wf_max_fwi_rp2.tif")
with rasterio.open(URL) as src:
    value = next(src.sample([(150.3, -33.7)]))[0]
print(round(float(value), 2))
```

```text
47.27
```
