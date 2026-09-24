#!/usr/bin/env python
"""
Build an area-weighted Census tract -> City Council district crosswalk.

Downloads the same district boundaries the site's vote map uses, plus the
Census Bureau's TIGER/Line cartographic tract boundaries for King County, and
overlays them to find what fraction of each tract's land area falls in each
council district. Tracts that straddle a district line get split
proportionally rather than assigned whole to one side.

Writes server/legistar/data/tract_district_overlap.csv, which
build_district_demographics.py consumes to apportion tract-level ACS counts
to districts. Requires geopandas/shapely/fiona (not a runtime dependency of
the Django app — only needed when regenerating this crosswalk, which should
be rare: only after a City Council redistricting or a new decennial TIGER
vintage).

Usage:
    python build_tract_district_crosswalk.py
"""

import os
import tempfile
import urllib.request
import zipfile

import geopandas as gpd

DISTRICT_GEOJSON_URL = (
    "https://raw.githubusercontent.com/seattleio/"
    "seattle-boundaries-data/master/data/city-council-districts.geojson"
)
TIGER_TRACT_ZIP_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_53_tract_500k.zip"
)
KING_COUNTY_FIPS = "033"
# Washington State Plane North (US Feet) — projected CRS for area math.
AREA_CRS = "EPSG:2926"
# Drop overlap slivers smaller than this share of the tract's area; these are
# boundary-alignment noise between two independently-drawn datasets, not real
# tract/district splits.
MIN_OVERLAP_FRACTION = 0.01

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "server", "legistar", "data", "tract_district_overlap.csv")


def _download(url: str, dest: str) -> None:
    urllib.request.urlretrieve(url, dest)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        districts_path = os.path.join(tmp, "districts.geojson")
        _download(DISTRICT_GEOJSON_URL, districts_path)
        districts = gpd.read_file(districts_path)

        tract_zip_path = os.path.join(tmp, "tracts.zip")
        _download(TIGER_TRACT_ZIP_URL, tract_zip_path)
        tract_dir = os.path.join(tmp, "tracts")
        with zipfile.ZipFile(tract_zip_path) as z:
            z.extractall(tract_dir)
        shp_name = next(f for f in os.listdir(tract_dir) if f.endswith(".shp"))
        tracts = gpd.read_file(os.path.join(tract_dir, shp_name))

    king = tracts[tracts["COUNTYFP"] == KING_COUNTY_FIPS].copy()
    king_proj = king.to_crs(AREA_CRS)
    districts_proj = districts.to_crs(AREA_CRS)
    king_proj["tract_area"] = king_proj.geometry.area

    overlay = gpd.overlay(
        king_proj[["GEOID", "tract_area", "geometry"]],
        districts_proj[["district", "geometry"]],
        how="intersection",
    )
    overlay["frac_of_tract"] = overlay.geometry.area / overlay["tract_area"]
    overlay = overlay[overlay["frac_of_tract"] > MIN_OVERLAP_FRACTION]

    out = overlay[["GEOID", "district", "frac_of_tract"]].sort_values(
        ["GEOID", "district"]
    )
    out["frac_of_tract"] = out["frac_of_tract"].round(6)
    out.to_csv(OUT_PATH, index=False)
    print(
        f"Wrote {OUT_PATH}: {out['GEOID'].nunique()} tracts, "
        f"{len(out)} tract/district rows"
    )


if __name__ == "__main__":
    main()
