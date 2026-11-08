import sys, os, subprocess, math, traceback, re, time, shutil, platform, getpass
import glob, datetime, fnmatch, warnings
warnings.filterwarnings("ignore", message=r".*sipPyTypeDict.*")
from collections import deque
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QProgressBar, QLabel
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QThread, QObject, QPointF, QPoint, QRect, QRectF
)
from PyQt6.QtGui import (
    QFont, QTextCursor, QColor, QTextCharFormat, QPainter, QPen,
    QImage, QBrush, QLinearGradient
)


ASCII_LOGO = (
    "  ╔═╗╔═╗╔╗╔╔═╗╦ ╦ ╔╦╗╔═╗╦═╗╔╦╗╦╔╗╔╔═╗╦\n"
    "  ╠╣ ╠═╣║║║║  ╚╦╝  ║ ╠═╣╠╦╝║║║║║║║╠═╣║\n"
    "  ╚  ╩ ╩╝╚╝╚═╝ ╩   ╩ ╚═╝╩╚═╩ ╩╩╝╚╝╩ ╩╩═╝"
)


# ─────────────────────────────────────────────────────────────
#  ANSI
# ─────────────────────────────────────────────────────────────
_ANSI_SGR   = re.compile(r'\x1b\[([0-9;]*)m')
_ANSI_OTHER = re.compile(r'\x1b\[[0-9;?]*[a-ln-zA-LN-Z]')
_ANSI_OSC   = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
_ANSI_MISC  = re.compile(r'\x1b[()][A-Za-z0-9]|\x1b[=>]')
_PALETTE = ["#1c1c1c","#cc5555","#55cc55","#cccc55","#5577cc","#cc55cc",
            "#55cccc","#c0c0c0","#4a4a4a","#ff7777","#77ff77","#ffff77",
            "#7799ff","#ff77ff","#77ffff","#ffffff"]

def _ansi256(n):
    if n < 16:  return _PALETTE[n]
    if n < 232:
        n -= 16
        return f"#{(n//36)*51:02x}{((n//6)%6)*51:02x}{(n%6)*51:02x}"
    v = (n - 232) * 10 + 8
    return f"#{v:02x}{v:02x}{v:02x}"

def _strip_other(t):
    t = _ANSI_OSC.sub('', t); t = _ANSI_MISC.sub('', t); t = _ANSI_OTHER.sub('', t)
    return t

def parse_ansi(text, default_color):
    if '\x1b' not in text:
        if text: yield (text, default_color)
        return
    text = _strip_other(text)
    pos, current = 0, default_color
    for m in _ANSI_SGR.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            if chunk: yield (chunk, current)
        codes = (m.group(1) or '0').split(';')
        i = 0
        while i < len(codes):
            try: c = int(codes[i]) if codes[i] else 0
            except ValueError: i += 1; continue
            if c == 0: current = default_color
            elif 30 <= c <= 37: current = _PALETTE[c - 30]
            elif 90 <= c <= 97: current = _PALETTE[c - 90 + 8]
            elif c == 39: current = default_color
            elif c == 38 and i + 1 < len(codes):
                if codes[i+1] == '5' and i + 2 < len(codes):
                    try: current = _ansi256(int(codes[i+2]))
                    except ValueError: pass
                    i += 2
                elif codes[i+1] == '2' and i + 4 < len(codes):
                    try:
                        r,g,b = int(codes[i+2]),int(codes[i+3]),int(codes[i+4])
                        current = f"#{r:02x}{g:02x}{b:02x}"
                    except ValueError: pass
                    i += 4
            i += 1
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        if chunk: yield (chunk, current)


# ─────────────────────────────────────────────────────────────
#  Window buttons
# ─────────────────────────────────────────────────────────────
class WinButton(QWidget):
    def __init__(self, kind, callback, parent=None):
        super().__init__(parent)
        self.kind, self.callback, self._hover = kind, callback, False
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
    def enterEvent(self, e): self._hover = True; self.update()
    def leaveEvent(self, e): self._hover = False; self.update()
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.callback()
    def paintEvent(self, ev):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width()/2, self.height()/2
        if self._hover:
            p.setBrush(QColor(230,70,90,55) if self.kind=='close' else QColor(255,255,255,18))
            p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(cx, cy), 10, 10)
        color = (QColor(255,145,160) if self.kind=='close' and self._hover
                 else QColor(0,235,215) if self._hover else QColor(110,125,140))
        pen = QPen(color, 1.3); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == 'min':
            p.drawLine(QPointF(cx-4, cy+3), QPointF(cx+4, cy+3))
        elif self.kind == 'max':
            if self.window().isMaximized():
                p.drawRect(QRectF(cx-4, cy-3, 6, 6)); p.drawRect(QRectF(cx-2, cy-5, 6, 6))
            else:
                p.drawRect(QRectF(cx-4, cy-4, 8, 8))
        else:
            p.drawLine(QPointF(cx-3.5, cy-3.5), QPointF(cx+3.5, cy+3.5))
            p.drawLine(QPointF(cx+3.5, cy-3.5), QPointF(cx-3.5, cy+3.5))


# ─────────────────────────────────────────────────────────────
#  Title bar
# ─────────────────────────────────────────────────────────────
class TitleBar(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win, self._drag = win, None
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 6, 0); lay.setSpacing(0)
        self.cwd_label = QLabel("~")
        self.cwd_label.setStyleSheet(
            "color:#4f5a66; font-family:Consolas; font-size:11px; background:transparent;")
        lay.addWidget(self.cwd_label); lay.addStretch()
        self.btn_min   = WinButton('min',   win.showMinimized)
        self.btn_max   = WinButton('max',   self._toggle_max)
        self.btn_close = WinButton('close', win.close)
        lay.addWidget(self.btn_min); lay.addWidget(self.btn_max); lay.addWidget(self.btn_close)
    def set_cwd(self, path): self.cwd_label.setText(path)
    def _toggle_max(self):
        self._win.showNormal() if self._win.isMaximized() else self._win.showMaximized()
        self.btn_max.update()
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            ev.accept()
    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton and self._drag is not None:
            if self._win.isMaximized():
                self._win.showNormal()
                self._drag = ev.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            self._win.move(ev.globalPosition().toPoint() - self._drag)
            ev.accept()
    def mouseReleaseEvent(self, ev): self._drag = None
    def mouseDoubleClickEvent(self, ev): self._toggle_max()


# ─────────────────────────────────────────────────────────────
#  Voxel ripple
# ─────────────────────────────────────────────────────────────
class VoxelRipple(QWidget):
    BLUR_SCALE     = 2
    WAKE_DECAY     = 0.55
    WAKE_STRENGTH  = 0.65
    EDGE_SHARPNESS = 1.6
    EDGE_BOOST     = 0.55
    WAVE_VARIANCE  = 0.10
    TRAVEL_DIM     = 0.65
    FADE_RATE      = 0.06

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self._active = False; self._origin = QPointF(0, 0)
        self._radius = 0.0; self._max_r = 1000.0
        self._life = 1.0; self._travel_life = 1.0
        self._cell = 10; self._speed = 20.0
        self._color = QColor(0, 235, 215)
        self._t = QTimer(self); self._t.timeout.connect(self._step)

    def spawn(self, x, y, cell, color=(0, 235, 215)):
        self._origin = QPointF(x, y); self._radius = 0.0
        self._cell = max(6, int(cell))
        w, h = max(1, self.width()), max(1, self.height())
        self._max_r = max(math.hypot(cx-x, cy-y)
                          for cx, cy in [(0,0),(w,0),(0,h),(w,h)])
        self._speed = max(14.0, self._max_r / 55.0)
        self._life = 1.0; self._travel_life = 1.0
        self._color = QColor(*color); self._active = True
        if not self._t.isActive(): self._t.start(16)
        self.update()

    def _step(self):
        if not self._active: self._t.stop(); return
        self._radius += self._speed
        progress = min(1.0, self._radius / self._max_r)
        self._travel_life = max(0.20, 1.0 - progress * self.TRAVEL_DIM)
        if self._radius >= self._max_r:
            self._life -= self.FADE_RATE
        if self._life <= 0.02:
            self._active = False; self._t.stop()
        self.update()

    def paintEvent(self, ev):
        if not self._active: return
        s = self.BLUR_SCALE
        iw, ih = max(1, self.width()//s), max(1, self.height()//s)
        r = self._radius / s
        if r < 1.0: return
        img = QImage(iw, ih, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)

        cs = max(1.0, self._cell/s); cs_int = max(1, int(math.ceil(cs)))
        ox, oy = self._origin.x()/s, self._origin.y()/s
        r_sq = r * r
        life = self._life * self._travel_life
        cr, cg, cb = self._color.red(), self._color.green(), self._color.blue()
        wake_decay = max(r * self.WAKE_DECAY, 1.0)
        inv_decay = 1.0 / wake_decay
        edge_w = cs * self.EDGE_SHARPNESS
        inv_edge_sq = 1.0 / max(edge_w * edge_w, 1.0)
        var = self.WAVE_VARIANCE; var_half = var * 0.5

        col0 = max(0, int((ox - r - cs) / cs)); col1 = min(int(iw / cs) + 1, int((ox + r + cs) / cs) + 1)
        row0 = max(0, int((oy - r - cs) / cs)); row1 = min(int(ih / cs) + 1, int((oy + r + cs) / cs) + 1)

        with QPainter(img) as ip:
            ip.setPen(Qt.PenStyle.NoPen)
            for row in range(row0, row1):
                cy = row * cs + cs / 2; dy = cy - oy; dy_sq = dy * dy
                if dy_sq >= r_sq: continue
                dx_max = math.sqrt(r_sq - dy_sq)
                x0 = max(col0, int((ox - dx_max) / cs)); x1 = min(col1, int((ox + dx_max) / cs) + 1)
                for col in range(x0, x1):
                    cx = col * cs + cs / 2; dx = cx - ox
                    dist_sq = dx * dx + dy_sq
                    if dist_sq > r_sq: continue
                    dist = math.sqrt(dist_sq); behind = r - dist
                    decay = math.exp(-behind * inv_decay)
                    edge  = math.exp(-behind * behind * inv_edge_sq)
                    inten = (decay * self.WAKE_STRENGTH + edge * self.EDGE_BOOST) * life
                    if inten > 1.0: inten = 1.0
                    h = (col * 73856093) ^ (row * 19349663)
                    rand = (h & 0x7FFFFFFF) / 0x7FFFFFFF
                    inten *= (1.0 - var_half + var * rand)
                    if inten < 0.04: continue
                    alpha = int(inten * 250)
                    if alpha > 255: alpha = 255
                    ip.setBrush(QColor(cr, cg, cb, alpha))
                    ip.drawRect(int(col*cs), int(row*cs), cs_int, cs_int)

        with QPainter(self) as p:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self.rect(), img)


# ─────────────────────────────────────────────────────────────
#  Glow input
# ─────────────────────────────────────────────────────────────
class GlowInput(QLineEdit):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._phase = 0.0
        self._t = QTimer(self); self._t.timeout.connect(self._tick); self._t.start(40)
    def _tick(self):
        self._phase = (self._phase + 0.08) % (6.2831*2); self.update()
    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self.hasFocus(): return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(55 + 35*(0.5 + 0.5*math.sin(self._phase)))
        p.setPen(QPen(QColor(0,220,210,alpha), 1.0)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5,0.5,-0.5,-0.5), 5, 5)


# ─────────────────────────────────────────────────────────────
#  Progress bars
# ─────────────────────────────────────────────────────────────
class SmoothBar(QProgressBar):
    def __init__(self, name="", parent=None):
        super().__init__(parent)
        self.setTextVisible(False); self.setRange(0, 100); self.setFixedHeight(12)
        self._val = 0.0; self._target = 0.0
        self.setStyleSheet("""
            QProgressBar { background:#0a0c10; border:1px solid #16181e; border-radius:6px; }
            QProgressBar::chunk { border-radius:5px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #00d9c8, stop:1 #8060d0); }
        """)
        self._label = QLabel(name)
        self._label.setStyleSheet("color:#4f5a66; font-family:Consolas; font-size:10px; background:transparent;")
        self._t = QTimer(self); self._t.timeout.connect(self._step)
    def _step(self):
        d = self._target - self._val
        if abs(d) <= 0.15:
            self._val = self._target; self.setValue(int(self._val)); self._t.stop(); return
        self._val += d*0.18; self.setValue(int(self._val))
    def set_target(self, v):
        self._target = max(0.0, min(100.0, v))
        if not self._t.isActive(): self._t.start(16)


class ProgressGroup(QObject):
    def __init__(self, layout):
        super().__init__(); self._layout, self._bars = layout, {}
    def bar(self, name):
        if name not in self._bars:
            b = SmoothBar(name)
            self._layout.addWidget(b._label); self._layout.addWidget(b)
            self._bars[name] = b
        return self._bars[name]
    def set(self, name, pct): self.bar(name).set_target(pct)


# ─────────────────────────────────────────────────────────────
#  Shell worker
# ─────────────────────────────────────────────────────────────
class ShellWorker(QThread):
    line = pyqtSignal(str); done = pyqtSignal(int)
    def __init__(self, cmd, cwd=None, env=None):
        super().__init__(); self.cmd, self.cwd, self.env = cmd, cwd, env
        self.proc = None; self._killed = False
    def run(self):
        try:
            self.proc = subprocess.Popen(
                self.cmd, shell=True, cwd=self.cwd, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, errors='replace')
            for ln in self.proc.stdout:
                if self._killed: break
                self.line.emit(ln.rstrip("\r\n"))
            self.proc.wait()
            self.done.emit(130 if self._killed else self.proc.returncode)
        except Exception as e:
            self.line.emit(f"[error] {e}"); self.done.emit(1)
    def kill(self):
        self._killed = True
        if self.proc:
            try: self.proc.terminate()
            except Exception: pass


# ─────────────────────────────────────────────────────────────
#  Typewriter
# ─────────────────────────────────────────────────────────────
class Typewriter:
    def __init__(self, te: QTextEdit):
        self.te = te; self._q = []
        self._t = QTimer(); self._t.timeout.connect(self._tick); self._t.start(8)
    def write(self, text, color="#b8c8d4"):
        for c in text: self._q.append((c, color))
    def write_ansi(self, text, default_color="#b8c8d4"):
        for chunk, color in parse_ansi(text, default_color):
            for c in chunk: self._q.append((c, color))
    def _tick(self):
        n = len(self._q)
        if n == 0: return
        if   n > 4000: batch = n
        elif n > 800:  batch = 500
        elif n > 200:  batch = 60
        elif n > 50:   batch = 8
        else:          batch = 2
        self._insert(batch)
    def _insert(self, batch):
        runs = []
        for _ in range(min(batch, len(self._q))):
            ch, color = self._q.pop(0)
            if runs and runs[-1][1] == color: runs[-1][0] += ch
            else: runs.append([ch, color])
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for text, color in runs:
            fmt = QTextCharFormat(); fmt.setForeground(QColor(color))
            cursor.insertText(text, fmt)
        self.te.setTextCursor(cursor); self.te.ensureCursorVisible()


# ─────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────
class FancyTerminal(QWidget):
    RESIZE_MARGIN = 10
    RADIUS = 12
    KNOWN_CMDS = ["help","clear","exit","demo","cd","pwd","history",
                  "echo","alias","export","unset"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fancy Terminal")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1000, 700)
        self.setMouseTracking(True)

        self._resize_edge = None
        self._resize_start_geo = None
        self._resize_start_pos = None
        self._cwd = os.getcwd()
        self._prev_cwd = None
        self._aliases = {'ll': 'ls -la', 'la': 'ls -a', 'l': 'ls'}
        self._env = dict(os.environ)
        self._path_cache = None
        self._cmd_start = None
        self._search_matches = None
        self._search_idx = 0

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(self.RESIZE_MARGIN, self.RESIZE_MARGIN,
                                       self.RESIZE_MARGIN, self.RESIZE_MARGIN)
        self._outer.setSpacing(0)

        self._container = QWidget(); self._container.setObjectName("container")
        self._container.setMouseTracking(True)
        self._outer.addWidget(self._container)
        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(0, 0, 0, 0); inner.setSpacing(0)

        self._titlebar = TitleBar(self)
        inner.addWidget(self._titlebar)

        content = QWidget(); content.setStyleSheet("background:transparent;")
        c = QVBoxLayout(content)
        c.setContentsMargins(14, 8, 14, 12); c.setSpacing(8)
        inner.addWidget(content, stretch=1)

        self.out = QTextEdit(); self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 11))
        self.out.setStyleSheet("""
            QTextEdit {
                background:#060709; color:#b8c8d4;
                border:1px solid #14161a; border-radius:6px;
                padding:10px;
            }
            QScrollBar:vertical { background:transparent; width:8px; border:none; margin:0; }
            QScrollBar::handle:vertical { background:#1a1f26; min-height:24px; border-radius:4px; }
            QScrollBar::handle:vertical:hover { background:#28303a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; background:none; border:none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
            QScrollBar:horizontal { background:transparent; height:8px; border:none; margin:0; }
            QScrollBar::handle:horizontal { background:#1a1f26; min-width:24px; border-radius:4px; }
            QScrollBar::handle:horizontal:hover { background:#28303a; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; background:none; border:none; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:none; }
        """)
        c.addWidget(self.out, stretch=1)

        self.prog_box = QVBoxLayout(); self.prog_box.setSpacing(2)
        c.addLayout(self.prog_box)
        self.progress = ProgressGroup(self.prog_box)

        irow = QHBoxLayout(); irow.setSpacing(8)
        prompt = QLabel("λ")
        prompt.setStyleSheet("color:#00d9c8; font-family:Consolas; font-size:14px; background:transparent;")
        prompt.setFixedWidth(14)
        self.input = GlowInput(); self.input.setFont(QFont("Consolas", 12))
        self.input.setPlaceholderText("type a command...")
        self.input.setStyleSheet("""
            QLineEdit {
                background:#060709; color:#d0dde6;
                border:1px solid #14161a; border-radius:5px;
                padding:8px 10px;
                selection-background-color:#00d9c8; selection-color:#08090c;
            }
        """)
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        irow.addWidget(prompt); irow.addWidget(self.input)
        c.addLayout(irow)

        self.wave = VoxelRipple(self._container)
        self.wave.setGeometry(self._container.rect()); self.wave.raise_()
        self._container.installEventFilter(self)

        self.setStyleSheet("QLabel { color:#b8c8d4; background:transparent; }")
        self.tw = Typewriter(self.out)
        self._history = []; self._hist_idx = 0
        self.worker = None

        self._update_cwd_label()
        self.input.setFocus()

        cur = self.out.textCursor(); cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat(); fmt.setForeground(QColor("#00d9c8"))
        cur.insertText(ASCII_LOGO + "\n\n", fmt)
        self.out.setTextCursor(cur)

        self._write_welcome()
        self._apply_shape()

    # --- system-stats helpers ---
    def _greeting(self):
        h = datetime.datetime.now().hour
        if 5 <= h < 12:  return "Good morning"
        if 12 <= h < 18: return "Good afternoon"
        if 18 <= h < 23: return "Good evening"
        return "Working late"

    @staticmethod
    def _ascii_bar(pct, width=12):
        if pct is None:
            return "[" + "?" * width + "]   n/a"
        try:
            p = max(0.0, min(100.0, float(pct)))
        except Exception:
            return "[" + "?" * width + "]   n/a"
        filled = int(round(width * p / 100.0))
        return "[" + "█" * filled + "░" * (width - filled) + f"] {p:5.1f}%"

    def _get_gpu_usage(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                return gpus[0].load * 100.0
        except Exception:
            pass
        try:
            from pynvml import (
                nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
                nvmlDeviceGetUtilizationRates, nvmlShutdown,
            )
            nvmlInit()
            try:
                if nvmlDeviceGetCount() > 0:
                    h = nvmlDeviceGetHandleByIndex(0)
                    return float(nvmlDeviceGetUtilizationRates(h).gpu)
            finally:
                nvmlShutdown()
        except Exception:
            pass
        if platform.system() == "Windows":
            try:
                ps = (
                    "Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
                    "-ErrorAction SilentlyContinue | "
                    "Select-Object -ExpandProperty CounterSamples | "
                    "Measure-Object -Property CookedValue -Sum | "
                    "Select-Object -ExpandProperty Sum"
                )
                flags = 0
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    flags = subprocess.CREATE_NO_WINDOW
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", ps],
                    timeout=2, text=True, errors="replace",
                    creationflags=flags,
                ).strip()
                if out and out.replace('.', '', 1).isdigit():
                    return float(out)
            except Exception:
                pass
        return None

    def _write_welcome(self):
        now = datetime.datetime.now()
        try: user = getpass.getuser()
        except Exception: user = "user"
        host = platform.node() or "localhost"

        if platform.system() == "Windows":
            try:
                win_rel = "11" if int(platform.version().split('.')[2]) >= 22000 else "10"
                sysname = f"Windows {win_rel}"
            except Exception:
                sysname = "Windows"
        else:
            sysname = f"{platform.system()} {platform.release()}".strip()

        arch = platform.machine() or "—"
        pyver = platform.python_version()

        home = os.path.expanduser("~")
        cwd = self._cwd
        if cwd == home: cwd_disp = "~"
        elif cwd.startswith(home): cwd_disp = "~" + cwd[len(home):]
        else: cwd_disp = cwd
        cwd_disp = cwd_disp.replace(os.sep, "/")

        cpu_pct = ram_pct = None
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=0.15)
            ram_pct = psutil.virtual_memory().percent
        except Exception:
            pass
        gpu_pct = self._get_gpu_usage()

        self.tw.write(f"{self._greeting()}, {user}.\n\n", color="#00d9c8")
        self.tw.write(f"  {'system':<9} {sysname} · {arch}\n", color="#8fa8bc")
        self.tw.write(f"  {'python':<9} {pyver}\n", color="#8fa8bc")
        self.tw.write(f"  {'host':<9} {host}\n", color="#8fa8bc")
        self.tw.write(f"  {'cwd':<9} {cwd_disp}\n", color="#8fa8bc")
        self.tw.write("\n", color="#6f8898")
        self.tw.write(f"  {'cpu':<9} {self._ascii_bar(cpu_pct)}\n", color="#8fa8bc")
        self.tw.write(f"  {'gpu':<9} {self._ascii_bar(gpu_pct)}\n", color="#8fa8bc")
        self.tw.write(f"  {'ram':<9} {self._ascii_bar(ram_pct)}\n", color="#8fa8bc")
        self.tw.write(f"\n  {now.strftime('%A, %B %d %Y')} · {now.strftime('%H:%M')}\n\n",
                      color="#6f8898")
        self.tw.write("Type 'help' for commands, Tab to complete.\n\n", color="#6f8898")

    # --- paint & shape ---
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 8))

    def _apply_shape(self):
        if self.isMaximized() or self.isFullScreen():
            self._outer.setContentsMargins(0, 0, 0, 0)
            self._container.setStyleSheet(
                "QWidget#container { background:#0a0b0d; border-radius:0px; }")
        else:
            m = self.RESIZE_MARGIN
            self._outer.setContentsMargins(m, m, m, m)
            self._container.setStyleSheet(
                "QWidget#container { background:#0a0b0d; border-radius:%dpx; }" % self.RADIUS)

    def _update_cwd_label(self):
        home = os.path.expanduser("~"); p = self._cwd
        if p == home: p = "~"
        elif p.startswith(home): p = "~" + p[len(home):]
        self._titlebar.set_cwd(p.replace(os.sep, '/'))

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == ev.Type.WindowStateChange:
            self._apply_shape(); QTimer.singleShot(0, self._sync_wave)
    def _sync_wave(self):
        if hasattr(self, "wave"):
            self.wave.setGeometry(self._container.rect()); self.wave.raise_()

    # --- resize ---
    def _edge_at(self, pos, expanded=False):
        if self.isMaximized() or self.isFullScreen(): return None
        m = self.RESIZE_MARGIN + (6 if expanded else 0)
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        if x < 0 or y < 0 or x > w or y > h: return None
        L, R = x < m, x >= w-m; T, B = y < m, y >= h-m
        if T and L: return "tl"
        if T and R: return "tr"
        if B and L: return "bl"
        if B and R: return "br"
        if T: return "t"
        if B: return "b"
        if L: return "l"
        if R: return "r"
        return None
    def _cursor_for(self, e):
        return {"tl":Qt.CursorShape.SizeFDiagCursor, "br":Qt.CursorShape.SizeFDiagCursor,
                "tr":Qt.CursorShape.SizeBDiagCursor, "bl":Qt.CursorShape.SizeBDiagCursor,
                "t": Qt.CursorShape.SizeVerCursor,   "b": Qt.CursorShape.SizeVerCursor,
                "l": Qt.CursorShape.SizeHorCursor,   "r": Qt.CursorShape.SizeHorCursor
                }.get(e, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            e = self._edge_at(ev.position().toPoint(), expanded=True)
            if e:
                self._resize_edge = e
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = ev.globalPosition().toPoint()
                self.grabMouse(); ev.accept(); return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resize_edge and self._resize_start_geo:
            d = ev.globalPosition().toPoint() - self._resize_start_pos
            g = QRect(self._resize_start_geo); e = self._resize_edge
            if "l" in e: g.setLeft(g.left()+d.x())
            if "r" in e: g.setRight(g.right()+d.x())
            if "t" in e: g.setTop(g.top()+d.y())
            if "b" in e: g.setBottom(g.bottom()+d.y())
            if g.width() >= 520 and g.height() >= 380: self.setGeometry(g)
            ev.accept(); return
        e = self._edge_at(ev.position().toPoint())
        self.setCursor(self._cursor_for(e)) if e else self.unsetCursor()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._resize_edge: self.releaseMouse()
        self._resize_edge = None; self._resize_start_geo = None
        self._resize_start_pos = None
        super().mouseReleaseEvent(ev)

    # --- path helpers ---
    def _resolve_path(self, target, base=None):
        if base is None: base = self._cwd
        target = (target or '').strip()
        if len(target) >= 2 and target[0] == target[-1] and target[0] in '"\'':
            target = target[1:-1]
        if not target or target == '~':
            return os.path.expanduser('~')
        if target.startswith('~' + os.sep) or target.startswith('~/'):
            target = os.path.expanduser('~') + target[1:]
        if os.name == 'nt':
            target = target.replace('/', '\\')
        if not os.path.isabs(target):
            target = os.path.join(base, target)
        return os.path.normpath(target)

    def _split_args(self, text):
        args, cur, q = [], '', None
        for c in text:
            if q:
                if c == q: q = None
                else: cur += c
            elif c in '"\'':
                q = c
            elif c == ' ':
                if cur: args.append(cur); cur = ''
            else:
                cur += c
        if cur: args.append(cur)
        return args

    def _expand_globs(self, args):
        out = []
        for a in args:
            if a.startswith('-'):
                out.append(a); continue
            if any(c in a for c in '*?['):
                pattern = a if os.path.isabs(a) else os.path.join(self._cwd, a)
                matches = sorted(glob.glob(pattern))
                if matches: out.extend(matches)
                else: out.append(a)
            else:
                out.append(a)
        return out

    def _human(self, n):
        for unit in ['B', 'K', 'M', 'G', 'T']:
            if n < 1024: return f"{n:.0f}{unit}"
            n /= 1024
        return f"{n:.0f}P"

    # --- keyboard ---
    def eventFilter(self, obj, ev):
        if obj is self._container:
            if ev.type() == ev.Type.Resize:
                self._sync_wave()
            elif ev.type() == ev.Type.MouseMove and not self._resize_edge:
                wp = self._container.mapTo(self, ev.position().toPoint())
                e = self._edge_at(wp, expanded=True)
                self.setCursor(self._cursor_for(e)) if e else self.unsetCursor()
            elif (ev.type() == ev.Type.MouseButtonPress
                  and ev.button() == Qt.MouseButton.LeftButton
                  and not self._resize_edge):
                wp = self._container.mapTo(self, ev.position().toPoint())
                e = self._edge_at(wp, expanded=True)
                if e:
                    self._resize_edge = e
                    self._resize_start_geo = self.geometry()
                    self._resize_start_pos = ev.globalPosition().toPoint()
                    self.grabMouse(); return True
        if obj is self.input and ev.type() == ev.Type.KeyPress:
            ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if ctrl and ev.key() == Qt.Key.Key_R:
                self._reverse_search(); return True
            self._search_matches = None
            if ctrl and ev.key() == Qt.Key.Key_C:
                if self.input.selectedText(): return False
                if self.worker and self.worker.isRunning():
                    self.worker.kill(); self.tw.write("^C\n", color="#e05a6a")
                return True
            if ctrl and ev.key() == Qt.Key.Key_L: self.out.clear(); return True
            if ctrl and ev.key() == Qt.Key.Key_U: self.input.clear(); return True
            if ctrl and ev.key() == Qt.Key.Key_W:
                cur = self.input.cursorPosition(); t = self.input.text()
                new_t = re.sub(r'\S+\s*$', '', t[:cur])
                self.input.setText(new_t + t[cur:]); self.input.setCursorPosition(len(new_t)); return True
            if ctrl and ev.key() == Qt.Key.Key_K:
                self.input.setText(self.input.text()[:self.input.cursorPosition()]); return True
            if ctrl and ev.key() == Qt.Key.Key_D:
                if not self.input.text(): QApplication.quit()
                return True
            if ev.key() == Qt.Key.Key_Up:
                if self._history:
                    self._hist_idx = max(0, self._hist_idx - 1)
                    self.input.setText(self._history[self._hist_idx]); self.input.end(False)
                return True
            if ev.key() == Qt.Key.Key_Down:
                if self._history:
                    self._hist_idx = min(len(self._history), self._hist_idx + 1)
                    self.input.setText("" if self._hist_idx >= len(self._history)
                                       else self._history[self._hist_idx])
                    self.input.end(False)
                return True
            if ev.key() == Qt.Key.Key_Tab:
                self._tab_complete(); return True
        return super().eventFilter(obj, ev)

    def _reverse_search(self):
        if self._search_matches is None:
            q = self.input.text().strip()
            if not q: return
            matches = [c for c in self._history if q.lower() in c.lower()]
            if not matches: return
            self._search_matches = matches
            self._search_idx = len(matches) - 1
        else:
            self._search_idx = (self._search_idx - 1) % len(self._search_matches)
        self.input.setText(self._search_matches[self._search_idx])
        self.input.end(False)

    def _tab_complete(self):
        text = self.input.text(); cur = self.input.cursorPosition()
        before, after = text[:cur], text[cur:]
        if not before: return
        parts = before.split(' ')
        current = parts[-1]
        first = len(parts) == 1
        candidates = self._complete_command(current) if first else self._complete_path(current)
        if not candidates: return
        if len(candidates) == 1:
            cand = candidates[0]
            if first and cand == current: cand += ' '
            nb = ' '.join(parts[:-1] + [cand])
            self.input.setText(nb + after); self.input.setCursorPosition(len(nb)); return
        common = self._common_prefix_ci(candidates)
        if len(common) > len(current) and common[:len(current)].lower() == current.lower():
            nb = ' '.join(parts[:-1] + [current + common[len(current):]])
            self.input.setText(nb + after); self.input.setCursorPosition(len(nb)); return
        self.tw.write('  ' + '  '.join(candidates) + '\n', color="#8060d0")

    def _common_prefix_ci(self, strings):
        if not strings: return ''
        lower = [s.lower() for s in strings]
        lo, hi = min(lower), max(lower)
        i = 0
        while i < len(lo) and i < len(hi) and lo[i] == hi[i]:
            i += 1
        return strings[0][:i]

    def _complete_command(self, prefix):
        lower = prefix.lower()
        matches = []
        seen = set()
        for k in self.KNOWN_CMDS:
            if k.lower().startswith(lower):
                matches.append(k); seen.add(k.lower())
        if self._path_cache is None:
            self._path_cache = set()
            for p in os.environ.get('PATH', '').split(os.pathsep):
                if not p or not os.path.isdir(p): continue
                try:
                    for e in os.listdir(p):
                        if os.name == 'nt':
                            base, ext = os.path.splitext(e)
                            if ext.lower() in ('.exe','.bat','.cmd','.com'):
                                self._path_cache.add(base)
                        else:
                            self._path_cache.add(e)
                except Exception: pass
        if prefix:
            for e in self._path_cache:
                el = e.lower()
                if el.startswith(lower) and el not in seen:
                    matches.append(e); seen.add(el)
        return sorted(matches, key=str.lower)

    def _complete_path(self, prefix):
        display = prefix
        resolved = os.path.expanduser(prefix) if prefix.startswith('~') else prefix
        if os.sep in resolved or '/' in resolved:
            d = os.path.dirname(resolved) or '.'; base = os.path.basename(resolved)
        else:
            d, base = self._cwd, resolved
        if not os.path.isabs(d): d = os.path.join(self._cwd, d)
        try: entries = os.listdir(d)
        except Exception: return []
        inc = base.startswith('.')
        base_lower = base.lower()
        out = []
        for e in entries:
            if not e.lower().startswith(base_lower): continue
            if e.startswith('.') and not inc: continue
            full = os.path.join(d, e)
            cand = e + ('/' if os.path.isdir(full) else '')
            if '/' in display or os.sep in display:
                pdir = os.path.dirname(display)
                cand = (pdir + '/' + cand) if pdir else cand
            out.append(cand)
        return sorted(out, key=str.lower)

    # --- submit ---
    def _submit(self):
        try: self._submit_impl()
        except Exception: traceback.print_exc()

    def _expand_history(self, text):
        if text == '!!': return self._history[-1] if self._history else text
        if text.startswith('!') and text[1:].isdigit():
            n = int(text[1:])
            if 1 <= n <= len(self._history): return self._history[n-1]
        if text.startswith('!-') and text[2:].isdigit():
            n = int(text[2:])
            if 1 <= n <= len(self._history): return self._history[-n]
        return text

    def _submit_impl(self):
        raw = self.input.text()
        if not raw.strip(): self.input.clear(); return

        fm = self.input.fontMetrics()
        trimmed = raw.rstrip(); sp = trimmed.rfind(' ')
        last_word = trimmed if sp == -1 else trimmed[sp+1:]
        prefix_w = 0 if sp == -1 else fm.horizontalAdvance(raw[:sp+1])
        if last_word and self.wave.width() > 0:
            wx = 10 + prefix_w; ww = fm.horizontalAdvance(last_word)
            cell = max(8, min(16, fm.horizontalAdvance('M')))
            gp = self.input.mapToGlobal(QPoint(int(wx + ww/2), int(self.input.height()/2)))
            lp = self.wave.mapFromGlobal(gp)
            self.wave.spawn(lp.x(), lp.y(), cell)

        raw_cmd = self._expand_history(raw.strip())
        text = raw_cmd
        first = text.split()[0] if text.split() else ''
        if first not in self.KNOWN_CMDS and first in self._aliases:
            text = self._aliases[first] + text[len(first):]

        self.input.clear()
        self._history.append(raw_cmd); self._hist_idx = len(self._history)
        self.tw.write(f"λ {raw_cmd}\n", color="#00d9c8")

        if text == 'help' or text == '?':
            self.tw.write(
                "Builtins:\n"
                "  cd [dir]  ·  pwd  ·  history  ·  alias [k=v]  ·  export K=V  ·  unset K\n"
                "  echo  ·  clear  ·  exit  ·  demo (progress bars)\n"
                "\n"
                "Shortcuts:  ..  ...  ~  -     (e.g. just type '..' to go up one level)\n"
                "Aliases:    ll='ls -la'   la='ls -a'   l='ls'\n"
                "\n"
                "Linux tools (auto on Windows):\n"
                "  ls [-a|-l]  cat  touch  mkdir  rmdir  rm [-r]  cp  mv\n"
                "  which/type  whoami  uname [-a]  env  date  df  du\n"
                "  head [-n N]  tail [-n N]  wc [-l]  grep PATTERN FILE...\n"
                "  find [DIR] PATTERN  ·  tree [-L N] [DIR]\n"
                "Wildcards:   ls *.py   cat *.txt\n"
                "\n"
                "Keys:  Tab ↑↓  Ctrl+R (reverse search)  Ctrl+C L U W K D\n\n",
                color="#6f8898")
        elif text == 'clear':
            self.out.clear()
        elif text == 'exit':
            QApplication.quit()
        elif text == 'pwd':
            self.tw.write(f"{self._cwd}\n\n")
        elif text == 'history':
            if not self._history: self.tw.write("  (empty)\n\n", color="#6f8898")
            else:
                for i, cmd in enumerate(self._history, 1):
                    self.tw.write(f"  {i:4d}  {cmd}\n")
                self.tw.write("\n")
        elif text == 'alias':
            if not self._aliases: self.tw.write("  (none)\n\n", color="#6f8898")
            else:
                for k, v in sorted(self._aliases.items()):
                    self.tw.write(f"  {k}='{v}'\n")
                self.tw.write("\n")
        elif text.startswith('alias '):
            rest = text[6:].strip()
            if '=' in rest:
                k, v = rest.split('=', 1)
                self._aliases[k.strip()] = v.strip().strip('"\'')
                self.tw.write(f"  alias {k.strip()}={self._aliases[k.strip()]}\n\n", color="#6f8898")
            else:
                self.tw.write("  usage: alias name=value\n\n", color="#e05a6a")
        elif text.startswith('export '):
            rest = text[7:].strip()
            if '=' in rest:
                k, v = rest.split('=', 1)
                k, v = k.strip(), v.strip().strip('"\'')
                self._env[k] = v; os.environ[k] = v
                self.tw.write(f"  export {k}={v}\n\n", color="#6f8898")
            else:
                self.tw.write("  usage: export KEY=VALUE\n\n", color="#e05a6a")
        elif text.startswith('unset '):
            k = text[6:].strip()
            self._env.pop(k, None); os.environ.pop(k, None)
            self.tw.write(f"  unset {k}\n\n", color="#6f8898")
        elif text in ('..', '...', '~', '-'):
            self._change_dir(text)
        elif text == 'cd' or text.lower().startswith('cd '):
            target_raw = '~' if text == 'cd' else text[3:].strip()
            if not target_raw: target_raw = '~'
            self._change_dir(target_raw)
        elif text == 'demo':
            self._demo()
        elif text == 'echo' or text.startswith('echo '):
            self.tw.write((text[5:] if len(text) > 5 else '') + "\n\n")
        else:
            if not self._try_linux_builtin(text):
                self._shell(text)

    def _change_dir(self, target_raw):
        if target_raw == '-':
            if self._prev_cwd and os.path.isdir(self._prev_cwd):
                old = self._cwd; self._cwd = self._prev_cwd; self._prev_cwd = old
                self._update_cwd_label()
                self.tw.write(f"{self._cwd}\n\n")
            else:
                self.tw.write("cd: OLDPWD not set\n\n", color="#e05a6a")
            return
        new_path = self._resolve_path(target_raw)
        if os.path.isdir(new_path):
            if new_path != self._cwd:
                self._prev_cwd = self._cwd
                self._cwd = new_path
            self._update_cwd_label()
        else:
            self.tw.write(f"cd: no such directory: {target_raw}\n\n", color="#e05a6a")

    # --- Linux builtins ---
    def _try_linux_builtin(self, text):
        parts = self._split_args(text)
        if not parts: return False
        cmd, args = parts[0], parts[1:]
        force = {'find', 'tree'}
        if cmd not in force and shutil.which(cmd):
            return False
        fns = {
            'ls': self._cmd_ls, 'cat': self._cmd_cat, 'touch': self._cmd_touch,
            'mkdir': self._cmd_mkdir, 'rmdir': self._cmd_rmdir, 'rm': self._cmd_rm,
            'cp': self._cmd_cp, 'mv': self._cmd_mv,
            'which': self._cmd_which, 'type': self._cmd_which,
            'whoami': self._cmd_whoami, 'uname': self._cmd_uname, 'env': self._cmd_env,
            'date': self._cmd_date, 'df': self._cmd_df, 'du': self._cmd_du,
            'head': self._cmd_head, 'tail': self._cmd_tail, 'wc': self._cmd_wc,
            'grep': self._cmd_grep, 'find': self._cmd_find, 'tree': self._cmd_tree,
        }
        fn = fns.get(cmd)
        if fn is None: return False
        fn(args); return True

    def _cmd_ls(self, args):
        args = self._expand_globs(args)
        show_all = any(a.startswith('-') and 'a' in a for a in args)
        long_fmt = any(a.startswith('-') and 'l' in a for a in args)
        targets = [a for a in args if not a.startswith('-')] or ['.']
        for i, t in enumerate(targets):
            path = self._resolve_path(t)
            if os.path.isfile(path):
                try: disp = os.path.relpath(path, self._cwd)
                except ValueError: disp = t
                self.tw.write(disp + "\n"); continue
            if not os.path.isdir(path):
                self.tw.write(f"ls: {t}: no such file or directory\n", color="#e05a6a"); continue
            try: entries = sorted(os.listdir(path))
            except Exception as e:
                self.tw.write(f"ls: {t}: {e}\n", color="#e05a6a"); continue
            if len(targets) > 1:
                if i > 0: self.tw.write("\n")
                self.tw.write(f"{t}:\n")
            for e in entries:
                if e.startswith('.') and not show_all: continue
                full = os.path.join(path, e); is_dir = os.path.isdir(full)
                color = "#5a9fd0" if is_dir else "#b8c8d4"
                if long_fmt:
                    try: size = 0 if is_dir else os.path.getsize(full)
                    except OSError: size = 0
                    perm = 'd' if is_dir else '-'
                    self.tw.write(f"{perm}rw-r--r--  {size:>8}  {e}{'/' if is_dir else ''}\n", color=color)
                else:
                    self.tw.write(e + ('/' if is_dir else '') + "\n", color=color)
        self.tw.write("\n"); return True

    def _cmd_cat(self, args):
        args = self._expand_globs(args)
        if not args: self.tw.write("usage: cat FILE...\n\n", color="#e05a6a"); return True
        for f in args:
            try:
                path = self._resolve_path(f)
                if not os.path.isfile(path):
                    self.tw.write(f"cat: {f}: no such file\n", color="#e05a6a"); continue
                if os.path.getsize(path) > 500_000:
                    self.tw.write(f"cat: {f}: file too large\n", color="#e05a6a"); continue
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                self.tw.write(content)
                if content and not content.endswith('\n'): self.tw.write("\n")
            except Exception as e:
                self.tw.write(f"cat: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_touch(self, args):
        if not args: self.tw.write("usage: touch FILE...\n\n", color="#e05a6a"); return True
        for f in args:
            try:
                with open(self._resolve_path(f), 'a'): pass
            except Exception as e:
                self.tw.write(f"touch: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_mkdir(self, args):
        if not args: self.tw.write("usage: mkdir DIR...\n\n", color="#e05a6a"); return True
        for d in args:
            try: os.makedirs(self._resolve_path(d), exist_ok=False)
            except FileExistsError: self.tw.write(f"mkdir: {d}: already exists\n", color="#e05a6a")
            except Exception as e: self.tw.write(f"mkdir: {d}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_rmdir(self, args):
        if not args: self.tw.write("usage: rmdir DIR...\n\n", color="#e05a6a"); return True
        for d in args:
            try: os.rmdir(self._resolve_path(d))
            except Exception as e: self.tw.write(f"rmdir: {d}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_rm(self, args):
        recursive = any(a in ('-r','-R','-rf','-fr') for a in args)
        files = [a for a in args if not a.startswith('-')]
        if not files: self.tw.write("usage: rm [-r] FILE...\n\n", color="#e05a6a"); return True
        for f in files:
            try:
                path = self._resolve_path(f)
                if os.path.isdir(path):
                    if recursive: shutil.rmtree(path)
                    else: raise IsADirectoryError("use -r for directories")
                else: os.remove(path)
            except Exception as e:
                self.tw.write(f"rm: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_cp(self, args):
        files = [a for a in args if not a.startswith('-')]
        if len(files) < 2: self.tw.write("usage: cp SRC DST\n\n", color="#e05a6a"); return True
        try: shutil.copy2(self._resolve_path(files[0]), self._resolve_path(files[1]))
        except Exception as e: self.tw.write(f"cp: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_mv(self, args):
        files = [a for a in args if not a.startswith('-')]
        if len(files) < 2: self.tw.write("usage: mv SRC DST\n\n", color="#e05a6a"); return True
        try: shutil.move(self._resolve_path(files[0]), self._resolve_path(files[1]))
        except Exception as e: self.tw.write(f"mv: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_which(self, args):
        if not args: self.tw.write("usage: which CMD...\n\n", color="#e05a6a"); return True
        for name in args:
            found = shutil.which(name)
            self.tw.write((found or f"which: {name}: not found") + "\n",
                          color="#b8c8d4" if found else "#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_whoami(self, args):
        try: self.tw.write(getpass.getuser() + "\n\n")
        except Exception: self.tw.write("unknown\n\n")
        return True

    def _cmd_uname(self, args):
        if '-a' in args:
            self.tw.write(f"{platform.system()} {platform.node()} {platform.release()} {platform.machine()}\n\n")
        else:
            self.tw.write(platform.system() + "\n\n")
        return True

    def _cmd_env(self, args):
        for k in sorted(self._env): self.tw.write(f"{k}={self._env[k]}\n")
        self.tw.write("\n"); return True

    def _cmd_date(self, args):
        self.tw.write(datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y") + "\n\n")
        return True

    def _cmd_df(self, args):
        try:
            u = shutil.disk_usage(self._cwd)
            pct = int(u.used / u.total * 100) if u.total else 0
            drive = os.path.splitdrive(self._cwd)[0] or '/'
            self.tw.write(f"Filesystem      Size      Used     Avail  Use%  Mounted on\n")
            self.tw.write(f"{drive:<10} {self._human(u.total):>8}  {self._human(u.used):>8}  "
                          f"{self._human(u.free):>8}  {pct:>3}%  {self._cwd}\n\n")
        except Exception as e:
            self.tw.write(f"df: {e}\n\n", color="#e05a6a")
        return True

    def _cmd_du(self, args):
        targets = [a for a in args if not a.startswith('-')] or ['.']
        for t in targets:
            path = self._resolve_path(t)
            try:
                total = 0
                if os.path.isfile(path):
                    total = os.path.getsize(path)
                else:
                    for dp, dn, fns in os.walk(path):
                        for f in fns:
                            try: total += os.path.getsize(os.path.join(dp, f))
                            except OSError: pass
                self.tw.write(f"{self._human(total):>8}\t{t}\n")
            except Exception as e:
                self.tw.write(f"du: {t}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_head(self, args):
        n = 10; files = []; i = 0
        while i < len(args):
            a = args[i]
            if a == '-n' and i+1 < len(args):
                try: n = int(args[i+1]); i += 2; continue
                except: pass
            elif a.startswith('-') and a[1:].isdigit(): n = int(a[1:]); i += 1; continue
            else: files.append(a); i += 1
        if not files: self.tw.write("usage: head [-n N] FILE...\n\n", color="#e05a6a"); return True
        for f in files:
            try:
                with open(self._resolve_path(f), 'r', encoding='utf-8', errors='replace') as fh:
                    for j, line in enumerate(fh):
                        if j >= n: break
                        self.tw.write(line)
            except Exception as e: self.tw.write(f"head: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_tail(self, args):
        n = 10; files = []; i = 0
        while i < len(args):
            a = args[i]
            if a == '-n' and i+1 < len(args):
                try: n = int(args[i+1]); i += 2; continue
                except: pass
            elif a.startswith('-') and a[1:].isdigit(): n = int(a[1:]); i += 1; continue
            else: files.append(a); i += 1
        if not files: self.tw.write("usage: tail [-n N] FILE...\n\n", color="#e05a6a"); return True
        for f in files:
            try:
                with open(self._resolve_path(f), 'r', encoding='utf-8', errors='replace') as fh:
                    for line in deque(fh, maxlen=n): self.tw.write(line)
            except Exception as e: self.tw.write(f"tail: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_wc(self, args):
        lines_only = '-l' in args
        files = [a for a in args if not a.startswith('-')]
        if not files: self.tw.write("usage: wc [-l] FILE...\n\n", color="#e05a6a"); return True
        for f in files:
            try:
                with open(self._resolve_path(f), 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                nl = content.count('\n')
                if lines_only: self.tw.write(f"{nl:>8} {f}\n")
                else: self.tw.write(f"{nl:>8} {len(content.split()):>8} {len(content):>8} {f}\n")
            except Exception as e: self.tw.write(f"wc: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_grep(self, args):
        if len(args) < 2: self.tw.write("usage: grep PATTERN FILE...\n\n", color="#e05a6a"); return True
        pattern, files = args[0], args[1:]
        try: rx = re.compile(pattern)
        except re.error: rx = None
        for f in files:
            try:
                with open(self._resolve_path(f), 'r', encoding='utf-8', errors='replace') as fh:
                    for i, line in enumerate(fh, 1):
                        if (rx and rx.search(line)) or (not rx and pattern in line):
                            self.tw.write(f"{f}:{i}:{line}")
            except Exception as e: self.tw.write(f"grep: {f}: {e}\n", color="#e05a6a")
        self.tw.write("\n"); return True

    def _cmd_find(self, args):
        if not args:
            self.tw.write("usage: find [DIR] PATTERN\n\n", color="#e05a6a"); return True
        root = self._cwd; pattern = args[0]
        if len(args) >= 2 and os.path.isdir(self._resolve_path(args[0])):
            root = self._resolve_path(args[0]); pattern = args[1]
        if not os.path.isdir(root):
            self.tw.write(f"find: {root}: not a directory\n\n", color="#e05a6a"); return True
        matches = []
        for dp, dn, fns in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith('.')]
            for f in fns:
                if f.startswith('.'): continue
                if fnmatch.fnmatch(f.lower(), pattern.lower()):
                    matches.append(os.path.join(dp, f))
        for m in matches[:500]:
            try: rel = os.path.relpath(m, self._cwd)
            except ValueError: rel = m
            self.tw.write(rel + "\n")
        if not matches: self.tw.write("  (no matches)\n", color="#6f8898")
        elif len(matches) > 500: self.tw.write(f"  … {len(matches) - 500} more\n", color="#6f8898")
        else: self.tw.write(f"\n{len(matches)} match(es)\n", color="#6f8898")
        self.tw.write("\n"); return True

    def _cmd_tree(self, args):
        depth = 3; root = self._cwd; i = 0
        while i < len(args):
            a = args[i]
            if a == '-L' and i + 1 < len(args):
                try: depth = int(args[i+1]); i += 2; continue
                except: pass
                i += 1; continue
            elif a.startswith('-L') and len(a) > 2:
                try: depth = int(a[2:]); i += 1; continue
                except: pass
            root = self._resolve_path(a); i += 1
        if not os.path.isdir(root):
            self.tw.write(f"tree: {root}: not a directory\n\n", color="#e05a6a"); return True
        try: rel_root = os.path.relpath(root, self._cwd)
        except ValueError: rel_root = root
        self.tw.write(rel_root + "\n")
        dirs_c = [0]; files_c = [0]
        self._tree_recurse(root, '', 1, depth, dirs_c, files_c)
        self.tw.write(f"\n{dirs_c[0]} directories, {files_c[0]} files\n\n", color="#6f8898")
        return True

    def _tree_recurse(self, path, prefix, level, max_level, dirs_c, files_c):
        if level > max_level: return
        try: entries = sorted(os.listdir(path))
        except: return
        entries = [e for e in entries if not e.startswith('.')]
        for i, e in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = '└── ' if is_last else '├── '
            full = os.path.join(path, e)
            is_dir = os.path.isdir(full)
            if is_dir: dirs_c[0] += 1
            else: files_c[0] += 1
            self.tw.write(prefix + connector + e + ('/' if is_dir else '') + "\n",
                          color="#5a9fd0" if is_dir else "#b8c8d4")
            if is_dir:
                ext = '    ' if is_last else '│   '
                self._tree_recurse(full, prefix + ext, level + 1, max_level, dirs_c, files_c)

    def _demo(self):
        self.tw.write("Running demo…\n", color="#8060d0")
        p = self.progress
        for val, delay in [(10,0),(25,300),(45,600),(70,900),(90,1200),(100,1500)]:
            QTimer.singleShot(delay, lambda v=val: p.set("progress", v))
        QTimer.singleShot(1900, lambda: self.tw.write("✓ demo complete\n\n", color="#00d9c8"))

    def _shell(self, cmd):
        self._cmd_start = time.time()
        self.worker = ShellWorker(cmd, cwd=self._cwd, env=self._env)
        self.worker.line.connect(lambda l: self.tw.write_ansi(l + "\n"))
        self.worker.done.connect(self._on_shell_done)
        self.worker.start()

    def _on_shell_done(self, code):
        elapsed = time.time() - self._cmd_start if self._cmd_start else 0.0
        color = "#00d9c8" if code == 0 else "#e05a6a"
        self.tw.write(f"\n[exit {code}] · {elapsed:.2f}s\n\n", color=color)


def main():
    def hook(t, v, tb): traceback.print_exception(t, v, tb)
    sys.excepthook = hook
    app = QApplication(sys.argv)
    win = FancyTerminal(); win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()