import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import tokenorb_core as core
except ModuleNotFoundError:
    core = None


class TokenOrbCoreTests(unittest.TestCase):
    def require_core(self):
        self.assertIsNotNone(core, "Linux TokenOrb core has not been implemented")
        return core

    def test_parser_supports_camel_case_rate_limits_and_selects_display_window(self):
        module = self.require_core()
        snapshot = module.parse_rate_limits(
            {
                "limitId": "codex",
                "planType": "plus",
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 1_790_000_000,
                },
                "secondary": {
                    "usedPercent": 100,
                    "windowDurationMins": 10080,
                    "resetsAt": 1_790_100_000,
                },
                "credits": {"hasCredits": False, "balance": "0"},
            },
            source="test",
            is_live=True,
        )

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.plan_type, "plus")
        self.assertEqual(snapshot.orb_display_window.window_minutes, 10080)
        self.assertEqual(snapshot.orb_display_window.remaining_percent, 0)

    def test_find_rate_limits_prefers_codex_limit_id(self):
        module = self.require_core()
        value = {
            "result": {
                "rateLimitsByLimitId": {
                    "other": {"primary": {"usedPercent": 10}},
                    "codex": {"primary": {"usedPercent": 20}},
                }
            }
        }

        self.assertEqual(module.find_rate_limits(value)["primary"]["usedPercent"], 20)

    def test_local_reader_returns_latest_token_count_event(self):
        module = self.require_core()
        with tempfile.TemporaryDirectory() as temp_dir:
            rollout = Path(temp_dir) / "2026" / "rollout-2026-09-22.jsonl"
            rollout.parent.mkdir(parents=True)
            events = [
                {
                    "timestamp": "2026-09-22T01:00:00Z",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {
                                "used_percent": 40,
                                "window_minutes": 300,
                            }
                        },
                    },
                },
                {
                    "timestamp": "2026-09-22T02:00:00Z",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {
                                "used_percent": 55,
                                "window_minutes": 300,
                            }
                        },
                    },
                },
            ]
            rollout.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )

            snapshot = module.LocalSnapshotReader(Path(temp_dir)).latest()

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.primary.used_percent, 55)
        self.assertEqual(snapshot.captured_at, datetime(2026, 9, 22, 2, tzinfo=timezone.utc))

    def test_rpc_request_shapes_match_codex_app_server(self):
        module = self.require_core()
        self.assertEqual(
            module.initialize_request("TokenOrb", "1.6.0"),
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "TokenOrb",
                        "title": "TokenOrb",
                        "version": "1.6.0",
                    }
                },
            },
        )
        self.assertEqual(
            module.rate_limits_request(10),
            {"method": "account/rateLimits/read", "id": 10},
        )


if __name__ == "__main__":
    unittest.main()
