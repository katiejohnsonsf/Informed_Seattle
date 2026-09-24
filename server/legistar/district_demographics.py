"""
Read-only access to the precomputed district-level Census/ACS dataset.

The actual numbers live in server/legistar/data/district_demographics.json,
built offline by build_tract_district_crosswalk.py + build_district_
demographics.py (repo root) — this app never calls the Census API itself.
"""

import json
import logging
import os
import typing as t
from functools import lru_cache

from server.legistar.label_schema import STATUTORY_POPULATION_LABELS

logger = logging.getLogger(__name__)

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "district_demographics.json")


@lru_cache(maxsize=1)
def _data() -> dict | None:
    """Return the parsed dataset, or None if it's missing/corrupt.

    This is read on every bill render, so a bad file (deleted, mid-refresh,
    truncated) should degrade to "no district data shown" rather than take
    down the whole calendar page.
    """
    try:
        with open(_DATA_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.warning("district_demographics.json missing or invalid at %s", _DATA_PATH)
        return None


def vintage_context() -> dict | None:
    """Page-level citation info: vintage, source link, methodology."""
    d = _data()
    if d is None:
        return None
    return {
        "vintage": d["vintage"],
        "methodology": d["methodology"],
    }


def district_impact_for_populations(slugs: list[str]) -> list[dict[str, t.Any]]:
    """
    Given the population slugs a bill's label flagged, return only the ones
    with real Census/ACS district data, each carrying citywide + per-district
    percentages for the density map. Slugs with no ACS grounding (see
    EXCLUDED_POPULATIONS in build_district_demographics.py) are silently
    dropped here — the caller shows nothing for those rather than a fabricated
    number. Sorted by citywide prevalence, descending, so the most prevalent
    flagged population is what a map defaults to showing.
    """
    d = _data()
    if d is None:
        return []
    citywide = d["citywide"]
    districts = d["districts"]

    out = []
    for slug in slugs:
        if slug not in citywide:
            continue
        entry = citywide[slug]
        out.append(
            {
                "slug": slug,
                "label": STATUTORY_POPULATION_LABELS.get(slug, slug),
                "unit": entry.get("unit", "population"),
                "note": entry.get("note"),
                "citywide_percent": entry["percent"],
                "by_district": {
                    dist: districts[dist][slug]["percent"] for dist in districts
                },
            }
        )
    out.sort(key=lambda p: p["citywide_percent"] or 0, reverse=True)
    return out
