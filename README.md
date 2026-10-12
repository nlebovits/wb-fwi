# wb-fwi

A git-backed [Portolan](https://www.portolan-sdi.org/) mirror of the World
Bank [global wildfire hazard](https://datacatalog.worldbank.org/search/dataset/0066912/global-wildfire-hazard)
dataset. It holds Fire Weather Index return levels for 2, 10, and 30 years on
a global 0.5° grid, as cloud-optimized GeoTIFFs.

- Catalog: [source.coop/portolan-mirrors/wb-fwi](https://source.coop/portolan-mirrors/wb-fwi)
- Data browser: [browser.portolan-sdi.org](https://browser.portolan-sdi.org/#/external/data.source.coop/portolan-mirrors/wb-fwi/catalog.json)
- Proposal: [portolan-data#63](https://github.com/portolan-sdi/portolan-data/issues/63)

**`catalog/` is the published catalog.** Everything in it is published, and
nothing outside it ever is. The COGs are built into `staging/` and never
enter git. Each return period is one collection with one collection-level
COG.

## Build

```bash
python -m pip install -r requirements-ci.txt
python3 tools/build.py
```

`tools/build.py` downloads the three GeoTIFFs, checks each against the SHA-256
in `tools/sources.json`, and writes COGs with embedded statistics to
`staging/`. It then writes the measured STAC fields: sizes, checksums, bands,
projection, and extent. Every other STAC field is written by hand.

`tools/thumbnail.py` renders each `catalog/<collection>/thumbnail.png` from
that collection's render. Run it before the build when a render changes, and
look at the images before you commit them.

## Test

```bash
python3 tools/build.py --check
CI_LIGHT=1 python3 tests/run_all.py
```

| Gate | What it checks |
|---|---|
| `tools/build.py --check` | The STAC JSON matches what the build measures |
| `test_links.py` | Every relative link and asset href resolves |
| `test_publish.py` | Nothing outside `catalog/` can be uploaded |
| `test_upload_data.py` | Only staged files with an allowed suffix upload |
| `test_stac_valid.py` | Valid STAC 1.1.0, via `stac-check` |
| `test_conformance.py` | Portolan conformance, via `rashid` |
| `test_agent_claims.py` | Every claim in each published `AGENTS.md`, against the COGs and the sources |
| `test_agent_claims_mutation.py` | The claims gate fails when any number in a guide changes |

CI runs all of them on each pull request. The weekly
[Live claims](.github/workflows/live-claims.yml) workflow runs the claims gate
against the published objects and compares their bytes with the STAC JSON.

## Publish

The catalog publishes to the `portolan-mirrors` account on Source
Cooperative. `catalog.publish.yaml` names the `source-coop-proxy` AWS profile,
which reads temporary credentials from the
[source-coop CLI](https://github.com/source-cooperative/source-coop-cli).

```bash
source-coop login
python3 tools/upload_data.py --confirm
python3 tools/publish.py --confirm
```

Both scripts run as a dry run without `--confirm`. Neither deletes an object.

## License

Apache-2.0 covers the tooling in this repository. The data is
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), from the World Bank
and CSIRO.
