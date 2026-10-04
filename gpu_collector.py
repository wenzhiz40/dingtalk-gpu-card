"""Collect privacy-preserving GPU metrics from the local NVIDIA driver."""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
import os
import re
import subprocess

try:
    import pwd
except ImportError:  # Windows supports tests/dry-run but not Linux /proc ownership.
    pwd = None


GPU_QUERY_FIELDS = (
    "index,uuid,name,utilization.gpu,memory.used,memory.total,"
    "temperature.gpu,power.draw"
)
COMPUTE_QUERY_FIELDS = "gpu_uuid,pid,used_memory"
NVIDIA_SMI_COMMAND = [
    "/usr/bin/nvidia-smi",
    f"--query-gpu={GPU_QUERY_FIELDS}",
    "--format=csv,noheader,nounits",
]
COMPUTE_COMMAND = [
    "/usr/bin/nvidia-smi",
    f"--query-compute-apps={COMPUTE_QUERY_FIELDS}",
    "--format=csv,noheader,nounits",
]
_USERNAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class GPUUser:
    username: str
    memory_used_mib: float


@dataclass(frozen=True)
class GPU:
    index: int
    name: str
    utilization: float
    memory_used_mib: float
    memory_total_mib: float
    temperature_c: float
    power_w: float
    users: tuple[GPUUser, ...] = ()


def gpu_to_dict(gpu: GPU) -> dict:
    return {
        "index": gpu.index,
        "name": gpu.name,
        "utilization": gpu.utilization,
        "memory_used_mib": gpu.memory_used_mib,
        "memory_total_mib": gpu.memory_total_mib,
        "temperature_c": gpu.temperature_c,
        "power_w": gpu.power_w,
        "users": [
            {"username": user.username, "memory_used_mib": user.memory_used_mib}
            for user in gpu.users
        ],
    }


def gpu_from_dict(value: dict) -> GPU:
    users = tuple(
        GPUUser(str(item["username"]), float(item["memory_used_mib"]))
        for item in value.get("users", [])
    )
    return GPU(
        index=int(value["index"]),
        name=str(value["name"]),
        utilization=float(value["utilization"]),
        memory_used_mib=float(value["memory_used_mib"]),
        memory_total_mib=float(value["memory_total_mib"]),
        temperature_c=float(value["temperature_c"]),
        power_w=float(value["power_w"]),
        users=users,
    )


def _parse_inventory(output: str) -> tuple[list[GPU], dict[str, int]]:
    gpus: list[GPU] = []
    uuid_to_position: dict[str, int] = {}
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != 8:
            raise RuntimeError(f"nvidia-smi 返回了意外的列数：{len(row)}")
        try:
            uuid = row[1].strip()
            uuid_to_position[uuid] = len(gpus)
            gpus.append(
                GPU(
                    index=int(row[0]),
                    name=row[2].strip(),
                    utilization=float(row[3]),
                    memory_used_mib=float(row[4]),
                    memory_total_mib=float(row[5]),
                    temperature_c=float(row[6]),
                    power_w=float(row[7]),
                )
            )
        except ValueError as exc:
            raise RuntimeError("nvidia-smi 返回了无法解析的指标") from exc
    if not gpus:
        raise RuntimeError("nvidia-smi 没有返回 GPU")
    return gpus, uuid_to_position


def _process_username(pid: int) -> str:
    if pwd is None:
        return ""
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
        username = pwd.getpwuid(uid).pw_name
    except (FileNotFoundError, KeyError, PermissionError, ProcessLookupError):
        return ""
    return username if _USERNAME.fullmatch(username) else ""


def _parse_compute_users(
    output: str, uuid_to_position: dict[str, int]
) -> dict[int, tuple[GPUUser, ...]]:
    totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != 3:
            continue
        position = uuid_to_position.get(row[0].strip())
        if position is None:
            continue
        try:
            pid = int(row[1])
            memory = float(row[2])
        except ValueError:
            continue
        username = _process_username(pid)
        if username:
            totals[position][username] += memory
    return {
        position: tuple(
            GPUUser(username, memory)
            for username, memory in sorted(users.items())
        )
        for position, users in totals.items()
    }


def collect_gpus() -> list[GPU]:
    # 参数完全固定且 shell=False，群消息或环境变量无法变成 shell 命令。
    result = subprocess.run(
        NVIDIA_SMI_COMMAND,
        check=True,
        capture_output=True,
        text=True,
        timeout=8,
        shell=False,
    )
    gpus, uuid_to_position = _parse_inventory(result.stdout)
    try:
        processes = subprocess.run(
            COMPUTE_COMMAND,
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
        users_by_position = _parse_compute_users(processes.stdout, uuid_to_position)
    except (OSError, subprocess.SubprocessError):
        # Core metrics remain useful if process inspection is temporarily unavailable.
        users_by_position = {}
    return [
        GPU(
            gpu.index,
            gpu.name,
            gpu.utilization,
            gpu.memory_used_mib,
            gpu.memory_total_mib,
            gpu.temperature_c,
            gpu.power_w,
            users_by_position.get(position, ()),
        )
        for position, gpu in enumerate(gpus)
    ]
