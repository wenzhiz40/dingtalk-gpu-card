#!/usr/bin/env python3
"""Periodically update this server's independent DingTalk GPU card."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from card_data import ServerReport, build_cluster_card_data
from config import Config, load_config
from dingtalk_api import DingTalkClient, DingTalkError
from gpu_collector import (
    GPU,
    collect_gpus,
    gpu_from_dict,
    gpu_to_dict,
)


LOG = logging.getLogger("dingtalk-gpu-card")
STOP = False


def _stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def _load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _cached_gpus(state: dict, name: str) -> tuple[list[GPU], str]:
    servers = state.get("servers", {})
    if not isinstance(servers, dict):
        return [], ""
    value = servers.get(name, {})
    if not isinstance(value, dict):
        return [], ""
    try:
        gpus = [gpu_from_dict(item) for item in value.get("gpus", [])]
    except (TypeError, ValueError):
        gpus = []
    return gpus, str(value.get("lastSeenAt", ""))


def _remember_success(state: dict, name: str, gpus: list[GPU], seen_at: str) -> None:
    servers = state.get("servers")
    if not isinstance(servers, dict):
        servers = {}
        state["servers"] = servers
    servers[name] = {
        "lastSeenAt": seen_at,
        "gpus": [gpu_to_dict(gpu) for gpu in gpus],
    }


def _failure_report(
    state: dict, name: str, status: str, detail: str, checked_at: str
) -> ServerReport:
    gpus, last_seen = _cached_gpus(state, name)
    return ServerReport(name, status, gpus, checked_at, last_seen, detail)


def _collect_reports(config: Config, state: dict) -> list[ServerReport]:
    reports: list[ServerReport] = []
    checked_at = _now()
    try:
        gpus = collect_gpus()
    except subprocess.TimeoutExpired:
        reports.append(
            _failure_report(
                state, config.server_name, "error", "本机 nvidia-smi 查询超时", checked_at
            )
        )
    except FileNotFoundError:
        reports.append(
            _failure_report(
                state,
                config.server_name,
                "error",
                "本机未找到 /usr/bin/nvidia-smi",
                checked_at,
            )
        )
    except OSError:
        reports.append(
            _failure_report(
                state,
                config.server_name,
                "error",
                "本机无法启动 nvidia-smi，请检查文件和设备权限",
                checked_at,
            )
        )
    except subprocess.CalledProcessError as exc:
        reports.append(
            _failure_report(
                state,
                config.server_name,
                "error",
                f"本机 nvidia-smi 执行失败（退出码 {exc.returncode}）",
                checked_at,
            )
        )
    except RuntimeError as exc:
        reports.append(
            _failure_report(state, config.server_name, "error", str(exc), checked_at)
        )
    else:
        _remember_success(state, config.server_name, gpus, checked_at)
        reports.append(
            ServerReport(config.server_name, "online", gpus, checked_at, checked_at)
        )
    return reports


def _card_title(config: Config, reports: list[ServerReport]) -> str:
    if config.card_title:
        return config.card_title
    models = []
    for report in reports:
        for gpu in report.gpus:
            if gpu.name not in models:
                models.append(gpu.name)
    if len(models) == 1:
        return f"{models[0]} GPU 状态"
    return f"{config.server_name} GPU 状态"


def _availability_events(
    config: Config, state: dict, reports: list[ServerReport]
) -> list[dict]:
    if not config.availability_alerts_enabled:
        return []
    alert_state = state.get("availabilityAlerts")
    if not isinstance(alert_state, dict):
        alert_state = {}
        state["availabilityAlerts"] = alert_state

    events: list[dict] = []
    for report in reports:
        if report.state != "online":
            continue
        for gpu in report.gpus:
            key = json.dumps([report.name, gpu.index], ensure_ascii=False)
            entry = alert_state.get(key)
            if not isinstance(entry, dict):
                entry = {}
                alert_state[key] = entry
            if gpu.utilization >= config.availability_high_percent:
                entry["armed"] = True
            elif gpu.utilization < config.availability_low_percent and entry.get("armed"):
                events.append(
                    {
                        "key": key,
                        "server": report.name,
                        "index": gpu.index,
                        "model": gpu.name,
                        "utilization": gpu.utilization,
                    }
                )
            entry["lastUtilization"] = gpu.utilization
    return events


def _availability_message(config: Config, events: list[dict]) -> str:
    lines = ["GPU 可用提醒"]
    for event in events:
        lines.append(
            f"{event['server']} GPU {event['index']}（{event['model']}）可使用："
            f"利用率已从 ≥{config.availability_high_percent:g}% 降至 "
            f"{event['utilization']:.0f}%。"
        )
    lines.append("请结合总览卡片中的显存与计算用户确认。")
    return "\n".join(lines)


def _mark_events_sent(state: dict, events: list[dict]) -> None:
    alert_state = state.get("availabilityAlerts", {})
    for event in events:
        entry = alert_state.get(event["key"])
        if isinstance(entry, dict):
            entry["armed"] = False


def run_once(*, dry_run: bool) -> None:
    config = load_config(require_dingtalk=not dry_run)
    state_path = Path(config.state_file)
    state = {} if dry_run else _load_state(state_path)
    reports = _collect_reports(config, state)
    availability_events = _availability_events(config, state, reports)
    card_data = build_cluster_card_data(
        _card_title(config, reports),
        reports,
        config.busy_util_percent,
        config.busy_memory_mib,
    )
    if dry_run:
        print(json.dumps(card_data, ensure_ascii=False, indent=2))
        return

    client = DingTalkClient(config.client_id, config.client_secret)
    track_id = str(state.get("outTrackId", ""))
    if track_id:
        client.update_card(track_id, card_data)
        LOG.info("GPU 总览卡片已更新")
    else:
        track_id = client.create_and_deliver_card(
            config.card_template_id,
            config.open_conversation_id,
            card_data,
        )
        state["outTrackId"] = track_id
        LOG.info("GPU 总览卡片已首次投放，请在群中手动置顶")
    if availability_events:
        try:
            client.send_group_text(
                config.open_conversation_id,
                _availability_message(config, availability_events),
            )
        except DingTalkError as exc:
            # A missing robot-message permission must never stop the status card.
            LOG.warning("GPU 可用提醒发送失败（总览卡片不受影响）: %s", exc)
        else:
            _mark_events_sent(state, availability_events)
            LOG.info("GPU 可用提醒已发送")
    _save_state(state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只更新一次")
    parser.add_argument("--dry-run", action="store_true", help="只打印数据，不访问钉钉")
    args = parser.parse_args()
    if args.dry_run and hasattr(sys.stdout, "reconfigure"):
        # Windows consoles commonly default to GBK, which cannot encode status emoji.
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    config = load_config(require_dingtalk=not args.dry_run)
    while not STOP:
        try:
            run_once(dry_run=args.dry_run)
        except Exception as exc:  # systemd retains diagnostics; secrets are never formatted.
            LOG.error("本轮更新失败: %s", exc)
            if args.once or args.dry_run:
                return 1
        if args.once or args.dry_run:
            break
        stop_at = time.monotonic() + config.update_interval_seconds
        while not STOP and time.monotonic() < stop_at:
            time.sleep(min(1, stop_at - time.monotonic()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
