"""Linux runtime for TokenOrb's Codex quota integration.

The macOS and Windows clients use the same Codex app-server protocol.  This
module keeps the Linux port independent from Qt so the parser and local
snapshot fallback can be tested without starting a graphical session.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


UTC = dt.timezone.utc
WEEKLY_WINDOW_MINUTES = 7 * 24 * 60
FIVE_HOUR_WINDOW_MINUTES = 5 * 60


@dataclass
class QuotaWindow:
    used_percent: Optional[float] = None
    window_minutes: Optional[int] = None
    resets_at: Optional[dt.datetime] = None

    @property
    def is_meaningful(self) -> bool:
        return (
            self.used_percent is not None
            or self.window_minutes is not None
            or self.resets_at is not None
        )

    @property
    def remaining_percent(self) -> float:
        return min(100.0, max(0.0, 100.0 - (self.used_percent or 0.0)))

    def merged(self, update: Optional["QuotaWindow"]) -> "QuotaWindow":
        if update is None:
            return self
        return QuotaWindow(
            used_percent=update.used_percent
            if update.used_percent is not None
            else self.used_percent,
            window_minutes=update.window_minutes
            if update.window_minutes is not None
            else self.window_minutes,
            resets_at=update.resets_at if update.resets_at is not None else self.resets_at,
        )


@dataclass
class QuotaCredits:
    has_credits: Optional[bool] = None
    unlimited: Optional[bool] = None
    balance: Optional[str] = None

    def merged(self, update: Optional["QuotaCredits"]) -> "QuotaCredits":
        if update is None:
            return self
        return QuotaCredits(
            has_credits=update.has_credits
            if update.has_credits is not None
            else self.has_credits,
            unlimited=update.unlimited if update.unlimited is not None else self.unlimited,
            balance=update.balance if update.balance else self.balance,
        )


@dataclass
class QuotaSnapshot:
    limit_id: Optional[str] = None
    limit_name: Optional[str] = None
    primary: Optional[QuotaWindow] = None
    secondary: Optional[QuotaWindow] = None
    credits: Optional[QuotaCredits] = None
    plan_type: Optional[str] = None
    rate_limit_reached_type: Optional[str] = None
    spend_control_reached: Optional[bool] = None
    captured_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(UTC))
    source: str = ""
    is_live: bool = False

    @property
    def has_quota_data(self) -> bool:
        return (
            (self.primary is not None and self.primary.is_meaningful)
            or (self.secondary is not None and self.secondary.is_meaningful)
            or self.credits is not None
        )

    @property
    def orb_display_window(self) -> Optional[QuotaWindow]:
        windows = [
            window
            for window in (self.primary, self.secondary)
            if window is not None and window.used_percent is not None
        ]
        weekly = next(
            (window for window in windows if window.window_minutes == WEEKLY_WINDOW_MINUTES),
            None,
        )
        five_hour = next(
            (window for window in windows if window.window_minutes == FIVE_HOUR_WINDOW_MINUTES),
            None,
        )
        if weekly is not None and weekly.remaining_percent <= 0:
            return weekly
        return five_hour or weekly or (windows[0] if windows else None)

    def merged(self, update: "QuotaSnapshot") -> "QuotaSnapshot":
        return QuotaSnapshot(
            limit_id=update.limit_id or self.limit_id,
            limit_name=update.limit_name or self.limit_name,
            primary=self.primary.merged(update.primary)
            if self.primary is not None
            else update.primary,
            secondary=self.secondary.merged(update.secondary)
            if self.secondary is not None
            else update.secondary,
            credits=self.credits.merged(update.credits)
            if self.credits is not None
            else update.credits,
            plan_type=update.plan_type or self.plan_type,
            rate_limit_reached_type=update.rate_limit_reached_type
            or self.rate_limit_reached_type,
            spend_control_reached=update.spend_control_reached
            if update.spend_control_reached is not None
            else self.spend_control_reached,
            captured_at=update.captured_at,
            source=update.source or self.source,
            is_live=self.is_live or update.is_live,
        )


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _mapping(value: Any) -> Optional[dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    return None


def parse_date(value: Any) -> Optional[dt.datetime]:
    number = _float(value)
    if number is not None:
        return dt.datetime.fromtimestamp(number, UTC)
    if not isinstance(value, str):
        return None
    try:
        seconds = float(value)
    except ValueError:
        seconds = None
    if seconds is not None:
        return dt.datetime.fromtimestamp(seconds, UTC)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _window(data: Optional[dict[str, Any]]) -> Optional[QuotaWindow]:
    if data is None:
        return None
    window = QuotaWindow(
        used_percent=_float(_first(data, "usedPercent", "used_percent")),
        window_minutes=_int(
            _first(data, "windowDurationMins", "window_minutes", "windowMinutes")
        ),
        resets_at=parse_date(_first(data, "resetsAt", "resets_at")),
    )
    return window if window.is_meaningful else None


def _credits(data: Optional[dict[str, Any]]) -> Optional[QuotaCredits]:
    if data is None:
        return None
    return QuotaCredits(
        has_credits=_bool(_first(data, "hasCredits", "has_credits")),
        unlimited=_bool(data.get("unlimited")),
        balance=_string(data.get("balance")),
    )


def parse_rate_limits(
    limits: dict[str, Any],
    *,
    source: str,
    is_live: bool,
    captured_at: Optional[dt.datetime] = None,
) -> Optional[QuotaSnapshot]:
    snapshot = QuotaSnapshot(
        limit_id=_string(_first(limits, "limitId", "limit_id")),
        limit_name=_string(_first(limits, "limitName", "limit_name")),
        primary=_window(_mapping(limits.get("primary"))),
        secondary=_window(_mapping(limits.get("secondary"))),
        credits=_credits(_mapping(limits.get("credits"))),
        plan_type=_string(_first(limits, "planType", "plan_type")),
        rate_limit_reached_type=_string(
            _first(limits, "rateLimitReachedType", "rate_limit_reached_type")
        ),
        spend_control_reached=_bool(
            _first(limits, "spendControlReached", "spend_control_reached")
        ),
        captured_at=captured_at or dt.datetime.now(UTC),
        source=source,
        is_live=is_live,
    )
    return snapshot if snapshot.has_quota_data else None


def find_rate_limits(value: Any, depth: int = 0) -> Optional[dict[str, Any]]:
    if depth > 4 or not isinstance(value, dict):
        return None
    direct = _mapping(_first(value, "rateLimits", "rate_limits"))
    if direct is not None:
        return direct
    by_id = _mapping(_first(value, "rateLimitsByLimitId", "rate_limits_by_limit_id"))
    if by_id is not None:
        codex = _mapping(by_id.get("codex"))
        if codex is not None:
            return codex
        for candidate in by_id.values():
            mapped = _mapping(candidate)
            if mapped is not None:
                return mapped
    if "primary" in value or "secondary" in value:
        return value
    for key in ("result", "params", "account", "data"):
        found = find_rate_limits(value.get(key), depth + 1)
        if found is not None:
            return found
    return None


def parse_local_event(json_line: str) -> Optional[QuotaSnapshot]:
    try:
        root = json.loads(json_line)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(root, dict):
        return None
    payload = _mapping(root.get("payload"))
    if payload is None:
        return None
    event_type = _string(payload.get("type"))
    if event_type is not None and event_type.lower() != "token_count":
        return None
    limits = _mapping(_first(payload, "rate_limits", "rateLimits"))
    if limits is None:
        return None
    return parse_rate_limits(
        limits,
        source="本地会话快照",
        is_live=False,
        captured_at=parse_date(root.get("timestamp")),
    )


def initialize_request(client_name: str, version: str) -> dict[str, Any]:
    return {
        "method": "initialize",
        "id": 0,
        "params": {
            "clientInfo": {
                "name": client_name,
                "title": "TokenOrb",
                "version": version,
            }
        },
    }


def rate_limits_request(request_id: int) -> dict[str, Any]:
    return {"method": "account/rateLimits/read", "id": request_id}


def window_name(window: Optional[QuotaWindow]) -> str:
    minutes = window.window_minutes if window is not None else None
    if minutes is None:
        return "额度"
    if minutes == FIVE_HOUR_WINDOW_MINUTES:
        return "5小时"
    if minutes == WEEKLY_WINDOW_MINUTES:
        return "7天"
    if minutes > 0 and minutes % (24 * 60) == 0:
        return f"{minutes // (24 * 60)}天"
    if minutes > 0 and minutes % 60 == 0:
        return f"{minutes // 60}小时"
    return f"{minutes}分钟"


def resolved_reset(
    window: Optional[QuotaWindow], now: Optional[dt.datetime] = None
) -> Optional[dt.datetime]:
    if window is None or window.resets_at is None:
        return None
    current = now or dt.datetime.now(UTC)
    reset = window.resets_at
    if window.window_minutes == WEEKLY_WINDOW_MINUTES and reset <= current:
        elapsed = (current - reset).total_seconds()
        cycles = int(elapsed // (7 * 24 * 60 * 60)) + 1
        reset += dt.timedelta(seconds=cycles * 7 * 24 * 60 * 60)
    return reset


def reset_date_text(window: Optional[QuotaWindow], now: Optional[dt.datetime] = None) -> str:
    reset = resolved_reset(window, now)
    return reset.astimezone().strftime("%Y-%m-%d %H:%M:%S") if reset else "时间未知"


def reset_countdown_text(
    window: Optional[QuotaWindow], now: Optional[dt.datetime] = None
) -> str:
    current = now or dt.datetime.now(UTC)
    reset = resolved_reset(window, current)
    if reset is None:
        return ""
    remaining = (reset - current).total_seconds()
    if remaining <= 0:
        return "等待本地服务刷新"
    seconds = int(remaining)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    if remaining >= 86_400:
        return f"{days}天{hours}小时后"
    if remaining >= 3_600:
        return f"{hours}小时{minutes}分后"
    return f"{max(0, minutes)}分{max(0, seconds)}秒后"


def plan_name(plan: Optional[str]) -> str:
    normalized = (plan or "").strip()
    names = {
        "plus": "ChatGPT Plus",
        "pro": "ChatGPT Pro",
        "team": "ChatGPT Team",
        "business": "ChatGPT Business",
        "enterprise": "ChatGPT Enterprise",
        "edu": "ChatGPT Edu",
    }
    return names.get(normalized.lower(), normalized or "未知套餐")


def credits_text(value: Optional[QuotaCredits]) -> str:
    if value is None or value.has_credits is False:
        return "0"
    if value.unlimited is True:
        return "无限"
    if not value.balance:
        return "可用"
    try:
        return f"{Decimal(value.balance):,.2f}"
    except (InvalidOperation, ValueError):
        return value.balance


class CodexPaths:
    @staticmethod
    def home(environment: Optional[dict[str, str]] = None) -> Path:
        environment = environment or os.environ
        configured = environment.get("CODEX_HOME", "").strip()
        return Path(configured).expanduser() if configured else Path.home() / ".codex"

    @classmethod
    def sessions(cls, environment: Optional[dict[str, str]] = None) -> Path:
        return cls.home(environment) / "sessions"

    @classmethod
    def auth(cls, environment: Optional[dict[str, str]] = None) -> Path:
        return cls.home(environment) / "auth.json"


class CodexExecutableNotFound(RuntimeError):
    pass


def resolve_codex_executable(environment: Optional[dict[str, str]] = None) -> str:
    environment = environment or os.environ
    candidates: list[str] = []
    configured = environment.get("CODEX_QUOTA_CODEX_PATH", "").strip()
    if configured:
        candidates.append(str(Path(configured).expanduser()))
    candidates.extend(
        [
            str(Path.home() / ".local/bin/codex"),
            str(Path.home() / ".npm-global/bin/codex"),
            "/usr/local/bin/codex",
            "/usr/bin/codex",
        ]
    )
    located = shutil.which("codex", path=environment.get("PATH"))
    if located:
        candidates.append(located)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise CodexExecutableNotFound("未找到本地服务命令，请检查配置或 PATH。")


@dataclass(frozen=True)
class LocalSessionsFingerprint:
    newest_modification: float
    file_count: int
    total_size: int
    signature: str


class LocalSnapshotReader:
    tail_bytes = 2 * 1024 * 1024

    def __init__(self, sessions_root: Optional[Path] = None):
        self.sessions_root = Path(sessions_root or CodexPaths.sessions())

    def _rollout_files(self) -> list[tuple[Path, float, int]]:
        if not self.sessions_root.is_dir():
            return []
        files: list[tuple[Path, float, int]] = []
        for path in self.sessions_root.rglob("rollout-*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if path.is_file():
                files.append((path, stat.st_mtime, stat.st_size))
        return sorted(files, key=lambda item: item[1], reverse=True)

    def fingerprint(self) -> LocalSessionsFingerprint:
        files = self._rollout_files()
        signature = "|".join(
            f"{path}:{modified:.6f}:{size}" for path, modified, size in files
        )
        return LocalSessionsFingerprint(
            newest_modification=max((item[1] for item in files), default=0.0),
            file_count=len(files),
            total_size=sum(item[2] for item in files),
            signature=signature,
        )

    def latest(self) -> Optional[QuotaSnapshot]:
        newest: Optional[QuotaSnapshot] = None
        for path, _, _ in self._rollout_files()[:12]:
            snapshot = self._latest_in_file(path)
            if snapshot is not None and (
                newest is None or snapshot.captured_at > newest.captured_at
            ):
                newest = snapshot
        return newest

    def _latest_in_file(self, path: Path) -> Optional[QuotaSnapshot]:
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                offset = max(0, size - self.tail_bytes)
                handle.seek(offset)
                data = handle.read()
        except OSError:
            return None
        text = data.decode("utf-8", errors="replace")
        if offset > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        for line in reversed(text.splitlines()):
            snapshot = parse_local_event(line)
            if snapshot is not None and snapshot.has_quota_data:
                return snapshot
        return None


StatusCallback = Callable[[str, bool, bool], None]
SnapshotCallback = Callable[[QuotaSnapshot], None]
DiagnosticCallback = Callable[[str, str], None]


class CodexAppServerClient:
    """Small JSONL client for ``codex app-server`` with bounded retries."""

    retry_delays = (5.0, 10.0, 15.0, 30.0)

    def __init__(
        self,
        *,
        on_snapshot: Optional[SnapshotCallback] = None,
        on_status: Optional[StatusCallback] = None,
        on_diagnostic: Optional[DiagnosticCallback] = None,
        executable: Optional[str] = None,
    ):
        self.on_snapshot = on_snapshot
        self.on_status = on_status
        self.on_diagnostic = on_diagnostic
        self.executable = executable
        self._stop = threading.Event()
        self._commands: queue.Queue[str] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="tokenorb-codex", daemon=True)
        self._thread.start()

    def refresh(self) -> None:
        self._commands.put("refresh")

    def restart(self) -> None:
        self._commands.put("restart")

    def stop(self) -> None:
        self._stop.set()
        self._commands.put("stop")
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        self._thread = None

    def _status(self, text: str, connected: bool, fallback: bool = False) -> None:
        if self.on_status is not None:
            self.on_status(text, connected, fallback)

    def _diagnostic(self, operation: str, details: str) -> None:
        if self.on_diagnostic is not None:
            self.on_diagnostic(operation, details)

    def _worker(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                live = self._run_session()
                if self._stop.is_set():
                    break
                failures = 0 if live else failures + 1
            except Exception as exc:  # noqa: BLE001 - boundary around external process
                failures += 1
                self._diagnostic("本地服务", str(exc))
            if self._stop.is_set():
                break
            retry_index = min(failures, len(self.retry_delays)) - 1
            delay = self.retry_delays[max(0, retry_index)]
            fallback = failures >= 4
            self._status(
                f"{'使用本地快照；' if fallback else '实时连接失败，'}{int(delay)} 秒后重试",
                False,
                fallback,
            )
            self._stop.wait(delay)

    def _run_session(self) -> bool:
        executable = self.executable or resolve_codex_executable()
        process = subprocess.Popen(
            [executable, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        with self._lock:
            self._process = process
        assert process.stdout is not None
        output: queue.Queue[Optional[str]] = queue.Queue()
        reader = threading.Thread(
            target=self._read_output,
            args=(process.stdout, output),
            name="tokenorb-codex-output",
            daemon=True,
        )
        reader.start()
        pending_id: Optional[int] = None
        next_id = 10
        initialized = False
        live = False
        pending_since = 0.0
        try:
            self._send(process, initialize_request("token_orb_linux", "1.6.0"))
            self._status("正在连接实时接口…", False)
            while not self._stop.is_set():
                command = self._get_command()
                if command == "restart":
                    raise RuntimeError("收到重启请求")
                if command == "refresh" and initialized and pending_id is None:
                    pending_id = next_id
                    next_id += 1
                    pending_since = time.monotonic()
                    self._send(process, rate_limits_request(pending_id))

                if pending_id is not None and time.monotonic() - pending_since > 15:
                    raise TimeoutError("额度查询超过 15 秒未响应")

                try:
                    line = output.get(timeout=0.2)
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError(f"app-server exited with {process.returncode}")
                    continue
                if line is None:
                    if self._stop.is_set():
                        return live
                    raise RuntimeError("app-server 输出已关闭")
                message = self._decode(line)
                if message is None:
                    continue
                message_id = _int(message.get("id"))
                if message_id == 0:
                    if not isinstance(message.get("result"), dict):
                        error = _mapping(message.get("error")) or {}
                        raise RuntimeError(
                            _string(error.get("message")) or "初始化失败"
                        )
                    self._send(process, {"method": "initialized", "params": {}})
                    initialized = True
                    self._status("实时接口已连接，正在读取额度…", False)
                    pending_id = next_id
                    next_id += 1
                    pending_since = time.monotonic()
                    self._send(process, rate_limits_request(pending_id))
                    continue
                if pending_id is not None and message_id == pending_id:
                    pending_id = None
                    limits = find_rate_limits(message.get("result"))
                    snapshot = (
                        parse_rate_limits(
                            limits,
                            source="本地实时接口",
                            is_live=True,
                        )
                        if limits is not None
                        else None
                    )
                    if snapshot is None:
                        raise RuntimeError("实时响应中没有可用额度数据")
                    live = True
                    if self.on_snapshot is not None:
                        self.on_snapshot(snapshot)
                    self._status("实时同步中", True)
                    continue
                method = _string(message.get("method"))
                if method and method.lower() == "account/ratelimits/updated":
                    limits = find_rate_limits(message.get("params"))
                    if limits is not None:
                        snapshot = parse_rate_limits(
                            limits,
                            source="本地实时推送",
                            is_live=True,
                        )
                        if snapshot is not None and self.on_snapshot is not None:
                            live = True
                            self.on_snapshot(snapshot)
                            self._status("实时同步中", True)
            return live
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            with self._lock:
                self._process = None

    def _get_command(self) -> Optional[str]:
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    @staticmethod
    def _decode(line: str) -> Optional[dict[str, Any]]:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return None
        return message if isinstance(message, dict) else None

    @staticmethod
    def _read_output(stream, output: queue.Queue[Optional[str]]) -> None:
        try:
            for line in stream:
                output.put(line)
        finally:
            output.put(None)

    @staticmethod
    def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("app-server stdin 不可用")
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()
