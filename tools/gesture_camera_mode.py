from __future__ import annotations

import math
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtGui import QFont, QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


PINCH_DISTANCE = 0.055
SMOOTHING = 0.18
DEADZONE_PX = 7
BASE_DIR = Path(__file__).resolve().parent.parent
HAND_MODEL = BASE_DIR / "models" / "hand_landmarker.task"
CMD_FILE = Path("/tmp/jarvis-gesture-camera-cmd.json")
PID_FILE = Path("/tmp/jarvis-gesture-camera.pid")
LOG_FILE = Path("/tmp/jarvis-gesture-camera.log")

WIDGETS = {
    "tareas": ("Tareas", "Pendientes y tareas desde Jarvis/Supabase."),
    "notas": ("Notas", "Notas rápidas y material de estudio."),
    "calendario": ("Calendario", "Fechas importantes y próximos eventos."),
    "sistema": ("Sistema", "Estado rápido del PC y Jarvis."),
    "camara": ("Cámara", "Vista de cámara y control gestual."),
}


def _log(message: str) -> None:
    try:
        LOG_FILE.write_text(
            (LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else "")
            + f"{time.strftime('%H:%M:%S')} {message}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


class Card(QFrame):
    def __init__(self, title: str, body: str, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(260, 150)
        self.setStyleSheet("""
            QFrame {
                background: rgba(8, 12, 22, 220);
                border: 1px solid rgba(0, 230, 118, 160);
                border-radius: 14px;
            }
            QLabel { background: transparent; border: none; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #00e676;")
        lay.addWidget(title_lbl)

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet("color: #dde3ed; font-size: 12px;")
        lay.addWidget(body_lbl)

    def flash(self):
        self.setStyleSheet("""
            QFrame {
                background: rgba(0, 28, 14, 240);
                border: 3px solid rgba(0, 230, 118, 255);
                border-radius: 14px;
            }
            QLabel { background: transparent; border: none; }
        """)
        QTimer.singleShot(900, lambda: self.setStyleSheet("""
            QFrame {
                background: rgba(8, 12, 22, 220);
                border: 1px solid rgba(0, 230, 118, 160);
                border-radius: 14px;
            }
            QLabel { background: transparent; border: none; }
        """))


class GestureCameraOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS — Modo Cámara")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen)
        self._screen = screen

        self.preview = QLabel(self)
        self.preview.setGeometry(0, 0, screen.width(), screen.height())
        self.preview.setStyleSheet("background: #05070d;")
        self.preview.setScaledContents(True)
        self.preview.lower()

        self.hint = QLabel("Pinza para tomar y mover widgets · ESC sale", self)
        self.hint.setGeometry(24, 24, 860, 36)
        self.hint.setStyleSheet("color: #00e676; background: rgba(5,7,13,190); padding: 8px 12px; border-radius: 10px; font-weight: bold;")

        self.status = QLabel("", self)
        self.status.setGeometry(24, 70, 460, 40)
        self.status.setStyleSheet("color: #00e676; background: rgba(5,7,13,210); padding: 8px 12px; border-radius: 10px; font-weight: bold;")
        self.status.hide()

        self.menu = QWidget(self)
        self.menu.setGeometry(24, 116, 640, 38)
        menu_lay = QVBoxLayout(self.menu)
        menu_lay.setContentsMargins(0, 0, 0, 0)
        row = QWidget(self.menu)
        from PyQt6.QtWidgets import QHBoxLayout
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(6)
        for kind, label in [("tareas", "TAREAS"), ("notas", "NOTAS"), ("calendario", "CAL"), ("sistema", "SYS")]:
            btn = QPushButton(f"+ {label}")
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { background: rgba(5,7,13,210); color: #00e676; border: 1px solid rgba(0,230,118,120); border-radius: 8px; font-weight: bold; }
                QPushButton:hover { background: rgba(0,230,118,35); }
            """)
            btn.clicked.connect(lambda checked=False, k=kind: self.add_widget(k))
            row_lay.addWidget(btn)
        menu_lay.addWidget(row)

        self.cursor = QLabel("◉", self)
        self.cursor.setFixedSize(42, 42)
        self.cursor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cursor.setStyleSheet("color: #00e676; font-size: 28px; background: rgba(0,230,118,38); border-radius: 21px;")
        self.cursor.hide()

        self.cards = []
        self._spawn_index = 0
        for kind in ["tareas", "notas", "sistema"]:
            self.add_widget(kind, initial=True)

        self._selected: Card | None = None
        self._drag_offset = QPoint(0, 0)
        self._last_point: QPoint | None = None
        self._smooth_point: QPoint | None = None
        self._last_time = time.time()
        self._pinching = False

        options = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(HAND_MODEL)),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self._hands = mp_vision.HandLandmarker.create_from_options(options)
        self._cap = cv2.VideoCapture(0)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._cap.set(cv2.CAP_PROP_FPS, 30)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

        self._cmd_timer = QTimer(self)
        self._cmd_timer.timeout.connect(self._poll_commands)
        self._cmd_timer.start(300)

        PID_FILE.write_text(str(__import__("os").getpid()), encoding="utf-8")

        QShortcut(QKeySequence("Escape"), self).activated.connect(self.close)
        QShortcut(QKeySequence("T"), self).activated.connect(lambda: self.add_widget("tareas"))
        QShortcut(QKeySequence("N"), self).activated.connect(lambda: self.add_widget("notas"))
        QShortcut(QKeySequence("C"), self).activated.connect(lambda: self.add_widget("calendario"))
        QShortcut(QKeySequence("S"), self).activated.connect(lambda: self.add_widget("sistema"))

    def add_widget(self, kind: str, initial: bool = False):
        title, body = WIDGETS.get(kind, (kind.title(), "Widget personalizado."))
        card = Card(title, body, self)
        if initial:
            x = self._screen.width() - 320 - ((self._spawn_index % 2) * 36)
            y = 90 + ((self._spawn_index % 5) * 180)
            if y + card.height() > self._screen.height() - 40:
                y = 90
        else:
            x = int((self._screen.width() - card.width()) / 2 + ((self._spawn_index % 3) - 1) * 46)
            y = int((self._screen.height() - card.height()) / 2 + ((self._spawn_index % 4) - 1) * 38)
        card.move(x, y)
        card.show()
        if not initial:
            card.flash()
        card.raise_()
        self.cards.append(card)
        self._spawn_index += 1
        if not initial:
            self.status.setText(f"Widget agregado: {title}")
            self.status.show()
            self.status.raise_()
            QTimer.singleShot(1600, self.status.hide)
        _log(f"add_widget {kind} -> {x},{y}")

    def _poll_commands(self):
        if not CMD_FILE.exists():
            return
        try:
            cmd = json.loads(CMD_FILE.read_text(encoding="utf-8"))
            CMD_FILE.unlink(missing_ok=True)
        except Exception:
            return
        if cmd.get("action") == "add_widget":
            _log(f"command add_widget {cmd.get('kind')}")
            self.add_widget(cmd.get("kind", "tareas"))

    def closeEvent(self, event):
        self._timer.stop()
        self._cmd_timer.stop()
        self._cap.release()
        self._hands.close()
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        super().closeEvent(event)

    def _gesture_info(self, landmarks) -> tuple[bool, QPoint]:
        thumb = landmarks[4]
        index = landmarks[8]
        dist = math.hypot(thumb.x - index.x, thumb.y - index.y)
        pinching = dist < PINCH_DISTANCE
        x = int(((thumb.x + index.x) / 2) * self._screen.width())
        y = int(((thumb.y + index.y) / 2) * self._screen.height())
        return pinching, QPoint(x, y)

    def _card_at(self, point: QPoint) -> Card | None:
        for card in reversed(self.cards):
            if card.isVisible() and card.geometry().contains(point):
                return card
        return None

    def _update_drag(self, pinching: bool, point: QPoint):
        now = time.time()

        if self._smooth_point is None:
            self._smooth_point = point
        else:
            dx = point.x() - self._smooth_point.x()
            dy = point.y() - self._smooth_point.y()
            if math.hypot(dx, dy) >= DEADZONE_PX:
                self._smooth_point = QPoint(
                    int(self._smooth_point.x() + dx * SMOOTHING),
                    int(self._smooth_point.y() + dy * SMOOTHING),
                )
        point = self._smooth_point

        dt = max(now - self._last_time, 1e-3)
        speed = 0.0
        if self._last_point is not None:
            speed = math.hypot(point.x() - self._last_point.x(), point.y() - self._last_point.y()) / dt

        self.cursor.move(point.x() - 21, point.y() - 21)
        self.cursor.show()
        self.cursor.raise_()
        self.cursor.setStyleSheet(
            "color: #ffb000; font-size: 28px; background: rgba(255,176,0,52); border-radius: 21px;"
            if pinching else
            "color: #00e676; font-size: 28px; background: rgba(0,230,118,38); border-radius: 21px;"
        )

        if pinching and not self._pinching:
            self._selected = self._card_at(point)
            if self._selected:
                self._selected.raise_()
                self._drag_offset = point - self._selected.pos()

        if pinching and self._selected:
            self._selected.move(point - self._drag_offset)

        if not pinching:
            self._selected = None

        self._pinching = pinching
        self._last_point = point
        self._last_time = now

    def _tick(self):
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._hands.detect(image)

        if result.hand_landmarks:
            pinching, point = self._gesture_info(result.hand_landmarks[0])
            self._update_drag(pinching, point)
        else:
            self.cursor.hide()
            self._selected = None
            self._pinching = False

        view = cv2.resize(rgb, (self._screen.width(), self._screen.height()))
        img = QImage(view.data, view.shape[1], view.shape[0], view.strides[0], QImage.Format.Format_RGB888)
        self.preview.setPixmap(QPixmap.fromImage(img.copy()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--add-widget", default="")
    args = parser.parse_args()

    if args.add_widget and PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            __import__("os").kill(pid, 0)
            CMD_FILE.write_text(json.dumps({"action": "add_widget", "kind": args.add_widget}), encoding="utf-8")
            _log(f"sent add_widget {args.add_widget} to {pid}")
            return
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    win = GestureCameraOverlay()
    if args.add_widget:
        win.add_widget(args.add_widget)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
