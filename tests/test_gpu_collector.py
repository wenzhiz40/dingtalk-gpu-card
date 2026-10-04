import subprocess
import unittest
from unittest.mock import patch

from gpu_collector import collect_gpus


class GPUCollectorTest(unittest.TestCase):
    @patch("gpu_collector._process_username", side_effect=lambda pid: {101: "userA", 102: "userA", 201: "userB"}[pid])
    @patch("gpu_collector.subprocess.run")
    def test_fixed_command_and_parse(self, run, _username):
        run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "0, GPU-a, NVIDIA GeForce RTX 2080 Ti, 0, 65, 11264, 36, 19.22\n"
                    "1, GPU-b, NVIDIA GeForce RTX 2080 Ti, 95, 9000, 11264, 70, 210.5\n"
                ),
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="GPU-a, 101, 1024\nGPU-a, 102, 512\nGPU-b, 201, 2048\n",
                stderr="",
            ),
        ]
        gpus = collect_gpus()
        self.assertEqual(2, len(gpus))
        self.assertEqual(11264, gpus[0].memory_total_mib)
        self.assertEqual("userA", gpus[0].users[0].username)
        self.assertEqual(1536, gpus[0].users[0].memory_used_mib)
        args, kwargs = run.call_args_list[0]
        self.assertEqual("/usr/bin/nvidia-smi", args[0][0])
        self.assertFalse(kwargs["shell"])
        self.assertEqual(8, kwargs["timeout"])

if __name__ == "__main__":
    unittest.main()
