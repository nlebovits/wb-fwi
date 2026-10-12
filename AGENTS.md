# Agent Instructions

This repository builds and publishes a Portolan mirror of the World Bank
global wildfire hazard dataset. The published catalog is
`https://data.source.coop/portolan-mirrors/wb-fwi/catalog.json`.

## The build

`tools/build.py` downloads the World Bank GeoTIFFs, writes one COG per
collection to `staging/`, and writes the measured fields into the STAC JSON.
`tools/sources.json` pins each source file by SHA-256. A changed upstream
file stops the build. Do not edit a pin to make the build pass.
Read what changed upstream first.

The build owns the measured fields. Edit every other STAC field by hand.
`python3 tools/build.py --check` fails when the STAC JSON and the built files
disagree.

`tools/thumbnail.py` renders each collection thumbnail from that collection's
render. Run it before the build when a render changes, then look at the
images.

## The publish boundary

`catalog/` is the published catalog. Everything in it is published, and
nothing outside it ever is. Do not move a file into `catalog/` to make it
publish. The COGs live in `staging/` and `tools/upload_data.py` uploads
them.

## Data never enters git

Never commit a COG. CI rebuilds the COGs from the pinned sources. Git keeps
every version of a binary forever.

## Published agent guides

Every block in a `catalog/**/AGENTS.md` carries a marker that CI tests. Read
the docstring of `tests/test_agent_claims.py` for the marker syntax. A
`check` marker names a function that measures the COGs. A `quote` marker
names a source and its exact words. A block that only instructs the reader
carries `<!-- guidance -->`.

Every number in a block must occur in a marker's quote or a check's output.
`tests/test_agent_claims_mutation.py` changes each number in turn and fails
when the claims gate still passes. When you add a claim, add its check or
quote in the same change.

## The conformance allow-list

`ACCEPTED` in `tests/test_conformance.py` ships empty. Never add an entry
without a matching row in `docs/conformance.md` giving the rule, where it
fires, why it is accepted, and the issue tracking its removal.

## The links back to this repository

`catalog/catalog.json` carries a `vcs` link and an `issues` link. Keep both
hrefs absolute, because a relative href resolves against the public base URL.
