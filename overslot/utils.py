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
