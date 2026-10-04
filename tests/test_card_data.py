import unittest

from card_data import (
    ServerReport,
    build_card_data,
    build_cluster_card_data,
    short_model_name,
)
from gpu_collector import GPU, GPUUser


class CardDataTest(unittest.TestCase):
    def test_privacy_and_status(self):
        gpus = [
            GPU(0, "RTX 5090", 0, 65, 32768, 36, 19),
            GPU(1, "RTX 5090", 91, 9000, 32768, 70, 210),
        ]
        result = build_card_data("5090", gpus, 10, 1024)
        self.assertEqual(["content"], list(result))
        self.assertIn("1 张低占用 · 1 张使用中", result["content"])
        self.assertIn("低占用", result["content"])
        self.assertNotIn("可能空闲", result["content"])
        self.assertNotIn("检测到：", result["content"])
        self.assertNotIn("1 台在线", result["content"])
        self.assertIn("使用中", result["content"])
        self.assertNotIn("PID", result["content"])
        self.assertIn("计算用户：无可识别任务", result["content"])
        self.assertIn("> ① 使用中：", result["content"])
        self.assertIn("> ④ 离线：", result["content"])
        self.assertNotIn("**状态判断", result["content"])

    def test_only_aggregated_compute_users_are_rendered(self):
        gpu = GPU(
            0,
            "NVIDIA GeForce RTX 5090",
            75,
            9000,
            32768,
            70,
            250,
            (GPUUser("userA", 4096), GPUUser("userB", 2048)),
        )
        content = build_card_data("5090", [gpu], 10, 1024)["content"]
        self.assertIn("userA **4.0 GiB**", content)
        self.assertIn("userB **2.0 GiB**", content)
        self.assertNotIn("+0800", content)
        self.assertIn("北京时间（UTC+8）", content)
        self.assertIn("# 5090 GPU 状态", content)
        self.assertNotIn("NVIDIA GeForce RTX 5090", content)

    def test_short_model_name(self):
        self.assertEqual("5090", short_model_name("NVIDIA GeForce RTX 5090"))
        self.assertEqual("A100", short_model_name("NVIDIA A100-PCIE-40GB"))
        self.assertEqual("L40S", short_model_name("NVIDIA L40S"))

    def test_mixed_models_are_identified_per_gpu(self):
        gpus = [
            GPU(0, "NVIDIA GeForce RTX 5090", 0, 0, 32768, 35, 20),
            GPU(1, "NVIDIA L40S", 0, 0, 49152, 35, 20),
        ]
        content = build_card_data("混合节点", gpus, 10, 1024)["content"]
        self.assertIn("GPU 0 · 5090 · 🟢 低占用", content)
        self.assertIn("GPU 1 · L40S · 🟢 低占用", content)

    def test_cluster_uses_detected_models_and_shows_offline_server(self):
        reports = [
            ServerReport(
                "计算节点A",
                "online",
                [GPU(0, "NVIDIA GeForce RTX 5090", 0, 65, 32768, 36, 19)],
                "2026-10-04 10:00:00 +0800",
                "2026-10-04 10:00:00 +0800",
            ),
            ServerReport(
                "计算节点B",
                "offline",
                [GPU(0, "NVIDIA GeForce RTX 5090", 0, 0, 32768, 30, 20)],
                "2026-10-04 10:01:00 +0800",
                "2026-10-04 09:59:00 +0800",
                "连接超时；主机可能已关机或网络不可达",
            ),
        ]
        content = build_cluster_card_data("GPU 集群状态", reports, 10, 1024)["content"]
        self.assertIn("1 台在线", content)
        self.assertIn("1 台掉线", content)
        self.assertIn("5090", content)
        self.assertIn("掉线（疑似关机）", content)
        self.assertIn("最近在线", content)


if __name__ == "__main__":
    unittest.main()
