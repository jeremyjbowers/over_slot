from django.test import SimpleTestCase

from overslot.management.commands.sheet_load_mocks import resolve_mock_rank, to_int_or_none


class ResolveMockRankTestCase(SimpleTestCase):
    def test_prefers_explicit_rank(self):
        self.assertEqual(
            resolve_mock_rank({"rank": "3", "mock_pick_number": "7"}),
            3,
        )

    def test_falls_back_to_mock_pick_number_when_rank_missing(self):
        self.assertEqual(
            resolve_mock_rank({"mock_pick_number": "12"}),
            12,
        )

    def test_falls_back_when_rank_blank(self):
        self.assertEqual(
            resolve_mock_rank({"rank": "", "mock_pick_number": "4"}),
            4,
        )

    def test_none_when_neither_present(self):
        self.assertIsNone(resolve_mock_rank({"name": "Ada"}))
        self.assertIsNone(resolve_mock_rank(None))

    def test_to_int_or_none_handles_sheet_floats(self):
        self.assertEqual(to_int_or_none("1.0"), 1)
        self.assertIsNone(to_int_or_none("n/a"))
