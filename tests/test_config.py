import os
import unittest
from unittest.mock import patch

from config import load_config


class ConfigTest(unittest.TestCase):
    def test_blank_title_enables_detected_model_title(self):
        values = {
            "CARD_TITLE": "",
            "LOCAL_SERVER_NAME": "5090服务器",
        }
        with patch.dict(os.environ, values, clear=True):
            config = load_config(require_dingtalk=False)
        self.assertEqual("", config.card_title)
        self.assertEqual("5090服务器", config.server_name)

    def test_rejects_invalid_alert_thresholds(self):
        values = {
            "GPU_AVAILABLE_HIGH_PERCENT": "20",
            "GPU_AVAILABLE_LOW_PERCENT": "70",
        }
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaises(ValueError):
                load_config(require_dingtalk=False)


if __name__ == "__main__":
    unittest.main()
