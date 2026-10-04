"""Convert one server snapshot to a privacy-preserving DingTalk card."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from gpu_collector import GPU


@dataclass(frozen=True)
class ServerReport:
    name: str
    state: str  # online, offline, or error
    gpus: list[GPU]
    checked_at: str
    last_seen_at: str = ""
    detail: str = ""


def _status(gpu: GPU, busy_util: float, busy_memory: float) -> str:
    if gpu.utilization >= busy_util or gpu.memory_used_mib >= busy_memory:
        return "🔴 使用中"
    return "🟢 低占用（可能空闲）"


def _models(gpus: list[GPU]) -> str:
    counts = Counter(gpu.name for gpu in gpus)
    return "；".join(
        f"{count} × {name}" if count > 1 else name
        for name, count in counts.items()
    ) or "尚未识别"


def _server_section(
    report: ServerReport, busy_util: float, busy_memory: float
) -> tuple[str, int, int]:
    if report.state == "online":
        lines = [
            f"### 🟢 {report.name} · 在线",
            f"检测到：**{_models(report.gpus)}**",
        ]
        busy_count = 0
        for gpu in report.gpus:
            status = _status(gpu, busy_util, busy_memory)
            busy_count += status.startswith("🔴")
            if gpu.users:
                user_summary = "；".join(
                    f"{user.username} **{user.memory_used_mib / 1024:.1f} GiB**"
                    for user in gpu.users
                )
                user_line = f"计算用户：{user_summary}"
            else:
                user_line = "计算用户：未检测到可识别的计算任务"
            lines.extend(
                [
                    "",
                    f"**GPU {gpu.index} · {status}**  ",
                    f"{gpu.name}  ",
                    f"利用率 **{gpu.utilization:.0f}%** ｜ "
                    f"显存 **{gpu.memory_used_mib / 1024:.1f}/"
                    f"{gpu.memory_total_mib / 1024:.1f} GiB**  ",
                    f"温度 **{gpu.temperature_c:.0f}°C** ｜ 功耗 **{gpu.power_w:.0f} W**  ",
                    user_line,
                ]
            )
        return "\n".join(lines), len(report.gpus) - busy_count, busy_count

    if report.state == "offline":
        title = f"### ⚫ {report.name} · 掉线（疑似关机）"
    else:
        title = f"### 🟠 {report.name} · 异常"
    lines = [title, f"检查结果：{report.detail or '无法采集 GPU 状态'}"]
    if report.last_seen_at:
        lines.append(f"最近在线：**{report.last_seen_at}**")
    if report.gpus:
        lines.append(f"上次识别：{_models(report.gpus)}")
    lines.append(f"本次检查：{report.checked_at}")
    return "  \n".join(lines), 0, 0


def build_cluster_card_data(
    card_title: str,
    reports: list[ServerReport],
    busy_util: float,
    busy_memory: float,
) -> dict[str, str]:
    sections: list[str] = []
    idle_count = 0
    busy_count = 0
    online_count = 0
    offline_count = 0
    error_count = 0
    for report in reports:
        section, idle, busy = _server_section(report, busy_util, busy_memory)
        sections.append(section)
        idle_count += idle
        busy_count += busy
        online_count += report.state == "online"
        offline_count += report.state == "offline"
        error_count += report.state == "error"

    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    server_summary = f"{online_count} 台在线"
    if offline_count:
        server_summary += f" · {offline_count} 台掉线"
    if error_count:
        server_summary += f" · {error_count} 台异常"
    gpu_summary = f"{idle_count} 张低占用，{busy_count} 张使用中"
    rule_note = (
        f"状态为估算：利用率 ≥ {busy_util:g}% 或显存 ≥ "
        f"{busy_memory / 1024:g} GiB 时标记为使用中"
    )
    return {
        "content": (
            f"# {card_title}\n\n"
            f"**{server_summary} ｜ {gpu_summary}**\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n\n---\n\n"
            f"更新时间：{now}  \n"
            f"> {rule_note}  \n"
            "> 时间均为北京时间（UTC+8）  \n"
            "> 计算用户仅统计可识别的 NVIDIA 计算任务，不展示其他进程细节或桌面图形任务  \n"
            "> 若更新时间超过 3 分钟未变化，表示本机服务器或监控服务已停止/掉线"
        )
    }


def build_card_data(
    server_name: str,
    gpus: list[GPU],
    busy_util: float,
    busy_memory: float,
) -> dict[str, str]:
    """Backward-compatible single-server formatter used by existing callers/tests."""
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    return build_cluster_card_data(
        f"{server_name} GPU 状态",
        [ServerReport(server_name, "online", gpus, now, now)],
        busy_util,
        busy_memory,
    )
