"""Convert one server snapshot to a privacy-preserving DingTalk card."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

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
    return "🟢 低占用"


def short_model_name(name: str) -> str:
    """Return the concise model token used in card titles, e.g. RTX 5090 -> 5090."""
    match = re.search(
        r"\b([A-Z]?\d{2,4}(?:\s*(?:Ti|SUPER))?S?)\b",
        name,
        flags=re.IGNORECASE,
    )
    return match.group(1).replace("  ", " ") if match else name.strip()


def _models(gpus: list[GPU]) -> str:
    counts = Counter(short_model_name(gpu.name) for gpu in gpus)
    return "；".join(
        f"{count} × {name}" if count > 1 else name
        for name, count in counts.items()
    ) or "尚未识别"


def _server_section(
    report: ServerReport, busy_util: float, busy_memory: float
) -> tuple[str, int, int]:
    if report.state == "online":
        lines = [f"### 🟢 {report.name} · 在线"]
        mixed_models = len({gpu.name for gpu in report.gpus}) > 1
        busy_count = 0
        for gpu in report.gpus:
            status = _status(gpu, busy_util, busy_memory)
            busy_count += status.startswith("🔴")
            model = f" · {short_model_name(gpu.name)}" if mixed_models else ""
            if gpu.users:
                user_summary = "；".join(
                    f"{user.username} **{user.memory_used_mib / 1024:.1f} GiB**"
                    for user in gpu.users
                )
                user_line = f"计算用户：{user_summary}"
            else:
                user_line = "计算用户：无可识别任务"
            lines.extend(
                [
                    "",
                    f"**GPU {gpu.index}{model} · {status}**  ",
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
    gpu_summary = f"{idle_count} 张低占用 · {busy_count} 张使用中"
    summary = gpu_summary
    if len(reports) > 1 or offline_count or error_count:
        summary = f"{server_summary} ｜ {gpu_summary}"
    return {
        "content": (
            f"# {card_title}\n\n"
            f"**{summary}**\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n\n---\n\n"
            f"更新时间：{now}  \n"
            f"> 1. **状态判断：**利用率 ≥ {busy_util:g}% 或显存 ≥ "
            f"{busy_memory / 1024:g} GiB 时标记为使用中。  \n"
            "> 2. **时间标准：**北京时间（UTC+8）。  \n"
            "> 3. **计算用户：**仅统计可识别的 NVIDIA 计算任务。  \n"
            "> 4. **离线判断：**更新时间超过 3 分钟未变化时，服务器或监控服务可能已停止。"
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
    models = list(dict.fromkeys(gpu.name for gpu in gpus))
    title = (
        f"{short_model_name(models[0])} GPU 状态"
        if len(models) == 1
        else f"{server_name} GPU 状态"
    )
    return build_cluster_card_data(
        title,
        [ServerReport(server_name, "online", gpus, now, now)],
        busy_util,
        busy_memory,
    )
