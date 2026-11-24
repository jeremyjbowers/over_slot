"""
Matching college stat rows (Trackman sheets, 6-4-3) to Overslot players.

Stat sources only give us a name and a team. Matching on the name alone put a
South Alabama outfielder's numbers on the NC State Rett Johnson's page, so a
name match now has to agree on school too:

* the stat row's team is one of the player's known schools (ranking school or
  HS commitment), or
* another source puts the player at that team in the same season, or 6-4-3's
  career history for him includes that team, or
* a human already said "this name at this team is this player" (StatTeamLink).

When none of those hold, the row is held back and a pending StatTeamLink is
queued for review instead of being attached. Human decisions are stored per
(name, team, player), so a reviewed pair is never asked about again.
"""

import re

from django.db.models import Q

# Words that carry no identity in a school name.
_STOPWORDS = {"university", "of", "the", "college", "at"}

# Spellings that normalize differently but are the same school. Keys and
# values are both normalized keys (see normalize_school).
SCHOOL_ALIASES = {
    "ncst": "northcarolinast",
    "lsu": "louisianast",
    "byu": "brighamyoung",
    "usc": "southerncalifornia",
    "ucf": "centralflorida",
    "olemiss": "mississippi",
    "unc": "northcarolina",
    "pitt": "pittsburgh",
    "miamifl": "miami",
    "miamiflorida": "miami",
    "tcu": "texaschristian",
    "uconn": "connecticut",
    "vatech": "virginiatech",
    "gatech": "georgiatech",
    "fiu": "floridainternational",
    "fau": "floridaatlantic",
    "ucsb": "ucsantabarbara",
    "ucsd": "ucsandiego",
    "uci": "ucirvine",
    "ucla": "ucla",
    "lmu": "loyolamarymount",
    "loyolamarymountca": "loyolamarymount",
    "dbu": "dallasbaptist",
    "smu": "southernmethodist",
    "vcu": "virginiacommonwealth",
    "umass": "massachusetts",
    "unlv": "nevadalasvegas",
    "utsa": "texassanantonio",
    "usf": "southflorida",
    "fgcu": "floridagulfcoast",
    "calbaptist": "californiabaptist",
    "cbu": "californiabaptist",
    "uscupstate": "southcarolinaupstate",
    "csufullerton": "calstfullerton",
    "fullerton": "calstfullerton",
    "csun": "calstnorthridge",
    "longbeach": "longbeachst",
    "uncw": "uncwilmington",
    "northcarolinawilmington": "uncwilmington",
    "uncg": "uncgreensboro",
    "northcarolinagreensboro": "uncgreensboro",
    "northcarolinaasheville": "uncasheville",
    "utrgv": "texasriograndevalley",
    "etsu": "easttennesseest",
    "mtsu": "middletennesseest",
    "ul": "louisiana",
    "louisianalafayette": "louisiana",
    "ullafayette": "louisiana",
    "ulm": "louisianamonroe",
    "sfa": "stephenfaustin",
    "uab": "alabamabirmingham",
    "uic": "illinoischicago",
    "ualr": "littlerock",
    "arkansaslittlerock": "littlerock",
    "siue": "southernillinoisedwardsville",
    "southernillinoisunivedwardsville": "southernillinoisedwardsville",
    "marylandcollegepark": "maryland",
    "texasam": "texasam",
    "tamu": "texasam",
    "txst": "texasst",
    "texasstsanmarcos": "texasst",
    "kstate": "kansasst",
    "okst": "oklahomast",
    "osu": "oklahomast",
    "msst": "mississippist",
    "missst": "mississippist",
    "ttu": "texastech",
    "wvu": "westvirginia",
    "jmu": "jamesmadison",
    "ecu": "eastcarolina",
    "uga": "georgia",
    "uk": "kentucky",
    "uva": "virginia",
    "ou": "oklahoma",
    "gcu": "grandcanyon",
    "unf": "northflorida",
    "fsu": "floridast",
    "wku": "westernkentucky",
    "nku": "northernkentucky",
    "ucr": "ucriverside",
    "ucdavis": "ucdavis",
    "sjsu": "sanjosest",
    "sdsu": "sandiegost",
    "usd": "sandiego",
    "cal": "california",
    "berkeley": "california",
    "ucberkeley": "california",
    "stmarysca": "stmarys",
    "stmaryscollegeofcalifornia": "stmarys",
    "stjohnsny": "stjohns",
    "miamioh": "miamiohio",
    "vmi": "virginiamilitary",
    "virginiamilitaryinstitute": "virginiamilitary",
    "citadel": "citadel",
    "thecitadel": "citadel",
    "army": "army",
    "armywestpoint": "army",
    "navy": "navy",
    "usnavalacademy": "navy",
    "airforce": "airforce",
    "usafa": "airforce",
    # Schools Trackman spells with "State" and 6-4-3 or the boards without.
    "austinpeay": "austinpeayst",
    "bowlinggreen": "bowlinggreenst",
    "floridasouthwestern": "floridasouthwesternst",
    "grambling": "gramblingst",
    "mcneese": "mcneesest",
    "middletennessee": "middletennesseest",
    "nicholls": "nichollsst",
    "northcarolinaat": "northcarolinaatst",
    "samhouston": "samhoustonst",
    # Campus qualifiers.
    "marylandpark": "maryland",
    "indianabloomington": "indiana",
    "hawaiimanoa": "hawaii",
    "californiasandiego": "ucsandiego",
    "unccharlotte": "charlotte",
    "northcarolinacharlotte": "charlotte",
    "southernmiss": "southernmississippi",
    "usm": "southernmississippi",
}


def normalize_school(name):
    """Reduce a school name to a comparable key ('NC State' -> 'northcarolinast')."""
    if not name:
        return ""
    s = str(name).lower().strip()
    s = s.replace("&", " ")
    s = re.sub(r"\(([^)]*)\)", r" \1 ", s)  # "Saint Mary's (CA)" -> "saint mary's ca"
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bst\.", "st", s)
    s = re.sub(r"\bstate\b", "st", s)
    s = re.sub(r"\buniv\.?\b", "university", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w for w in s.split() if w not in _STOPWORDS]
    key = "".join(words)
    return SCHOOL_ALIASES.get(key, key)


def normalize_person_name(name):
    """Comparable key for a person's name: lowercase, no punctuation or suffixes."""
    if not name:
        return ""
    s = str(name).lower().replace(".", "").replace("'", "").replace("-", " ").replace(",", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return " ".join(s.split())


def schools_match(a, b):
    ka, kb = normalize_school(a), normalize_school(b)
    return bool(ka) and ka == kb


def ranked_school_keys(player):
    """Schools a player's rankings tie him to: ranking school plus HS commitment."""
    from overslot import models

    keys = set()
    for school, commitment in models.PlayerRanking.objects.filter(player=player).values_list(
        "school", "commitment"
    ):
        for value in (school, commitment):
            k = normalize_school(value)
            if k:
                keys.add(k)
    return keys


def season_school_keys(player, season_year, exclude_source=None):
    """Teams another stat source already puts this player at in this season."""
    from overslot import models

    keys = set()
    year = str(season_year)
    if exclude_source != "trackman":
        for school in models.PlayerStatSeason.objects.filter(
            player=player, year=year, level="College"
        ).values_list("school", flat=True):
            k = normalize_school(school)
            if k:
                keys.add(k)
    if exclude_source != "643":
        for team in models.Player643StatSeason.objects.filter(player=player, year=year).values_list(
            "team_name", flat=True
        ):
            k = normalize_school(team)
            if k:
                keys.add(k)
    return keys


def team_fits_player(player, team, season_year=None, source=None):
    """
    True when `team` is consistent with what we already know about `player`:
    a ranking school or commitment, an accepted StatTeamLink, or (when we know
    the season) the team another stat source has for him that same season.
    """
    from overslot import models

    key = normalize_school(team)
    if not key:
        return False
    links = models.StatTeamLink.objects.filter(player=player, team_key=key)
    if links.filter(status=models.StatTeamLink.REJECTED).exists():
        return False
    if links.filter(status=models.StatTeamLink.ACCEPTED).exists():
        return True
    if key in ranked_school_keys(player):
        return True
    if season_year is not None and key in season_school_keys(player, season_year, exclude_source=source):
        return True
    if source != "643" and key in career_643_keys(player):
        return True
    return False


def career_643_keys(player):
    """
    Every team 6-4-3 lists for this player. 6-4-3 maps its players to our
    UUIDs, so its career history is our best record of transfers.
    """
    from overslot import models

    return {
        normalize_school(t)
        for t in models.Player643StatSeason.objects.filter(player=player).values_list("team_name", flat=True)
        if t
    }


def follow_merges(player):
    """Return the surviving player if `player` was merged into another."""
    from overslot import models

    seen = set()
    while player is not None and not player.active and player.pk not in seen:
        seen.add(player.pk)
        decision = (
            models.DuplicateDecision.objects.filter(decision="merged", primary_player__isnull=False)
            .filter(Q(player1=player) | Q(player2=player))
            .exclude(primary_player=player)
            .select_related("primary_player")
            .first()
        )
        if not decision:
            break
        player = decision.primary_player
    return player


def name_candidates(name, debug=False, stdout=None):
    """Active players this name could be. Exact normalized-name matches first."""
    from overslot import models, utils

    key = normalize_person_name(name)
    if not key:
        return []
    exact = [
        p
        for p in models.Player.objects.filter(active=True, name__iexact=name.strip())
    ]
    if not exact:
        last = key.split()[-1]
        exact = [
            p
            for p in models.Player.objects.filter(active=True, name__icontains=last)
            if normalize_person_name(p.name) == key
        ]
    if exact:
        return exact
    fuzzy = utils.fuzzy_find_player(name, debug=debug, stdout=stdout)
    return [fuzzy] if fuzzy else []


def queue_link(player, name, team, season_year, source, reason):
    """Create or refresh a pending StatTeamLink. Decided links are left alone."""
    from overslot import models

    name_key = normalize_person_name(name)
    team_key = normalize_school(team)
    if not name_key or not team_key:
        return None
    decided = (
        models.StatTeamLink.objects.filter(player=player, team_key=team_key)
        .exclude(status=models.StatTeamLink.PENDING)
        .first()
    )
    if decided:
        return decided
    link, created = models.StatTeamLink.objects.get_or_create(
        name_key=name_key,
        team_key=team_key,
        player=player,
        defaults={
            "raw_name": name,
            "raw_team": team,
            "status": models.StatTeamLink.PENDING,
            "reason": reason,
        },
    )
    if link.status != models.StatTeamLink.PENDING:
        return link
    changed = created
    entry = f"{source}:{season_year}"
    seasons = list(link.seasons or [])
    if entry not in seasons:
        seasons.append(entry)
        link.seasons = sorted(seasons)
        changed = True
    if reason and link.reason != reason and reason == models.StatTeamLink.REASON_CONFLICT:
        link.reason = reason
        changed = True
    if changed:
        link.save()
    return link


def resolve_college_stat_player(name, season_year, team, source, debug=False, stdout=None, queue=True):
    """
    Find the Overslot player a college stat row belongs to, or None.

    `team` is the row's school. A row whose name matches but whose team doesn't
    fit the player is held back (returns None) and, when `queue` is set, a
    pending StatTeamLink is created for review.
    """
    from overslot import models, utils

    def log(msg):
        if debug and stdout:
            stdout.write(msg)

    name = utils.normalize_sheet_player_name(name)
    name_key = normalize_person_name(name)
    team_key = normalize_school(team)

    if name_key and team_key:
        links = models.StatTeamLink.objects.filter(name_key=name_key, team_key=team_key).select_related("player")
        accepted = [l for l in links if l.status == models.StatTeamLink.ACCEPTED]
        if accepted:
            player = follow_merges(accepted[0].player)
            if player is not None and player.active:
                log(f"[match] '{name}' at '{team}' -> '{player.name}' (reviewed link)")
                return player
        # A rejection means "this player's stats never came from this team",
        # whatever spelling of the name the source used.
        rejected = set(
            models.StatTeamLink.objects.filter(
                team_key=team_key, status=models.StatTeamLink.REJECTED
            ).values_list("player_id", flat=True)
        )
    else:
        rejected = set()

    candidates = [
        p
        for p in name_candidates(name, debug=debug, stdout=stdout)
        if p.pk not in rejected and utils.player_accepts_college_season(p, season_year)
    ]
    if not candidates:
        log(f"[match] No player for '{name}' at '{team}' ({season_year})")
        return None

    if not team_key:
        # No team on the row: only a single unambiguous name match is safe.
        if len(candidates) == 1:
            return candidates[0]
        log(f"[match] '{name}' has no team and {len(candidates)} candidates; skipping")
        return None

    fits = [p for p in candidates if team_fits_player(p, team, season_year, source=source)]
    if len(fits) == 1:
        log(f"[match] '{name}' at '{team}' -> '{fits[0].name}' (school agrees)")
        return fits[0]

    if queue:
        for p in candidates:
            queue_link(p, name, team, season_year, source, models.StatTeamLink.REASON_UNKNOWN_SCHOOL)
    log(
        f"[match] HOLD '{name}' at '{team}' ({season_year}): "
        f"{len(candidates)} name match(es), {len(fits)} with that school; queued for review"
    )
    return None
