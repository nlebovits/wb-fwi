# AGENTS.md: Wildfire Hazard: FWI, 2-Year Return Period

Read the [catalog guide](../AGENTS.md) first. It lists the quirks that all
three files share, the hazard thresholds, and a recipe that combines the
return periods. Every fact below is measured from this collection's COG, and
the HTML comment beside it names the CI check that tests it.
<!-- guidance -->

## The file

The `data` asset is `csiro_wf_max_fwi_rp2.tif`, at
`https://data.source.coop/portolan-mirrors/wb-fwi/fwi-rp2/csiro_wf_max_fwi_rp2.tif`.
Each cell holds the yearly maximum 12 noon FWI expected once in 2 years.
<!-- check: collection_file -->
<!-- quote: pdf | 13 | Modelled yearly maximum 12 noon FWI for return period intervals -->

## The grid

- CRS EPSG:4326, 720 columns by 267 rows, 0.5° cells. <!-- check: grid_shape -->
- The grid runs from longitude -180.3125 to 179.6875 and from latitude -58.25
  to 75.25. <!-- check: grid_bounds -->
- Data type Float32. <!-- check: dtype -->

## The values

72.07% of the cells hold 0. Those cells are masked, or they have no fire
weather. <!-- check: zero_share -->

53694 cells hold a value above 0. Their median is 33.98, and their 99th percentile
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
