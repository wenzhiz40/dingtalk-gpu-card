import unittest

from card_data import ServerReport, build_card_data, build_cluster_card_data
from gpu_collector import GPU, GPUUser


class CardDataTest(unittest.TestCase):
    def test_privacy_and_status(self):
        gpus = [
            GPU(0, "RTX 5090", 0, 65, 32768, 36, 19),
            GPU(1, "RTX 5090", 91, 9000, 32768, 70, 210),
        ]
        result = build_card_data("5090", gpus, 10, 1024)
        self.assertEqual(["content"], list(result))
        self.assertIn("1 张低占用，1 张使用中", result["content"])
        self.assertIn("低占用（可能空闲）", result["content"])
        self.assertIn("使用中", result["content"])
        self.assertNotIn("PID", result["content"])
        self.assertIn("未检测到可识别的计算任务", result["content"])

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
        self.assertIn("时间均为北京时间（UTC+8）", content)

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
        self.assertIn("NVIDIA GeForce RTX 5090", content)
        self.assertIn("掉线（疑似关机）", content)
        self.assertIn("最近在线", content)


if __name__ == "__main__":
    unittest.main()
