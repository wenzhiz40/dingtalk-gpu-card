from types import SimpleNamespace
import unittest

from app import _availability_events, _card_title, _mark_events_sent
from card_data import ServerReport
from gpu_collector import GPU


class AvailabilityAlertTest(unittest.TestCase):
    def test_title_uses_detected_gpu_model(self):
        config = SimpleNamespace(card_title="", server_name="错误的旧名称")
        gpu = GPU(0, "NVIDIA GeForce RTX 3090", 1, 100, 24576, 40, 50)
        reports = [ServerReport("3090服务器", "online", [gpu], "now", "now")]
        self.assertEqual("NVIDIA GeForce RTX 3090 GPU 状态", _card_title(config, reports))

    def test_high_then_middle_then_low_sends_once(self):
        config = SimpleNamespace(
            availability_alerts_enabled=True,
            availability_high_percent=70,
            availability_low_percent=20,
        )
        state = {}

        def report(utilization):
            gpu = GPU(0, "RTX 3090", utilization, 100, 24576, 40, 50)
            return [ServerReport("3090服务器", "online", [gpu], "now", "now")]

        self.assertEqual([], _availability_events(config, state, report(75)))
        self.assertEqual([], _availability_events(config, state, report(45)))
        events = _availability_events(config, state, report(12))
        self.assertEqual(1, len(events))
        _mark_events_sent(state, events)
        self.assertEqual([], _availability_events(config, state, report(10)))


if __name__ == "__main__":
    unittest.main()
