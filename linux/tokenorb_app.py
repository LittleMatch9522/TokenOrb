#!/usr/bin/env python3
"""Linux desktop client for TokenOrb.

The UI uses the system PyQt5 runtime for native packages. The local service
protocol and snapshot fallback live in ``tokenorb_core.py`` so the UI does not
need to know about JSONL details.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QPoint, QRectF, Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QProgressBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from tokenorb_core import (
    CodexAppServerClient,
    LocalSnapshotReader,
    QuotaSnapshot,
    credits_text,
    plan_name,
    reset_countdown_text,
    reset_date_text,
    window_name,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
ICON_PATH = RUNTIME_ROOT / "assets" / "tokenorb.svg"
PRODUCT_NAME = "TokenOrb"


class Settings:
    def __init__(self) -> None:
        config_root = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
        self.path = config_root / "tokenorb" / "settings.json"
        self.size = 94
        self.accent = "#2FA4EB"
        self.position: Optional[tuple[int, int]] = None
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.size = max(64, min(160, int(data.get("size", self.size))))
        accent = data.get("accent", self.accent)
        if isinstance(accent, str) and QColor(accent).isValid():
            self.accent = accent
        position = data.get("position")
        if isinstance(position, list) and len(position) == 2:
            self.position = (int(position[0]), int(position[1]))

    def save(self) -> None:
        data = {"size": self.size, "accent": self.accent}
        if self.position is not None:
            data["position"] = list(self.position)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


class OrbWindow(QWidget):
    clicked = pyqtSignal()
    context_requested = pyqtSignal(QPoint)
    moved = pyqtSignal(QPoint)

    def __init__(self, settings: Settings) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.settings = settings
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(settings.size, settings.size)
        self.setWindowTitle(PRODUCT_NAME)
        self._remaining: Optional[float] = None
        self._connected = False
        self._drag_offset: Optional[QPoint] = None
        self._dragged = False
        self._position_window()

    def _position_window(self) -> None:
        if self.settings.position is not None:
            self.move(*self.settings.position)
            return
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRectF(0, 0, 1440, 900)
        self.move(available.right() - self.width() - 42, available.top() + 90)

    def update_snapshot(self, snapshot: Optional[QuotaSnapshot], connected: bool) -> None:
        self._remaining = (
            snapshot.orb_display_window.remaining_percent
            if snapshot is not None and snapshot.orb_display_window is not None
            else None
        )
        self._connected = connected
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = float(min(self.width(), self.height()))
        circle = QRectF(5, 5, size - 10, size - 10)

        glow = QRadialGradient(circle.center(), size * 0.58)
        glow.setColorAt(0.0, QColor(self.settings.accent).lighter(135))
        glow.setColorAt(0.78, QColor(self.settings.accent))
        glow.setColorAt(1.0, QColor(self.settings.accent).darker(150))
        painter.setPen(QPen(QColor(255, 255, 255, 210), 2))
        painter.setBrush(glow)
        painter.drawEllipse(circle)

        inner = circle.adjusted(7, 7, -7, -7)
        shine = QLinearGradient(inner.topLeft(), inner.bottomRight())
        shine.setColorAt(0.0, QColor(255, 255, 255, 90))
        shine.setColorAt(0.35, QColor(255, 255, 255, 0))
        shine.setColorAt(1.0, QColor(0, 0, 0, 45))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shine)
        painter.drawEllipse(inner)

        text = "…" if self._remaining is None else f"{round(self._remaining):d}%"
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Sans", max(13, int(size * 0.19)), QFont.Bold)
        painter.setFont(font)
        painter.drawText(circle, Qt.AlignCenter, text)

        status_color = QColor("#63E6BE") if self._connected else QColor("#FFD166")
        painter.setBrush(status_color)
        painter.setPen(QPen(QColor("#17324D"), 2))
        painter.drawEllipse(QRectF(size - 24, 10, 13, 13))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.RightButton:
            self.context_requested.emit(event.globalPos())
            return
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._dragged = False

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            self._dragged = True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.LeftButton:
            if self._dragged:
                self.moved.emit(self.pos())
            else:
                self.clicked.emit()
            self._drag_offset = None


class DetailDialog(QDialog):
    refresh_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{PRODUCT_NAME} - Codex 额度")
        self.setMinimumWidth(390)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._snapshot: Optional[QuotaSnapshot] = None
        self._status = "正在准备…"
        self._connected = False

        self.title_label = QLabel("Codex 剩余额度")
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #17324D;")
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.primary = self._make_quota_card()
        self.secondary = self._make_quota_card()
        self.credits_label = QLabel("—")
        self.plan_label = QLabel("—")
        self.source_label = QLabel("—")
        self.captured_label = QLabel("—")
        self.refresh_button = QPushButton("立即刷新")
        self.refresh_button.clicked.connect(self.refresh_requested)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.primary[0])
        layout.addWidget(self.secondary[0])
        form = QFormLayout()
        form.addRow("积分", self.credits_label)
        form.addRow("套餐", self.plan_label)
        form.addRow("数据来源", self.source_label)
        form.addRow("更新时间", self.captured_label)
        layout.addLayout(form)
        layout.addWidget(self.refresh_button)

    def _make_quota_card(self):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #F2F8FC; border: 1px solid #C9DFEA; border-radius: 10px; }"
        )
        layout = QVBoxLayout(frame)
        title = QLabel()
        title.setStyleSheet("font-weight: 700; color: #17324D;")
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setTextVisible(False)
        progress.setStyleSheet(
            "QProgressBar { background: #D5E7F0; border: 0; border-radius: 5px; height: 10px; }"
            "QProgressBar::chunk { background: #2FA4EB; border-radius: 5px; }"
        )
        reset = QLabel()
        reset.setStyleSheet("color: #486B80;")
        layout.addWidget(title)
        layout.addWidget(progress)
        layout.addWidget(reset)
        return frame, title, progress, reset

    def update_state(
        self, snapshot: Optional[QuotaSnapshot], status: str, connected: bool
    ) -> None:
        self._snapshot = snapshot
        self._status = status
        self._connected = connected
        self._render()

    def _render(self) -> None:
        state = "实时" if self._connected else "本地快照"
        color = "#087F5B" if self._connected else "#8F5200"
        self.status_label.setText(f"<b style='color:{color}'>{state}</b>　{self._status}")
        self._render_card(self.primary, self._snapshot.primary if self._snapshot else None)
        self._render_card(self.secondary, self._snapshot.secondary if self._snapshot else None)
        self.credits_label.setText(credits_text(self._snapshot.credits if self._snapshot else None))
        self.plan_label.setText(plan_name(self._snapshot.plan_type if self._snapshot else None))
        self.source_label.setText(self._snapshot.source if self._snapshot else "等待 Codex 额度数据")
        self.captured_label.setText(
            self._snapshot.captured_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if self._snapshot
            else "尚未更新"
        )

    @staticmethod
    def _render_card(card, window) -> None:
        frame, title, progress, reset = card
        frame.setVisible(window is not None and window.used_percent is not None)
        if window is None:
            return
        title.setText(f"{window_name(window)}额度　剩余 {round(window.remaining_percent)}%")
        progress.setValue(round(window.remaining_percent))
        reset.setText(f"重置：{reset_date_text(window)}　({reset_countdown_text(window)})")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._render()


class RuntimeSignals(QObject):
    snapshot = pyqtSignal(object)
    status = pyqtSignal(str, bool, bool)
    diagnostic = pyqtSignal(str, str)


class TokenOrbApp:
    def __init__(self, app: QApplication, demo: bool = False) -> None:
        self.app = app
        self.demo = demo
        self.settings = Settings()
        self.reader = LocalSnapshotReader()
        self.snapshot: Optional[QuotaSnapshot] = None
        self.status = "正在读取 Codex 会话…"
        self.connected = False
        self.signals = RuntimeSignals()
        self.signals.snapshot.connect(self._apply_snapshot)
        self.signals.status.connect(self._apply_status_signal)
        self.signals.diagnostic.connect(self._diagnostic)

        self.orb = OrbWindow(self.settings)
        self.orb.clicked.connect(self.show_details)
        self.orb.context_requested.connect(self.show_context_menu)
        self.orb.moved.connect(self.save_position)
        self.orb.show()

        self.detail = DetailDialog()
        self.detail.refresh_requested.connect(self.refresh)

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), self.app)
            self.tray.setToolTip(PRODUCT_NAME)
            self.tray.activated.connect(self._tray_activated)
            self.tray.setContextMenu(self._make_tray_menu())
            self.tray.show()

        self.client = CodexAppServerClient(
            on_snapshot=self.signals.snapshot.emit,
            on_status=self.signals.status.emit,
            on_diagnostic=self.signals.diagnostic.emit,
        )
        client_snapshot = self.reader.latest()
        if demo:
            self.snapshot = self._demo_snapshot()
            self.status = "演示数据"
            self.connected = True
        elif client_snapshot is not None:
            self.snapshot = client_snapshot
        self._update_presentation()

        self.refresh_timer = QTimer(self.app)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(20_000)
        self.local_timer = QTimer(self.app)
        self.local_timer.timeout.connect(self.load_local_snapshot)
        self.local_timer.start(30_000)
        if not demo:
            self.client.start()

    def _make_tray_menu(self) -> QMenu:
        menu = QMenu()
        details = QAction("查看额度详情", menu)
        details.triggered.connect(self.show_details)
        refresh = QAction("立即刷新", menu)
        refresh.triggered.connect(self.refresh)
        toggle = QAction("显示/隐藏悬浮球", menu)
        toggle.triggered.connect(self.toggle_orb)
        quit_action = QAction("退出 TokenOrb", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(details)
        menu.addAction(refresh)
        menu.addSeparator()
        menu.addAction(toggle)
        menu.addSeparator()
        menu.addAction(quit_action)
        return menu

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_details()

    def _apply_status_signal(self, text: str, connected: bool, fallback: bool) -> None:
        del fallback
        self._apply_status(text, connected)

    def _apply_snapshot(self, snapshot: QuotaSnapshot) -> None:
        self.snapshot = snapshot
        self.connected = snapshot.is_live
        self._update_presentation()

    def _apply_status(self, text: str, connected: bool) -> None:
        self.status = text
        self.connected = connected
        if not connected:
            self.load_local_snapshot()
        self._update_presentation()

    def _diagnostic(self, operation: str, details: str) -> None:
        del operation, details

    def _update_presentation(self) -> None:
        self.orb.update_snapshot(self.snapshot, self.connected)
        self.detail.update_state(self.snapshot, self.status, self.connected)
        if self.tray is not None:
            self.tray.setToolTip(f"{PRODUCT_NAME} · {self.status}")

    def load_local_snapshot(self) -> None:
        if self.connected:
            return
        snapshot = self.reader.latest()
        if snapshot is not None:
            self.snapshot = snapshot
            self._update_presentation()

    def refresh(self) -> None:
        if not self.demo:
            self.client.refresh()
        else:
            self._update_presentation()

    def show_details(self) -> None:
        self.detail.show()
        self.detail.raise_()
        self.detail.activateWindow()

    def show_context_menu(self, position: QPoint) -> None:
        menu = self._make_tray_menu()
        menu.exec_(position)

    def toggle_orb(self) -> None:
        if self.orb.isVisible():
            self.orb.hide()
        else:
            self.orb.show()
            self.orb.raise_()

    def save_position(self, position: QPoint) -> None:
        self.settings.position = (position.x(), position.y())
        self.settings.save()

    def quit(self) -> None:
        self.settings.position = (self.orb.x(), self.orb.y())
        self.settings.save()
        self.client.stop()
        self.detail.close()
        self.orb.close()
        self.app.quit()

    @staticmethod
    def _demo_snapshot() -> QuotaSnapshot:
        from datetime import datetime, timedelta, timezone
        from tokenorb_core import QuotaCredits, QuotaWindow

        now = datetime.now(timezone.utc)
        return QuotaSnapshot(
            limit_id="codex",
            primary=QuotaWindow(31, 300, now + timedelta(hours=2, minutes=27)),
            secondary=QuotaWindow(54, 10080, now + timedelta(days=4, hours=7)),
            credits=QuotaCredits(True, False, "2226.6674375000"),
            plan_type="plus",
            captured_at=now,
            source="演示数据",
            is_live=True,
        )

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TokenOrb Linux client")
    parser.add_argument("--demo", action="store_true", help="使用演示额度启动")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setOrganizationName("chenxulin")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("TokenOrb")
    app.setQuitOnLastWindowClosed(False)
    controller = TokenOrbApp(app, demo=args.demo)
    app.aboutToQuit.connect(controller.client.stop)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
