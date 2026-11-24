"""
Stable player IDs for Joe's ranking sheets.

Each ranking tab carries an `overslot_id` column. The loader fills it with the
player's UUID, and Joe copies that cell when a player moves to another tab (for
example 2024 High School to 2025 College), so the move keeps the same player
even when the school and position change.

Rules, in order:
1. A row with an ID uses that player, after following merges to the survivor.
   The ID is ignored (and reported) when it's unknown, when the sheet name
   doesn't look like the player's name, or when an earlier row in the same tab
   already used it.
2. A row without a usable ID falls back to name + position, the loader's old
   behavior, but never reuses a player an earlier row in the tab already took.
   Two different "Ryan Brown, OF" rows in one tab become two players.
3. After the load, the resolved IDs are written back to the sheet, so merged
   players' IDs are rewritten to the survivor's.
"""
import uuid as uuid_lib

from thefuzz import fuzz

from overslot.stat_identity import follow_merges, normalize_person_name

OVERSLOT_ID_HEADER = "overslot_id"
SHEETS_WRITE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def parse_overslot_id(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return uuid_lib.UUID(s)
    except ValueError:
        return None


def names_compatible(sheet_name, player_name):
    """
    True when a sheet name plausibly names this player. Last names must agree
    (allowing small typos); first names can differ (Jake/Jacob, AJ/A.J.).
    """
    a, b = normalize_person_name(sheet_name), normalize_person_name(player_name)
    if not a or not b:
        return False
    if a == b:
        return True
    last_a, last_b = a.split()[-1], b.split()[-1]
    if last_a == last_b:
        return True
    return fuzz.ratio(last_a, last_b) >= 85 and fuzz.token_sort_ratio(a, b) >= 85


class TabResolver:
    """Resolves the rows of one sheet tab to players. Use one per tab."""

    def __init__(self, tab_label=""):
        self.tab_label = tab_label
        self.claimed = {}  # player pk -> sheet row number
        self.issues = []
        self.counts = {"id": 0, "id_merged": 0, "name": 0, "created": 0, "split": 0}

    def _issue(self, row_number, message):
        self.issues.append(f"{self.tab_label} row {row_number}: {message}")

    def _claim(self, player, row_number):
        self.claimed[player.pk] = row_number
        return player

    def resolve(self, row_number, row):
        """Return (player, created) for a sheet row."""
        from overslot import models

        name = str(row.get("name", "")).strip()
        position = row.get("position", "")

        raw_id = row.get(OVERSLOT_ID_HEADER)
        parsed = parse_overslot_id(raw_id)
        if raw_id and str(raw_id).strip() and parsed is None:
            self._issue(row_number, f"'{raw_id}' isn't a valid overslot_id; matched by name instead")
        if parsed is not None:
            found = models.Player.objects.filter(uuid=parsed).first()
            if found is None:
                self._issue(row_number, f"overslot_id {parsed} doesn't exist; matched by name instead")
            else:
                player = follow_merges(found)
                if not names_compatible(name, player.name):
                    self._issue(
                        row_number,
                        f"overslot_id belongs to {player.name}, not {name}; matched by name instead",
                    )
                elif player.pk in self.claimed:
                    self._issue(
                        row_number,
                        f"overslot_id for {player.name} is also on row {self.claimed[player.pk]}; "
                        "matched by name instead",
                    )
                else:
                    self.counts["id_merged" if player.pk != found.pk else "id"] += 1
                    return self._claim(player, row_number), False

        candidates = []
        seen = set()
        for p in models.Player.objects.filter(name=name, position=position).order_by("-active", "created"):
            survivor = follow_merges(p)
            if survivor.pk in seen:
                continue
            seen.add(survivor.pk)
            candidates.append(survivor)

        free = [p for p in candidates if p.pk not in self.claimed]
        if free:
            self.counts["name"] += 1
            return self._claim(free[0], row_number), False

        player = models.Player.objects.create(name=name, position=position)
        self.counts["created"] += 1
        if candidates:
            self.counts["split"] += 1
            rows = ", ".join(str(self.claimed[p.pk]) for p in candidates)
            self._issue(
                row_number,
                f"{name} ({position}) is also on row {rows}; created a separate player. "
                "If they're the same person, delete one row.",
            )
        return self._claim(player, row_number), True


def column_letter(index):
    """0-based column index to A1 letters (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def read_tab(sheet_id, tab, service=None):
    """
    Read a tab keeping sheet row numbers. Returns (header, [(row_number, row_dict)]).
    Row 1 is the header, so data starts at row 2.
    """
    from overslot import utils

    if service is None:
        service = sheets_service(write=False)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=utils.sheet_tab_a1_range(tab, "A:AZ"))
        .execute()
    )
    values = result.get("values") or []
    if not values:
        return [], []
    header = [str(h).strip() for h in values[0]]
    rows = []
    for offset, raw in enumerate(values[1:], start=2):
        rows.append((offset, dict(zip(header, raw))))
    return header, rows


def sheets_service(write=False):
    from googleapiclient.discovery import build

    from overslot import utils

    scopes = SHEETS_WRITE_SCOPES if write else ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    return build("sheets", "v4", credentials=utils.get_google_creds(scopes), cache_discovery=False)


def write_ids(sheet_id, tab, header, assignments, service=None):
    """
    Write player UUIDs into the tab's overslot_id column.

    `assignments` maps sheet row number -> (sheet name as loaded, uuid string).
    Before writing, the name column is read again, and any row whose name has
    changed since the load (Joe sorted or inserted rows mid-load) is skipped,
    so an ID never lands on the wrong player. Cells that already hold the
    right ID aren't rewritten.

    Returns a dict of counts: written, unchanged, skipped_moved.
    """
    from overslot import utils

    if service is None:
        service = sheets_service(write=True)

    if "name" not in header:
        raise ValueError(f"{tab} has no name column")
    name_col = column_letter(header.index("name"))
    if OVERSLOT_ID_HEADER in header:
        id_col_index = header.index(OVERSLOT_ID_HEADER)
        needs_header = False
    else:
        id_col_index = len(header)
        needs_header = True
    id_col = column_letter(id_col_index)

    current = (
        service.spreadsheets()
        .values()
        .batchGet(
            spreadsheetId=sheet_id,
            ranges=[
                utils.sheet_tab_a1_range(tab, f"{name_col}:{name_col}"),
                utils.sheet_tab_a1_range(tab, f"{id_col}:{id_col}"),
            ],
        )
        .execute()
    )
    ranges = current.get("valueRanges") or [{}, {}]
    name_values = ranges[0].get("values") or []
    id_values = ranges[1].get("values") or []

    def cell(values, row_number):
        i = row_number - 1
        if i < len(values) and values[i]:
            return str(values[i][0]).strip()
        return ""

    if not needs_header and cell(id_values, 1) != OVERSLOT_ID_HEADER:
        raise ValueError(f"{tab}: column {id_col} header changed since the load; not writing IDs")
    if needs_header and cell(id_values, 1):
        raise ValueError(f"{tab}: column {id_col} is no longer empty; not writing IDs")

    data = []
    counts = {"written": 0, "unchanged": 0, "skipped_moved": 0}
    if needs_header:
        data.append({"range": utils.sheet_tab_a1_range(tab, f"{id_col}1"), "values": [[OVERSLOT_ID_HEADER]]})
    for row_number, (loaded_name, player_id) in sorted(assignments.items()):
        if cell(name_values, row_number) != str(loaded_name).strip():
            counts["skipped_moved"] += 1
            continue
        if cell(id_values, row_number) == player_id:
            counts["unchanged"] += 1
            continue
        data.append({"range": utils.sheet_tab_a1_range(tab, f"{id_col}{row_number}"), "values": [[player_id]]})
        counts["written"] += 1

    if data:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id, body={"valueInputOption": "RAW", "data": data}
        ).execute()
    return counts
