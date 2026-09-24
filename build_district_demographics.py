#!/usr/bin/env python
"""
Pull ACS 5-Year tract-level estimates for King County, WA and apportion them
to Seattle's 7 City Council districts, writing a static data file the app
reads at request time — the app never calls the Census API directly.

Run build_tract_district_crosswalk.py first (only needed again after a
redistricting or a new decennial TIGER vintage). This script should be rerun
whenever the ACS vintage should be refreshed (new 5-year release, roughly
annual) — it is not scheduled/automated.

Requires CENSUS_API_KEY in the environment (free key:
https://api.census.gov/data/key_signup.html).

Usage:
    CENSUS_API_KEY=... python build_district_demographics.py
"""

import csv
import datetime
import json
import os
import time
import urllib.parse
import urllib.request

API_KEY = os.environ["CENSUS_API_KEY"]
YEAR = 2023
BASE = f"https://api.census.gov/data/{YEAR}/acs/acs5"
STATE_FIPS = "53"  # Washington
COUNTY_FIPS = "033"  # King County
SEATTLE_PLACE_FIPS = "63000"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "server", "legistar", "data")
CROSSWALK_PATH = os.path.join(DATA_DIR, "tract_district_overlap.csv")
OUT_PATH = os.path.join(DATA_DIR, "district_demographics.json")


def census_get(variables, for_geo, in_geo=None):
    params = {"get": ",".join(["NAME"] + variables), "for": for_geo, "key": API_KEY}
    if in_geo:
        params["in"] = in_geo
    url = BASE + "?" + urllib.parse.urlencode(params, safe=":*+,")
    with urllib.request.urlopen(url, timeout=30) as resp:
        rows = json.loads(resp.read())
    header, *data = rows
    return [dict(zip(header, row)) for row in data]


# ── Variable definitions per statutory-population slug (label_schema.py) ────
# Each entry maps to a specific ACS table already cited in
# STATUTORY_POPULATION_DEFINITIONS. Percent = sum(numerator) / sum(universe)
# computed post-aggregation (a ratio of sums, not a sum of ratios) — the
# correct way to combine estimates across small areas.
_AGE_65_PLUS = [
    "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
    "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
]
_AGE_UNDER_18 = [
    "B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",
    "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E",
]
_DISABILITY_VARS = [
    "B18101_004E", "B18101_007E", "B18101_010E", "B18101_013E", "B18101_016E", "B18101_019E",
    "B18101_023E", "B18101_026E", "B18101_029E", "B18101_032E", "B18101_035E", "B18101_038E",
]
_LEP_HOUSEHOLD_VARS = [
    "B16002_004E", "B16002_007E", "B16002_010E", "B16002_013E", "B16002_016E",
    "B16002_019E", "B16002_022E", "B16002_025E", "B16002_028E", "B16002_031E",
    "B16002_034E", "B16002_037E",
]

# Populations from label_schema.STATUTORY_POPULATIONS that map to a real ACS
# variable. Three of the eleven are deliberately left out — see
# EXCLUDED_POPULATIONS below — rather than approximated with something
# fabricated.
POPULATION_VARS = {
    "racial-or-ethnic-minorities": {
        "numerator": ["B03002_001E", "B03002_003E"],  # total, white-alone-non-hispanic
        "universe": ["B03002_001E"],
        "compute": lambda n, u: n[0] - n[1],
        "table": "B03002",
    },
    "low-income-populations": {
        "numerator": ["B17001_002E"],
        "universe": ["B17001_001E"],
        "compute": lambda n, u: n[0],
        "table": "B17001",
    },
    "linguistically-isolated": {
        "numerator": _LEP_HOUSEHOLD_VARS,
        "universe": ["B16002_001E"],
        "compute": lambda n, u: sum(n),
        "table": "B16002",
        "unit": "households",
    },
    "people-with-disabilities": {
        "numerator": _DISABILITY_VARS,
        "universe": ["B18101_001E"],
        "compute": lambda n, u: sum(n),
        "table": "B18101",
    },
    "older-adults": {
        "numerator": _AGE_65_PLUS,
        "universe": ["B01001_001E"],
        "compute": lambda n, u: sum(n),
        "table": "B01001",
    },
    "youth-and-children": {
        "numerator": _AGE_UNDER_18,
        "universe": ["B01001_001E"],
        "compute": lambda n, u: sum(n),
        "table": "B01001",
    },
    "pregnant-people-and-new-parents": {
        "numerator": ["B13002_002E"],
        "universe": ["B13002_001E"],
        "compute": lambda n, u: n[0],
        "table": "B13002",
        "note": (
            "Proxy only: women 15-50 who gave birth in the past 12 months. "
            "No ACS variable captures current pregnancy."
        ),
    },
    "tribal-members-and-treaty-rights-holders": {
        "numerator": ["B02001_004E"],
        "universe": ["B02001_001E"],
        "compute": lambda n, u: n[0],
        "table": "B02001",
        "note": (
            "Proxy only: self-identified American Indian/Alaska Native "
            "race. Not tribal enrollment or treaty status."
        ),
    },
    "households-with-children-under-18": {
        "numerator": ["B11005_002E"],
        "universe": ["B11005_001E"],
        "compute": lambda n, u: n[0],
        "table": "B11005",
        "unit": "households",
    },
    "households-with-a-child-under-6": {
        # Sum of "under 6 only" + "under 6 and 6-17" across all three family
        # types (married-couple, male householder, female householder).
        "numerator": [
            "B11003_004E", "B11003_005E",
            "B11003_011E", "B11003_012E",
            "B11003_017E", "B11003_018E",
        ],
        "universe": ["B11003_001E"],
        "compute": lambda n, u: sum(n),
        "table": "B11003",
        "unit": "families",
        "note": (
            "Universe is total families, not all households — this table "
            "doesn't capture the rare non-family household raising a "
            "young child."
        ),
    },
}

EXCLUDED_POPULATIONS = {
    "workers-in-affected-industries": (
        "Depends on which industry a specific bill affects; not a fixed "
        "population share."
    ),
    "populations-facing-environmental-harm": (
        "Requires environmental-exposure data (e.g. EPA EJScreen, "
        "discontinued 2025) layered over demographics; not a Census "
        "variable."
    ),
    "overburdened-community-geography": (
        "Washington HEAL Act designation requires the state's "
        "Environmental Health Disparities Map; not a Census variable."
    ),
}

ALL_VARS = sorted(
    {v for spec in POPULATION_VARS.values() for v in spec["numerator"] + spec["universe"]}
)


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_tract_data():
    """Return {geoid: {variable: value}} for every King County tract.

    Chunked because the Census API caps requests at 50 variables.
    """
    rows_by_tract = {}
    for chunk in chunked(ALL_VARS, 45):
        rows = census_get(
            chunk, for_geo="tract:*", in_geo=f"state:{STATE_FIPS}+county:{COUNTY_FIPS}"
        )
        for row in rows:
            geoid = row["state"] + row["county"] + row["tract"]
            for v in chunk:
                rows_by_tract.setdefault(geoid, {})[v] = (
                    int(row[v]) if row[v] not in (None, "", "-666666666") else 0
                )
        time.sleep(0.2)
    return rows_by_tract


def fetch_citywide():
    """Return {variable: value} queried directly at the Seattle place level
    (not resummed from districts/tracts, to avoid compounding apportionment
    error in the one number most readers will see first)."""
    result = {}
    for chunk in chunked(ALL_VARS, 45):
        row = census_get(chunk, for_geo=f"place:{SEATTLE_PLACE_FIPS}", in_geo=f"state:{STATE_FIPS}")[0]
        for v in chunk:
            result[v] = int(row[v]) if row[v] not in (None, "", "-666666666") else 0
        time.sleep(0.2)
    return result


def load_crosswalk():
    weights = {}  # geoid -> {district: frac_of_tract_area}
    with open(CROSSWALK_PATH) as f:
        for row in csv.DictReader(f):
            weights.setdefault(row["GEOID"], {})[int(row["district"])] = float(
                row["frac_of_tract"]
            )
    return weights


def build_population_block(raw_vars):
    out = {}
    for slug, spec in POPULATION_VARS.items():
        n = [raw_vars[v] for v in spec["numerator"]]
        u = [raw_vars[v] for v in spec["universe"]]
        count = spec["compute"](n, u)
        universe = u[0]
        out[slug] = {
            "count": round(count),
            "universe": round(universe),
            "percent": round(100 * count / universe, 1) if universe else None,
            "table": spec["table"],
        }
        if "note" in spec:
            out[slug]["note"] = spec["note"]
        if "unit" in spec:
            out[slug]["unit"] = spec["unit"]
    return out


def main():
    print("Fetching tract-level ACS data...")
    tract_data = fetch_tract_data()
    print(f"  {len(tract_data)} King County tracts")

    print("Fetching citywide (Seattle place) ACS data...")
    citywide_raw = fetch_citywide()

    crosswalk = load_crosswalk()
    district_totals = {d: {v: 0.0 for v in ALL_VARS} for d in range(1, 8)}
    for geoid, weights in crosswalk.items():
        tract = tract_data.get(geoid)
        if tract is None:
            continue
        for district, frac in weights.items():
            for v in ALL_VARS:
                district_totals[district][v] += tract[v] * frac

    result = {
        "vintage": {
            "acs_dataset": f"ACS {YEAR} 5-Year Estimates",
            "acs_years_covered": f"{YEAR - 4}-{YEAR}",
            "tiger_vintage": YEAR,
            "retrieved_at": datetime.date.today().isoformat(),
            "source_url": "https://www.census.gov/data/developers/data-sets/acs-5year.html",
            "api_endpoint": BASE,
            "tables_used": sorted({spec["table"] for spec in POPULATION_VARS.values()}),
        },
        "methodology": (
            "Census tract estimates apportioned to City Council districts by "
            "area-weighted overlay: each tract's counts are split across "
            "districts in proportion to the share of the tract's land area "
            "falling in each district, then summed per district. District "
            "boundaries: seattleio/seattle-boundaries-data (community-"
            "maintained, not an official City of Seattle GIS source). "
            "Tract boundaries: US Census Bureau TIGER/Line cartographic "
            "boundary files, 2023 vintage. Citywide figures are queried "
            "directly at the Seattle place level, not resummed from "
            "districts. ACS 5-year estimates carry sampling error that can "
            "be substantial at the tract level; treat percentages as "
            "estimates, not precise counts."
        ),
        "excluded_populations": EXCLUDED_POPULATIONS,
        "citywide": build_population_block(citywide_raw),
        "districts": {
            str(d): build_population_block(totals) for d, totals in district_totals.items()
        },
    }

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
