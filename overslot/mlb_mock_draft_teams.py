"""
MLB franchise IDs for cap-on-dark logos.

Kept in sync with draftboard/data/mock_draft_sim_team_ids.csv and draftboard/build-data.js
(team name → id for mock draft simulator / draftboard).
"""
from __future__ import annotations

from typing import Optional

# Same base URL as overslot/static/mock_draft/js/draft.js teamLogoHtml().
MLB_TEAM_CAP_ON_DARK_BASE = "https://www.mlbstatic.com/team-logos/team-cap-on-dark"

_MLB_TEAM_NAME_TO_ID: dict[str, int] = {
    "Oakland Athletics": 133,
    "Los Angeles Angels": 108,
    "Seattle Mariners": 136,
    "San Diego Padres": 135,
    "Arizona Diamondbacks": 109,
    "Chicago White Sox": 145,
    "Colorado Rockies": 115,
    "Milwaukee Brewers": 158,
    "Chicago Cubs": 112,
    "Los Angeles Dodgers": 119,
    "Texas Rangers": 140,
    "Houston Astros": 117,
    "Boston Red Sox": 111,
    "New York Yankees": 147,
    "Philadelphia Phillies": 143,
    "Miami Marlins": 146,
    "Baltimore Orioles": 110,
    "Atlanta Braves": 144,
    "Kansas City Royals": 118,
    "Detroit Tigers": 116,
    "Tampa Bay Rays": 139,
    "Toronto Blue Jays": 141,
    "Cleveland Guardians": 114,
    "Minnesota Twins": 142,
    "San Francisco Giants": 137,
    "New York Mets": 121,
    "Washington Nationals": 120,
    "St. Louis Cardinals": 138,
    "Pittsburgh Pirates": 134,
    "Cincinnati Reds": 113,
    # Pick order / team rules CSV uses "Athletics" (build-data.js maps to 133).
    "Athletics": 133,
}

_MLB_TEAM_NAME_TO_ID_LOWER = {k.lower(): v for k, v in _MLB_TEAM_NAME_TO_ID.items()}


def mlb_team_id_for_mock_team_name(name: Optional[str]) -> Optional[int]:
    """Resolve MLB Stats API-style team id from mock draft team label, or None."""
    if not name or not isinstance(name, str):
        return None
    s = name.strip()
    if not s:
        return None
    if s in _MLB_TEAM_NAME_TO_ID:
        return _MLB_TEAM_NAME_TO_ID[s]
    return _MLB_TEAM_NAME_TO_ID_LOWER.get(s.lower())


def mlb_team_cap_on_dark_url_for_team_name(name: Optional[str]) -> Optional[str]:
    """SVG URL for the same cap-on-dark treatment as the mock draft draftboard."""
    tid = mlb_team_id_for_mock_team_name(name)
    if tid is None:
        return None
    return f"{MLB_TEAM_CAP_ON_DARK_BASE}/{tid}.svg"
