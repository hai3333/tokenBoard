"""主面板关键交互回归；使用内存假数据，不修改用户数据库。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tokenboard.ui import panel as P  # noqa: E402


class StoreStub:
    def summary(self, since_day=None):
        return [{"app": "codex", "total_tokens": 1000, "requests": 2,
                 "input_tokens": 500, "output_tokens": 100,
                 "cache_read_tokens": 400, "cost_usd": 0.3}]

    def speed_stats(self, since_day=None):
        return {}

    def models_by_app(self, since_day=None):
        return {"codex": [{"key": "primary", "name": "primary",
                            "tokens": 800, "cost": 0.2,
                            "input": 400, "output": 80, "cache": 320},
                           {"key": "gpt-6-test", "name": "gpt-6-test",
                            "tokens": 200, "cost": 0.1,
                            "input": 100, "output": 20, "cache": 80}]}

    def daily(self, since_day=None):
        return []


class PanelRegressionTests(unittest.TestCase):
    def setUp(self):
        P._relayout(860, 560)
        self.panel = P.Panel(StoreStub(), None)
        self.panel.width, self.panel.height = 860, 560
        self.panel._load()

    def tearDown(self):
        P._relayout(960, 600)

    def test_search_focus_clear_and_escape(self):
        p = self.panel
        x, y, w, h = p._search_rect()
        p.on_click(x + 30, y + h / 2)
        self.assertTrue(p._search_focus)
        for ch in "codex":
            p.on_char(ch)
        self.assertEqual(p._search_q, "codex")
        p.on_click(x + w - 12, y + h / 2)
        self.assertEqual(p._search_q, "")
        self.assertTrue(p._search_focus)
        p.on_char("x")
        p.on_key(0x1B)
        self.assertEqual(p._search_q, "")
        self.assertFalse(p._search_focus)

    def test_search_finds_collapsed_child_and_keeps_original_state(self):
        p = self.panel
        p._search_q = "gpt-6-test"
        p._load()
        self.assertEqual([r["kind"] for r in p._rows], ["app", "sub"])
        self.assertTrue(p._rows[0]["open"])
        x, y, w, h = p._row_rect(0)
        p.on_click(x + 20, y + h / 2)
        p._load()
        self.assertEqual([r["kind"] for r in p._rows], ["app"])
        self.assertFalse(p._rows[0]["open"])
        p.on_click(x + 20, y + h / 2)
        p._load()
        self.assertEqual(len(p._rows), 2)
        p._search_q = ""
        p._load()
        self.assertEqual([r["kind"] for r in p._rows], ["app"])
        self.assertFalse(p._expanded)

    def test_last_row_is_reachable_and_hidden_rows_do_not_hit(self):
        p = self.panel
        p._rows = [{"kind": "app", "key": str(i)} for i in range(6)]
        p._layout_rows()
        self.assertGreater(p._max_scroll(), 0)
        x = P.CARD_X + 15
        self.assertEqual(p._row_at(x, P.BODY_Y + 5 * P.ROW_MAIN + 2), -1)
        p._scroll = p._max_scroll()
        x, y, w, h = p._row_rect(5)
        self.assertLessEqual(y + h, P.BODY_Y + P.BODY_H - P.TABLE_FOOT_H)
        self.assertEqual(p._row_at(x + 5, y + h / 2), 5)

    def test_quota_search_filters_and_footer_jump_still_works(self):
        p = self.panel
        p._view_idx = 3
        p._quota = [{"provider": "codex", "name": "Codex"},
                    {"provider": "minimax", "name": "MiniMax"}]
        p._search_q = "codex"
        self.assertEqual([q["provider"] for q, _ in p._quota_blocks()], ["codex"])
        hit = []
        p._jump_to_app = hit.append
        p._dot_hit = [("codex", 200, P.FOOT_Y, 50)]
        p.on_click(210, P.FOOT_Y + 5)
        self.assertEqual(hit, ["codex"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
