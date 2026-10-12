# World Bank global wildfire hazard, as a Portolan catalog

<!-- vale Google.Exclamation = NO -->
<!-- vale Microsoft.Negative = NO -->

This repository builds and maintains a [Portolan](https://www.portolan-sdi.org/)
mirror of the World Bank's
[global wildfire hazard](https://datacatalog.worldbank.org/search/dataset/0066912/global-wildfire-hazard)
dataset. CSIRO computed the data for the ThinkHazard! wildfire layer. Each
grid gives the yearly maximum Fire Weather Index at noon local time that is
expected once in 2, 10, or 30 years, on a global 0.5° grid.

The published catalog is at
[source.coop/portolan-mirrors/wb-fwi](https://source.coop/portolan-mirrors/wb-fwi).
Open it in the
[data browser](https://browser.portolan-sdi.org/#/external/data.source.coop/portolan-mirrors/wb-fwi/catalog.json),
or read a COG directly with GDAL or rasterio:

```python
import rasterio

URL = ("https://data.source.coop/portolan-mirrors/wb-fwi"
       "/fwi-rp2/csiro_wf_max_fwi_rp2.tif")
with rasterio.open(URL) as src:
    print(next(src.sample([(150.3, -33.7)]))[0])
```

Read the [catalog agent guide](catalog/AGENTS.md) before you analyze the data.
A value of 0 marks oceans and deserts that the source masks, as well as land
with no fire weather. The grid's west edge sits at -180.3125, and the data
browser draws it out of place until
[portolan-browser#78](https://github.com/portolan-sdi/portolan-browser/issues/78)
is fixed.

## Build

Data never enters git. `tools/build.py` downloads the World Bank GeoTIFFs,
which `tools/sources.json` pins by SHA-256, and converts each one to a COG in
`staging/`. The script then writes sizes, checksums, band statistics, and
extents into the STAC JSON under `catalog/`. The other STAC fields and the
documentation are hand-written.

```bash
python -m pip install -r requirements-ci.txt
python3 tools/build.py
```

When a collection's render changes, run `tools/thumbnail.py` first and look
at the new images before you commit them.

## Documentation tests

Each claim in a published `AGENTS.md` sits beside an HTML comment that names
its test. A check measures the COGs, and a quote must match the technical
basis PDF or the World Bank page word for word. Because every number in the
guides must come from one of those tests, an edited number fails CI. The
mutation test proves this by changing each number, one at a time.

```bash
python3 tools/build.py --check
CI_LIGHT=1 python3 tests/run_all.py
```

`tests/run_all.py` also runs the template gates for links, the publish
boundary, STAC validity, and Portolan conformance through `rashid`. Each week,
the [live claims](.github/workflows/live-claims.yml) workflow repeats the
claims gate against the published objects.

## Publishing

`catalog.publish.yaml` sends the catalog to the `portolan-mirrors` account on
Source Cooperative through the `source-coop-proxy` AWS profile. That profile
reads temporary credentials from the
[source-coop CLI](https://github.com/source-cooperative/source-coop-cli).

```bash
source-coop login
python3 tools/upload_data.py --confirm
python3 tools/publish.py --confirm
```

Without `--confirm`, both scripts print what they would upload. Neither
script deletes an object.

## License

Apache-2.0 covers the code in this repository. The data is
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Attribute the World
Bank and CSIRO when you reuse it.
