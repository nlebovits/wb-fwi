#!/usr/bin/env python3
"""Every STAC object validates against its core schema and each extension schema.

The registry runs stac-node-validator, which checks each object against the
STAC 1.1.0 core schema and against every URL in its stac_extensions. This
gate runs the same checks with jsonschema. stac-check does not cover them
here, because test_stac_valid.py exempts the collections from a stac-check
crash.

The gate fetches each schema and every schema it references over HTTPS.

Run: python3 tests/test_extension_schemas.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from functools import cache
from pathlib import Path

from jsonschema import Draft7Validator, validators
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
CORE = {
    "Catalog": "https://schemas.stacspec.org/v1.1.0/catalog-spec/json-schema/catalog.json",
    "Collection": "https://schemas.stacspec.org/v1.1.0/collection-spec/json-schema/collection.json",
    "Feature": "https://schemas.stacspec.org/v1.1.0/item-spec/json-schema/item.json",
}


@cache
def fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "wb-fwi-schemas"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def retrieve(uri: str) -> Resource:
    return Resource.from_contents(fetch(uri.split("#")[0]), default_specification=DRAFT7)


REGISTRY = Registry(retrieve=retrieve)


def validate(document: dict, url: str) -> list[str]:
    schema = fetch(url)
    cls = validators.validator_for(schema, default=Draft7Validator)
    validator = cls(schema, registry=REGISTRY)
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '(root)'}: {error.message[:160]}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    ]


def main() -> int:
    failures = []
    count = 0
    for path in sorted(CATALOG.rglob("*.json")):
        document = json.loads(path.read_text())
        rel = path.relative_to(ROOT)
        for url in [CORE[document["type"]], *document.get("stac_extensions", [])]:
            count += 1
            for error in validate(document, url):
                failures.append(f"{rel}: {url}: {error}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"PASS: {count} schema validations across the catalog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
