"""
datamart-mcp: MCP server exposing U.S. county-level data to AI assistants.

Tools:
  get_county_profile   — all available stats for a county (by FIPS)
  search_counties      — list counties, optionally filtered by state
  get_state_summary    — state-level aggregate stats
  compare_counties     — side-by-side profile for multiple FIPS codes

Configuration:
  DATAMART_API_URL  — base URL of the running API (default: http://localhost:8000/api)

Usage:
  python datamart-mcp/server.py
  # or via MCP client config: {"command": "python", "args": ["datamart-mcp/server.py"]}
"""

import json
import os
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("DATAMART_API_URL", "http://localhost:8000/api").rstrip("/")

mcp = FastMCP(
    "datamart",
    instructions=(
        "Access U.S. county-level socioeconomic, health, housing, labor, and "
        "environmental data. FIPS codes are 5-digit strings (e.g. '06037' for "
        "Los Angeles County). State FIPS are 2-digit (e.g. '06' for California)."
    ),
)

_client = httpx.Client(timeout=15)


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{API_BASE}/{path.lstrip('/')}"
    resp = _client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    # Unwrap DRF paginated responses
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


@mcp.tool()
def get_county_profile(fips: str) -> str:
    """
    Return all available statistics for a U.S. county.

    Covers: Census ACS5 demographics, CDC PLACES health, BLS labor, USDA food
    environment, EPA air quality, HUD fair market rents, NHTSA traffic fatalities,
    and education graduation rates.

    Args:
        fips: 5-digit county FIPS code (e.g. "06037" for Los Angeles County, CA).
    """
    if len(fips) not in (4, 5) or not fips.isdigit():
        return json.dumps({"error": f"Invalid FIPS code: {fips!r}. Must be 4-5 digits."})

    fips = fips.zfill(5)
    try:
        data = _get("profile/", {"fips": fips})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"API error {e.response.status_code}: {e.response.text[:200]}"})

    if not data:
        return json.dumps({"error": f"No data found for FIPS {fips}."})

    return json.dumps(data[0] if isinstance(data, list) else data, default=str)


@mcp.tool()
def search_counties(state_fips: str = "", name_contains: str = "") -> str:
    """
    List U.S. counties, optionally filtered by state or name substring.

    Returns basic geo metadata: FIPS, county name, state FIPS, and state name.
    Use the returned FIPS codes with get_county_profile for full statistics.

    Args:
        state_fips: 2-digit state FIPS code to filter by (e.g. "06" for California).
                    Leave empty to search all states.
        name_contains: case-insensitive substring to match against county name
                       (e.g. "cook" matches Cook County, IL).
    """
    params: dict[str, str] = {"geo_type": "county"}
    if state_fips:
        params["state_fips"] = state_fips.zfill(2)

    try:
        data = _get("geo/", params)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"API error {e.response.status_code}"})

    results = data if isinstance(data, list) else data.get("results", data)

    if name_contains:
        needle = name_contains.lower()
        results = [r for r in results if needle in (r.get("name") or "").lower()]

    summary = [
        {"fips": r["fips"], "name": r.get("name", ""), "state_fips": r.get("state_fips", "")}
        for r in results[:200]
    ]
    return json.dumps({"count": len(summary), "counties": summary})


@mcp.tool()
def get_state_summary(state_fips: str) -> str:
    """
    Return population-weighted aggregate statistics for all counties in a state.

    Includes median income, poverty rate, unemployment, educational attainment,
    population, and health indicators aggregated at the state level.

    Args:
        state_fips: 2-digit state FIPS code (e.g. "06" for California, "48" for Texas).
    """
    if not state_fips or not state_fips.strip().isdigit():
        return json.dumps({"error": "state_fips must be a 2-digit numeric code."})

    sf = state_fips.zfill(2)
    try:
        data = _get("aggregates/state-summary/", {"state_fips": sf})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"API error {e.response.status_code}"})

    results = data if isinstance(data, list) else data.get("results", [])
    if not results:
        return json.dumps({"error": f"No state summary found for state_fips={sf}."})

    return json.dumps(results[0] if len(results) == 1 else results, default=str)


@mcp.tool()
def compare_counties(fips_codes: list[str]) -> str:
    """
    Return side-by-side profiles for multiple counties to enable direct comparison.

    Fetches a full profile for each FIPS code and returns them as a list, ordered
    to match the input. Counties with no data are omitted and listed in 'missing'.

    Args:
        fips_codes: list of 5-digit county FIPS codes (2–10 recommended; max 20).
    """
    if not fips_codes:
        return json.dumps({"error": "Provide at least one FIPS code."})
    if len(fips_codes) > 20:
        return json.dumps({"error": "Maximum 20 FIPS codes per comparison."})

    profiles = []
    missing = []
    for fips in fips_codes:
        fips = str(fips).zfill(5)
        try:
            data = _get("profile/", {"fips": fips})
            if data:
                profiles.append(data[0] if isinstance(data, list) else data)
            else:
                missing.append(fips)
        except httpx.HTTPStatusError:
            missing.append(fips)

    result: dict[str, Any] = {"count": len(profiles), "profiles": profiles}
    if missing:
        result["missing"] = missing
    return json.dumps(result, default=str)


@mcp.tool()
def list_datasets() -> str:
    """
    List all data sources available in this datamart, with metadata.

    Returns source name, description, geographic coverage, time range, row count,
    and last ingestion timestamp for each dataset.
    """
    try:
        data = _get("datasets/")
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"API error {e.response.status_code}"})

    results = data if isinstance(data, list) else data.get("results", data)
    return json.dumps(results, default=str)


if __name__ == "__main__":
    mcp.run()
