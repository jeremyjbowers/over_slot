from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from overslot import models, sheet_identity


class FakeSheet:
    """In-memory stand-in for the Sheets v4 values API, one tab."""

    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.updates = []

    def _col(self, letters):
        n = 0
        for ch in letters:
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    def _column(self, a1):
        col = a1.split("!")[1].split(":")[0]
        i = self._col(col)
        return [[r[i]] if i < len(r) and r[i] != "" else [] for r in self.rows]

    # service.spreadsheets().values().<method>(...).execute()
    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId, range):
        return mock.Mock(execute=lambda: {"values": self.rows})

    def batchGet(self, spreadsheetId, ranges):
        return mock.Mock(execute=lambda: {"valueRanges": [{"values": self._column(r)} for r in ranges]})

    def batchUpdate(self, spreadsheetId, body):
        def run():
            for item in body["data"]:
                cell = item["range"].split("!")[1]
                letters = "".join(c for c in cell if c.isalpha())
                row = int("".join(c for c in cell if c.isdigit()))
                col = self._col(letters)
                while len(self.rows) < row:
                    self.rows.append([])
                r = self.rows[row - 1]
                while len(r) <= col:
                    r.append("")
                r[col] = item["values"][0][0]
                self.updates.append((cell, item["values"][0][0]))
            return {}

        return mock.Mock(execute=run)


HEADER = ["rank", "name", "position", "school", "class"]


class TabResolverTests(TestCase):
    def test_id_wins_over_name_and_position(self):
        hs = models.Player.objects.create(name="Rett Johnson", position="SS", school="Some HS")
        models.Player.objects.create(name="Rett Johnson", position="OF", school="South Alabama")
        r = sheet_identity.TabResolver("2027 College")
        p, created = r.resolve(2, {"name": "Rett Johnson", "position": "OF", "overslot_id": str(hs.pk)})
        self.assertEqual(p, hs)
        self.assertFalse(created)

    def test_merged_id_follows_to_survivor(self):
        keeper = models.Player.objects.create(name="AJ Evasco", position="C")
        gone = models.Player.objects.create(name="A.J. Evasco", position="C", active=False)
        models.DuplicateDecision.objects.create(
            player1=keeper, player2=gone, decision="merged", primary_player=keeper
        )
        r = sheet_identity.TabResolver("t")
        p, _ = r.resolve(2, {"name": "A.J. Evasco", "position": "C", "overslot_id": str(gone.pk)})
        self.assertEqual(p, keeper)
        self.assertEqual(r.counts["id_merged"], 1)

    def test_id_for_a_different_name_is_ignored(self):
        other = models.Player.objects.create(name="Nathan Hall", position="RHP")
        r = sheet_identity.TabResolver("t")
        p, created = r.resolve(5, {"name": "Ryan Brown", "position": "OF", "overslot_id": str(other.pk)})
        self.assertNotEqual(p, other)
        self.assertTrue(created)
        self.assertIn("belongs to Nathan Hall", r.issues[0])

    def test_nickname_first_name_still_trusts_id(self):
        p0 = models.Player.objects.create(name="Jacob Smith", position="OF")
        r = sheet_identity.TabResolver("t")
        p, _ = r.resolve(2, {"name": "Jake Smith", "position": "OF", "overslot_id": str(p0.pk)})
        self.assertEqual(p, p0)

    def test_duplicate_id_in_tab_falls_back_for_second_row(self):
        p0 = models.Player.objects.create(name="Ryan Brown", position="OF")
        r = sheet_identity.TabResolver("t")
        first, _ = r.resolve(2, {"name": "Ryan Brown", "position": "OF", "overslot_id": str(p0.pk)})
        second, created = r.resolve(9, {"name": "Ryan Brown", "position": "OF", "overslot_id": str(p0.pk)})
        self.assertEqual(first, p0)
        self.assertNotEqual(second, p0)
        self.assertTrue(created)
        self.assertTrue(any("also on row 2" in i for i in r.issues))

    def test_same_name_twice_in_tab_without_ids_is_two_players(self):
        p0 = models.Player.objects.create(name="Ryan Brown", position="OF")
        r = sheet_identity.TabResolver("t")
        a, _ = r.resolve(2, {"name": "Ryan Brown", "position": "OF"})
        b, created = r.resolve(3, {"name": "Ryan Brown", "position": "OF"})
        self.assertEqual(a, p0)
        self.assertNotEqual(b, p0)
        self.assertEqual(r.counts["split"], 1)

        # The next load (still no IDs) reuses both players instead of creating a third.
        r2 = sheet_identity.TabResolver("t")
        a2, _ = r2.resolve(2, {"name": "Ryan Brown", "position": "OF"})
        b2, created2 = r2.resolve(3, {"name": "Ryan Brown", "position": "OF"})
        self.assertEqual({a2, b2}, {a, b})
        self.assertFalse(created2)

    def test_unknown_or_garbage_id_falls_back_to_name(self):
        p0 = models.Player.objects.create(name="Ryan Brown", position="OF")
        r = sheet_identity.TabResolver("t")
        p, _ = r.resolve(2, {"name": "Ryan Brown", "position": "OF", "overslot_id": "not-a-uuid"})
        self.assertEqual(p, p0)
        p, _ = sheet_identity.TabResolver("t").resolve(
            2, {"name": "Ryan Brown", "position": "OF", "overslot_id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(p, p0)


class WriteIdsTests(TestCase):
    def test_adds_header_and_writes_ids(self):
        sheet = FakeSheet([HEADER, ["1", "Rett Johnson", "OF"], ["2", "Ryan Brown", "OF"]])
        counts = sheet_identity.write_ids(
            "sid", "2027 College", HEADER, {2: ("Rett Johnson", "u1"), 3: ("Ryan Brown", "u2")}, service=sheet
        )
        self.assertEqual(counts["written"], 2)
        self.assertEqual(sheet.rows[0][5], "overslot_id")
        self.assertEqual(sheet.rows[1][5], "u1")
        self.assertEqual(sheet.rows[2][5], "u2")

    def test_skips_rows_that_moved_and_unchanged_cells(self):
        header = HEADER + ["overslot_id"]
        sheet = FakeSheet([header, ["1", "Ryan Brown", "OF", "", "", "u2"], ["2", "Rett Johnson", "OF"]])
        # Loaded order was Rett, Ryan; Joe swapped them before the write.
        counts = sheet_identity.write_ids(
            "sid", "t", header, {2: ("Rett Johnson", "u1"), 3: ("Ryan Brown", "u2")}, service=sheet
        )
        self.assertEqual(counts, {"written": 0, "unchanged": 0, "skipped_moved": 2})
        self.assertEqual(sheet.updates, [])

        counts = sheet_identity.write_ids(
            "sid", "t", header, {2: ("Ryan Brown", "u2"), 3: ("Rett Johnson", "u1")}, service=sheet
        )
        self.assertEqual(counts, {"written": 1, "unchanged": 1, "skipped_moved": 0})
        self.assertEqual(sheet.updates, [("F3", "u1")])

    def test_refuses_when_target_column_got_a_header(self):
        sheet = FakeSheet([HEADER + ["notes"], ["1", "Rett Johnson", "OF"]])
        with self.assertRaises(ValueError):
            sheet_identity.write_ids("sid", "t", HEADER, {2: ("Rett Johnson", "u1")}, service=sheet)

    def test_column_letters(self):
        self.assertEqual(
            [sheet_identity.column_letter(i) for i in (0, 25, 26, 27, 51)], ["A", "Z", "AA", "AB", "AZ"]
        )


class LoaderIntegrationTests(TestCase):
    def run_loader(self, sheet, *extra):
        out, err = StringIO(), StringIO()
        read_tab, write_ids = sheet_identity.read_tab, sheet_identity.write_ids
        with mock.patch.object(
            sheet_identity, "read_tab", side_effect=lambda sid, tab: read_tab(sid, tab, service=sheet)
        ), mock.patch.object(
            sheet_identity, "write_ids", side_effect=lambda sid, tab, h, a: write_ids(sid, tab, h, a, service=sheet)
        ):
            call_command("sheet_load_rankings", "2027 College", *extra, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_load_writes_ids_and_reload_uses_them(self):
        hs = models.Player.objects.create(name="Rett Johnson", position="SS", school="Some HS")
        sheet = FakeSheet(
            [
                HEADER,
                ["1", "Rett Johnson", "OF", "NC State", "C"],
                ["2", "Ryan Brown", "OF", "Texas", "C"],
                ["3", "Ryan Brown", "OF", "Baylor", "C"],
            ]
        )
        out, err = self.run_loader(sheet)
        self.assertEqual(err, "")
        self.assertEqual(sheet.rows[0][5], "overslot_id")
        ids = [sheet.rows[i][5] for i in (1, 2, 3)]
        self.assertEqual(len(set(ids)), 3)
        # Joe moves the HS player's ID onto the college row; the next load attaches the HS player.
        sheet.rows[1][5] = str(hs.pk)
        out, err = self.run_loader(sheet)
        ranking = models.Ranking.objects.get(year="2027", draft_level="College", is_mock_draft=False)
        ranked = set(
            models.PlayerRanking.objects.filter(ranking=ranking, active=True).values_list("player_id", flat=True)
        )
        self.assertIn(hs.pk, ranked)
        self.assertEqual(len(ranked), 3)
        self.assertIn("3 by overslot_id", out)

    def test_no_write_ids_leaves_sheet_alone(self):
        sheet = FakeSheet([HEADER, ["1", "Rett Johnson", "OF", "NC State", "C"]])
        self.run_loader(sheet, "--no-write-ids")
        self.assertEqual(sheet.updates, [])
