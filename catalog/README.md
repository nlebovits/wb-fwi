# World Bank Global Wildfire Hazard

A Portolan mirror of the World Bank's
[global wildfire hazard](https://datacatalog.worldbank.org/search/dataset/0066912/global-wildfire-hazard)
dataset, published as cloud-optimized GeoTIFFs.

## What is here

Three collections, one per return period:
[2 years](fwi-rp2/README.md), [10 years](fwi-rp10/README.md), and
[30 years](fwi-rp30/README.md). Each holds the yearly maximum Fire Weather
Index (FWI) expected once in that period, on a global 0.5° grid.
[CSIRO](https://www.csiro.au/) computed the grids for the
[ThinkHazard!](https://thinkhazard.org/) wildfire layer, from daily FWI in
NASA's [Global Fire Weather Database](https://data.giss.nasa.gov/impacts/gfwed/)
for 1981 to 2016.

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as the World Bank
Data Catalog lists it. Attribute the World Bank and CSIRO when you reuse the
data.

## Provenance

This catalog is a mirror, not the official publication. The World Bank
publishes the original GeoTIFFs and the technical basis PDF. The World Bank
lists the dataset as "No further updates planned". The mirror converts each
GeoTIFF to a COG with embedded statistics and leaves every pixel value
unchanged. The build is in
[nlebovits/wb-fwi](https://github.com/nlebovits/wb-fwi). It pins each source
file by SHA-256, so a changed upstream file stops the build.

## Access

Read the 2-year return level at one point with
[rasterio](https://rasterio.readthedocs.io/):

```python
import rasterio

URL = ("https://data.source.coop/portolan-mirrors/wb-fwi"
       "/fwi-rp2/csiro_wf_max_fwi_rp2.tif")
with rasterio.open(URL) as src:
    print(next(src.sample([(150.3, -33.7)]))[0])
```

Read the [agent guide](AGENTS.md) before you query. It lists the quirks that
produce wrong answers. One example: 0 marks masked oceans and deserts as well
as cells with no fire weather.
