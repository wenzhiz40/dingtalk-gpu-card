"""Environment-only configuration. Secrets are never printed."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    card_template_id: str
    open_conversation_id: str
    server_name: str
    card_title: str
    update_interval_seconds: int
    busy_util_percent: float
    busy_memory_mib: float
    availability_alerts_enabled: bool
    availability_high_percent: float
    availability_low_percent: float
    state_file: str


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"缺少环境变量 {name}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是 true 或 false")


def _safe_label(value: object, field: str, *, allow_empty: bool = False) -> str:
    label = str(value).strip()
    if (not label and not allow_empty) or len(label) > 80 or any(
        char in label for char in "\r\n"
    ):
        raise ValueError(f"{field} 必须是不超过 80 个字符的单行文本")
    return label


def load_config(*, require_dingtalk: bool = True) -> Config:
    def value(name: str) -> str:
        return _required(name) if require_dingtalk else os.environ.get(name, "DRY_RUN")

    interval = int(os.environ.get("UPDATE_INTERVAL_SECONDS", "60"))
    if interval < 30:
        raise ValueError("UPDATE_INTERVAL_SECONDS 不能小于 30 秒")
    high_percent = float(os.environ.get("GPU_AVAILABLE_HIGH_PERCENT", "70"))
    low_percent = float(os.environ.get("GPU_AVAILABLE_LOW_PERCENT", "20"))
    if not 0 <= low_percent < high_percent <= 100:
        raise ValueError("GPU 可用提醒阈值必须满足 0 ≤ LOW < HIGH ≤ 100")

    return Config(
        client_id=value("DINGTALK_CLIENT_ID"),
        client_secret=value("DINGTALK_CLIENT_SECRET"),
        card_template_id=value("DINGTALK_CARD_TEMPLATE_ID"),
        open_conversation_id=value("DINGTALK_OPEN_CONVERSATION_ID"),
        server_name=_safe_label(
            os.environ.get("LOCAL_SERVER_NAME", os.environ.get("SERVER_NAME", "GPU服务器")),
            "LOCAL_SERVER_NAME",
        ),
        # 留空时由本轮实际检测到的 GPU 型号自动生成标题。
        card_title=_safe_label(
            os.environ.get("CARD_TITLE", ""), "CARD_TITLE", allow_empty=True
        ),
        update_interval_seconds=interval,
        busy_util_percent=float(os.environ.get("GPU_BUSY_UTIL_PERCENT", "10")),
        busy_memory_mib=float(os.environ.get("GPU_BUSY_MEMORY_MIB", "1024")),
        availability_alerts_enabled=_boolean("GPU_AVAILABLE_ALERTS_ENABLED", False),
        availability_high_percent=high_percent,
        availability_low_percent=low_percent,
        state_file=os.environ.get(
            "STATE_FILE", "/var/lib/dingtalk-gpu-card/state.json"
        ),
    )
