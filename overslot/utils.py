from googleapiclient.discovery import build
from google.oauth2 import service_account

import os

import gspread
import json

import base64
import numpy as np
from django.db.models import Q
from thefuzz import fuzz
from nicknames import NickNamer


def parse_sheet(sheet=None):
    if sheet:
        if sheet.value_cutoff:
            sheet.players = get_sheet(
                sheet._id, sheet._range, value_cutoff=sheet.value_cutoff
            )
        else:
            sheet.players = get_sheet(sheet._id, sheet._range)

        for player in sheet.players:

            if player.get('school', None):
                player['school'] = player['school'].strip()

            if player.get("city", None):
                player["city"] = player["city"].strip()

            if player.get("blurb", None):
                player["blurb"] = kill_curly(player["blurb"]).strip()

            if player.get("state", None):
                player["state_abbrev"] = None
                try:
                    player["state_abbrev"] = STATE_NAME_TO_ABBREV.get(
                        player["state"].strip(), None
                    )

                except:
                    pass
    return sheet


def get_google_creds(scopes):
    if os.environ.get("B64_GOOGLE", None):
        service_account_creds = base64.b64decode(os.environ.get("B64_GOOGLE", None))

        service_account_info = json.loads(service_account_creds)

        creds = service_account.Credentials.from_service_account_info(
            info=service_account_info, scopes=scopes
        )
    else:
        creds = service_account.Credentials.from_service_account_file(filename="credentials.json", scopes=scopes)
    return creds


def write_sheet(sheet_id, sheet_range, data):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = get_google_creds(SCOPES)

    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)

    first_sheet = sheet.get_worksheet(0)

    first_sheet.update(sheet_range, data)


def get_sheet(sheet_id, sheet_range, value_cutoff=None):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    creds = get_google_creds(SCOPES)

    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
    values = result.get("values", None)

    if values:
        if value_cutoff:
            return [dict(zip(values[0], r)) for r in values[1:value_cutoff]]
        return [dict(zip(values[0], r)) for r in values[1:]]
    return []


def sheet_tab_a1_range(tab_title, cell_range="A:Z"):
    """
    Build an A1 range with a correctly quoted worksheet title.
    Required when the tab name contains spaces, quotes, or other special characters.
    """
    escaped = str(tab_title).replace("'", "''")
    return f"'{escaped}'!{cell_range}"


def list_spreadsheet_sheet_titles(sheet_id):
    """
    Return worksheet titles for a Google spreadsheet, in UI tab order.
    Uses the same read-only Sheets scope as get_sheet.
    """
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = get_google_creds(SCOPES)
    service = build("sheets", "v4", credentials=creds)
    body = (
        service.spreadsheets()
        .get(spreadsheetId=sheet_id, fields="sheets.properties(title)")
        .execute()
    )
    titles = []
    for sh in body.get("sheets") or []:
        props = sh.get("properties") or {}
        t = props.get("title")
        if t is not None:
            titles.append(t)
    return titles


def kill_curly(s):
    if isinstance(s, str):
        return s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return s


STATE_NAME_TO_ABBREV = {
    "Alabama": "AL",
    "Alaska": "AK",
    "American Samoa": "AS",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Guam": "GU",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Northern Mariana Islands": "MP",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Puerto Rico": "PR",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virgin Islands": "VI",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "Australia": "AUS",
    "Canada": "CAN",
    "Panama": "PAN",
}


# Common utilities for Trackman data loading

def fix_blanks(row):
    """Convert empty strings to None in a row dictionary"""
    for k, v in row.items():
        if v == "":
            row[k] = None
    return row


def parse_value(val):
    """Parse a value from sheet data, handling percentages and various formats"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        try:
            if val.endswith('%'):
                return float(val.rstrip('%')) / 100.0
            return float(val)
        except (ValueError, TypeError):
            return None
    return None


def calculate_percentile_distribution(rows, column_name):
    """Calculate the percentile distribution for a column
    
    Returns the percentile thresholds that can be used to rank any value
    """
    values = []
    for row in rows:
        value = parse_value(row.get(column_name))
        if value is not None:
            values.append(value)
    
    if not values:
        return None
    
    # Calculate percentiles for this column (0th to 100th percentile)
    percentiles = np.percentile(values, np.arange(101))
    return percentiles


def get_percentile_rank(value, percentile_distribution, invert=False):
    """Get the percentile rank for a single value based on a percentile distribution"""
    if value is None or percentile_distribution is None:
        return None
    
    percentile_rank = np.interp(value, percentile_distribution, np.arange(101))
    percentile_value = percentile_rank / 100.0
    
    # Invert percentile for negative metrics (lower values = better performance)
    if invert:
        percentile_value = 1.0 - percentile_value
    
    return percentile_value


def calculate_weighted_percentile_score(row_percentiles, weights_info):
    """Calculate weighted average of percentiles"""
    score = 0
    total_weight = 0
    for weight_tuple in weights_info:
        # Handle both old format (col_name, weight) and new format (col_name, weight, invert)
        col_name = weight_tuple[0]
        weight = weight_tuple[1]
        
        percentile = row_percentiles.get(col_name)
        if percentile is not None:
            score += percentile * weight
            total_weight += weight
    if total_weight == 0:
        return None
    return score / total_weight


def fuzzy_find_player(name, debug=False, stdout=None):
    """Find a player by name using fuzzy matching, nickname handling, and merge resolution"""
    from overslot import models
    
    def normalize_name(n):
        n = n.lower().strip()
        for suffix in [' jr.', ' sr.', ' ii', ' iii', ' iv']:
            if n.endswith(suffix):
                n = n[:-len(suffix)]
        return n

    def extract_first_names(full_name):
        """Extract first and middle names from a full name"""
        parts = full_name.split()
        if len(parts) <= 1:
            return [full_name] if parts else []
        # Return all parts except the last (assuming last is surname)
        return parts[:-1]

    normalized_input = normalize_name(name)
    input_parts = normalized_input.split()
    
    if not input_parts:
        return None

    # Initialize nickname handler
    nn = NickNamer()
    
    # Get all players to check against (prefer active records)
    all_players = models.Player.objects.filter(active=True)
    
    exact_matches = []
    nickname_matches = []
    fuzzy_matches = []
    best_fuzzy_score = -1
    best_fuzzy_player = None
    
    for player in all_players:
        normalized_player = normalize_name(player.name)
        player_parts = normalized_player.split()
        
        # 1. Try exact matching (normalized)
        if normalized_input == normalized_player:
            exact_matches.append(player)
            continue
        
        # 2. Try nickname/canonical name variations
        input_first_names = extract_first_names(normalized_input)
        player_first_names = extract_first_names(normalized_player)
        
        # Check if any first name matches through nickname relationships
        name_variations_match = False
        for input_name in input_first_names:
            for player_name in player_first_names:
                # Check if input_name is a nickname of player_name
                if input_name in nn.nicknames_of(player_name):
                    name_variations_match = True
                    break
                # Check if player_name is a nickname of input_name  
                if player_name in nn.nicknames_of(input_name):
                    name_variations_match = True
                    break
                # Check if they share a canonical name
                input_canonicals = nn.canonicals_of(input_name)
                player_canonicals = nn.canonicals_of(player_name)
                if input_canonicals and player_canonicals and input_canonicals & player_canonicals:
                    name_variations_match = True
                    break
            if name_variations_match:
                break
        
        # If names match through nickname relationships, check if surname matches too
        if name_variations_match:
            # Check if surnames match (fuzzy matching for surnames)
            if len(input_parts) > 1 and len(player_parts) > 1:
                input_surname = input_parts[-1]
                player_surname = player_parts[-1]
                surname_score = fuzz.ratio(input_surname, player_surname)
                if surname_score >= 90:  # High threshold for surname matching
                    nickname_matches.append(player)
                    continue
            elif len(input_parts) == 1 or len(player_parts) == 1:
                # If one of them only has one name, consider it a match
                nickname_matches.append(player)
                continue
        
        # 3. Fall back to fuzzy matching
        score = fuzz.ratio(normalized_input, normalized_player)
        if score > best_fuzzy_score:
            best_fuzzy_score = score
            best_fuzzy_player = player
        if score >= 95:
            fuzzy_matches.append(player)
    
    # Return the best match based on priority
    if len(exact_matches) == 1:
        if debug and stdout:
            stdout.write(f"[match] Exact: '{name}' -> '{exact_matches[0].name}' (pk={exact_matches[0].pk})")
        return exact_matches[0]
    elif len(exact_matches) > 1:
        # Multiple exact matches — attempt to resolve using merge decisions to find the primary
        try:
            merges = models.DuplicateDecision.objects.filter(
                decision='merged',
                primary_player__isnull=False
            ).filter(
                Q(player1__in=exact_matches) | Q(player2__in=exact_matches)
            )
            primary_candidates = [m.primary_player for m in merges if m.primary_player in exact_matches]
            unique_primary_candidates = list({p.pk: p for p in primary_candidates}.values())
            if len(unique_primary_candidates) == 1:
                primary = unique_primary_candidates[0]
                if debug and stdout:
                    stdout.write(f"[match] Exact (resolved via merge): '{name}' -> '{primary.name}' (pk={primary.pk})")
                return primary
        except Exception as e:
            if debug and stdout:
                stdout.write(f"[match] Error resolving merges for '{name}': {e}")
    elif len(nickname_matches) == 1:
        if debug and stdout:
            stdout.write(f"[match] Nickname: '{name}' -> '{nickname_matches[0].name}' (pk={nickname_matches[0].pk})")
        return nickname_matches[0]
    elif len(fuzzy_matches) == 1:
        if debug and stdout:
            stdout.write(f"[match] Fuzzy: '{name}' -> '{fuzzy_matches[0].name}' (pk={fuzzy_matches[0].pk})")
        return fuzzy_matches[0]
    else:
        if debug and stdout:
            stdout.write(
                f"[match] No unique match for '{name}'. exact={len(exact_matches)}, nickname={len(nickname_matches)}, "
                f"fuzzy={len(fuzzy_matches)}; best_fuzzy={(best_fuzzy_player.name if best_fuzzy_player else None)}({best_fuzzy_score})"
            )
    
    return None


def _parse_year(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def college_stat_eligibility_for_players(player_ids=None):
    """
    Map player_id -> (max_hs_draft_year, has_college_ranking).

    Includes inactive PlayerRanking rows: a 2027 HS prospect whose board row
    was later deactivated is still a high-schooler, not the college player
    who shares their name.
    """
    from overslot import models

    qs = models.PlayerRanking.objects.select_related("ranking")
    if player_ids is not None:
        qs = qs.filter(player_id__in=player_ids)

    eligibility = {}
    for pr in qs.iterator():
        if not pr.player_id:
            continue
        max_hs, has_college = eligibility.get(pr.player_id, (None, False))
        if pr.level == "College":
            has_college = True
        elif pr.level == "High School" and pr.ranking:
            year = _parse_year(pr.ranking.year)
            if year is not None and (max_hs is None or year > max_hs):
                max_hs = year
        eligibility[pr.player_id] = (max_hs, has_college)
    return eligibility


def player_accepts_college_season(player, season_year, eligibility=None):
    """
    Whether college stats for `season_year` can belong to this Player.

    College Trackman/643 loaders match by name. If the only OverSlot Player
    with that name is a high-school prospect, stats for an unrelated college
    player get attached to the HS page.

    A player ranked High School for draft class Y is in high school through
    the spring of year Y, so they cannot have NCAA stats for season S where
    S <= Y — unless they also have a College ranking (enrolled early / JUCO).
    """
    if player is None:
        return False
    if eligibility is None:
        eligibility = college_stat_eligibility_for_players([player.pk])
    max_hs, has_college = eligibility.get(player.pk, (None, False))
    if has_college or max_hs is None:
        return True
    season = _parse_year(season_year)
    if season is None:
        return True
    return season > max_hs


def resolve_college_stat_player(name, season_year, debug=False, stdout=None):
    """Name-match a player, then reject HS-class collisions for this college season."""
    obj = fuzzy_find_player(name, debug=debug, stdout=stdout)
    if obj and not player_accepts_college_season(obj, season_year):
        if debug and stdout:
            stdout.write(
                f"[match] Skip college season {season_year} for '{name}' -> "
                f"'{obj.name}' (pk={obj.pk}): HS draft class is not yet in college"
            )
        return None
    return obj


def find_mismatched_college_stats():
    """
    College Trackman and 643 rows attached to HS-only players whose draft
    class year is >= the stat season (name-collision junk).
    """
    from overslot import models

    eligibility = college_stat_eligibility_for_players()
    trackman = [
        s
        for s in models.PlayerStatSeason.objects.filter(level="College").select_related("player")
        if not player_accepts_college_season(s.player, s.year, eligibility)
    ]
    stats_643 = [
        s
        for s in models.Player643StatSeason.objects.select_related("player")
        if not player_accepts_college_season(s.player, s.year, eligibility)
    ]
    return trackman, stats_643


def filter_plausible_college_seasons(seasons):
    """Drop name-collision college seasons from a Trackman or 643 queryset/list."""
    seasons = list(seasons)
    if not seasons:
        return seasons
    eligibility = college_stat_eligibility_for_players({s.player_id for s in seasons})
    return [
        s for s in seasons
        if player_accepts_college_season(s.player, s.year, eligibility)
    ]


def get_primary_team(team):
    """
    Check if this team has been merged into another team.
    If so, return the primary team. Otherwise, return the original team.
    Uses the same logic as load_games.py for consistency.
    """
    from overslot import models
    
    # Check if this team was merged into another (it would be inactive)
    if not team.active:
        # Look for a merge decision where this team was the secondary
        merge_decision = models.TeamDuplicateDecision.objects.filter(
            decision='merged',
            primary_team__isnull=False
        ).filter(
            Q(team1=team) | Q(team2=team)
        ).exclude(
            primary_team=team  # Don't match if this team was the primary
        ).first()
        
        if merge_decision and merge_decision.primary_team.active:
            return merge_decision.primary_team
    
    return team


def find_team_by_school_name(school_name):
    """
    Find a Team object by matching school name, using deduplication logic.
    Returns the primary team if the matched team has been merged.
    
    Args:
        school_name: The school name string to match
        
    Returns:
        Team object or None if no match found
    """
    from overslot import models
    from overslot.team_duplicate_views import normalize_team_name
    
    if not school_name:
        return None
    
    normalized_school = normalize_team_name(school_name)
    
    # Try exact match first (case-insensitive)
    try:
        team = models.Team.objects.get(name__iexact=school_name, active=True)
        return get_primary_team(team)
    except models.Team.DoesNotExist:
        pass
    except models.Team.MultipleObjectsReturned:
        # If multiple matches, prefer exact case match
        try:
            team = models.Team.objects.get(name=school_name, active=True)
            return get_primary_team(team)
        except models.Team.DoesNotExist:
            # Take first one and resolve via deduplication
            team = models.Team.objects.filter(name__iexact=school_name, active=True).first()
            if team:
                return get_primary_team(team)
    
    # Try normalized match
    all_teams = models.Team.objects.filter(active=True)
    for team in all_teams:
        normalized_team = normalize_team_name(team.name)
        if normalized_team == normalized_school:
            return get_primary_team(team)
    
    # Try fuzzy matching with a threshold
    from thefuzz import fuzz
    best_match = None
    best_score = 0
    threshold = 85  # Require 85% similarity
    
    for team in all_teams:
        normalized_team = normalize_team_name(team.name)
        score = fuzz.ratio(normalized_school, normalized_team)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = team
    
    if best_match:
        return get_primary_team(best_match)
    
    return None
