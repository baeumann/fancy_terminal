import sys, os, subprocess, math, traceback, re, time, shutil, platform, getpass
import glob, datetime, fnmatch, warnings, stat, codecs, signal, threading
warnings.filterwarnings("ignore", message=r".*sipPyTypeDict.*")
from collections import deque
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QProgressBar, QLabel
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QThread, QObject, QPointF, QPoint, QRect, QRectF, QEvent
)
from PyQt6.QtGui import (
    QFont, QTextCursor, QColor, QTextCharFormat, QTextBlockFormat, QPainter, QPen,
    QBrush, QLinearGradient, QRadialGradient, QPainterPath
)


ASCII_LOGO = (
    "  ╔═╗╔═╗╔╗╔╔═╗╦ ╦ ╔╦╗╔═╗╦═╗╔╦╗╦╔╗╔╔═╗╦\n"
    "  ╠╣ ╠═╣║║║║  ╚╦╝  ║ ╠═╣╠╦╝║║║║║║║╠═╣║\n"
    "  ╚  ╩ ╩╝╚╝╚═╝ ╩   ╩ ╚═╝╩╚═╩ ╩╩╝╚╝╩ ╩╩═╝"
)


# ─────────────────────────────────────────────────────────────
#  Qt-free helpers: colour maths, ANSI stream, column layout,
#  ripple maths.  (No Qt in here, so it can be unit-tested.)
# ─────────────────────────────────────────────────────────────
TEAL   = (0, 217, 200)
VIOLET = (128, 96, 208)
BG_HEX = "#0a0b0d"

def _lerp_rgb(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)

def _rgb(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _mix_hex(a, b, t):
    return _hex(_lerp_rgb(_rgb(a), _rgb(b), t))


# --- ANSI -------------------------------------------------------------------
_ANSI_SGR   = re.compile(r'\x1b\[([0-9;]*)m')
_ANSI_OTHER = re.compile(r'\x1b\[[0-9;?]*[a-ln-zA-LN-Z]')
_ANSI_OSC   = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
_ANSI_MISC  = re.compile(r'\x1b[()][A-Za-z0-9]|\x1b[=>]')
_ANSI_TAIL  = re.compile(r'\x1b(?:\[[0-9;?]*|\][^\x07\x1b]*)?\Z')   # escape cut off at chunk end
_CTRL       = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')       # everything but \t \n \r
_PALETTE = ["#3a4450", "#e05a6a", "#5fd68a", "#e0b050", "#5a9fd0", "#b08cf0",
            "#00d9c8", "#c0ccd6", "#4f5a66", "#ff7a8a", "#86efac", "#f5cc6a",
            "#7ab8e8", "#c9a8ff", "#4ff0e0", "#f2f7fa"]

def _ansi256(n):
    if n < 16:  return _PALETTE[n]
    if n < 232:
        n -= 16
        return f"#{(n//36)*51:02x}{((n//6)%6)*51:02x}{(n%6)*51:02x}"
    v = (n - 232) * 10 + 8
    return f"#{v:02x}{v:02x}{v:02x}"


class AnsiStream:
    """Incremental ANSI/SGR parser.

    Unlike a per-line parser it keeps colour/bold/underline state across
    chunks and lines, and holds back an escape sequence that is cut in half
    at the end of a chunk until the rest arrives.
    feed(text) -> [(plain_text, (color, bold, underline)), ...]
    """
    def __init__(self, default_color):
        self.default = default_color
        self.reset()

    def reset(self):
        self.color = self.default
        self.bold = self.underline = self.dim = False
        self._carry = ""

    def _style(self):
        c = _mix_hex(self.color, BG_HEX, 0.5) if self.dim else self.color
        return (c, self.bold, self.underline)

    def feed(self, text):
        text = self._carry + text
        self._carry = ""
        m = _ANSI_TAIL.search(text)
        if m:
            self._carry = text[m.start():]
            text = text[:m.start()]
        text = text.replace('\r\n', '\n')
        text = _ANSI_OSC.sub('', text)
        text = _ANSI_MISC.sub('', text)
        text = _ANSI_OTHER.sub('', text)
        out, pos = [], 0
        for m in _ANSI_SGR.finditer(text):
            if m.start() > pos:
                out.append((_CTRL.sub('', text[pos:m.start()]), self._style()))
            self._apply(m.group(1))
            pos = m.end()
        if pos < len(text):
            out.append((_CTRL.sub('', text[pos:]), self._style()))
        return [(t, s) for t, s in out if t]

    def _apply(self, params):
        codes = params.split(';') if params else ['0']
        i = 0
        while i < len(codes):
            try: c = int(codes[i]) if codes[i] else 0
            except ValueError: i += 1; continue
            if   c == 0:  self.color = self.default; self.bold = self.underline = self.dim = False
            elif c == 1:  self.bold = True
            elif c == 2:  self.dim = True
            elif c == 22: self.bold = self.dim = False
            elif c == 4:  self.underline = True
            elif c == 24: self.underline = False
            elif 30 <= c <= 37: self.color = _PALETTE[c - 30]
            elif 90 <= c <= 97: self.color = _PALETTE[c - 90 + 8]
            elif c == 39: self.color = self.default
            elif c in (38, 48, 58):
                mode = codes[i + 1] if i + 1 < len(codes) else ''
                new = None
                if mode == '5' and i + 2 < len(codes):
                    try: new = _ansi256(int(codes[i + 2]))
                    except ValueError: pass
                    i += 2
                elif mode == '2' and i + 4 < len(codes):
                    try: new = _hex((int(codes[i + 2]), int(codes[i + 3]), int(codes[i + 4])))
                    except ValueError: pass
                    i += 4
                if c == 38 and new: self.color = new      # 48 (background) / 58 are skipped
            i += 1


# --- layout / small utils ---------------------------------------------------
def layout_columns(widths, term_cols, gap=2):
    """Column-major layout like `ls`. widths = label widths.
    Returns (nrows, [column widths]); item (row r, col c) is index c*nrows + r."""
    n = len(widths)
    if n == 0:
        return 0, []
    upper = min(n, max(1, term_cols // (min(widths) + gap) + 1))
    for ncols in range(upper, 0, -1):
        nrows = -(-n // ncols)
        cols = [widths[c * nrows:(c + 1) * nrows] for c in range(ncols)]
        colw = [max(c) for c in cols if c]
        if ncols == 1 or sum(colw) + gap * (len(colw) - 1) <= term_cols:
            return nrows, colw
    return n, [max(widths)]


def suggest_from_history(history, text):
    """Fish-style inline suggestion: rest of the newest history entry that starts with text."""
    if not text or text.isspace():
        return ''
    for cmd in reversed(history):
        if len(cmd) > len(text) and cmd.startswith(text):
            return cmd[len(text):]
    return ''


def fmt_elapsed(s):
    if s < 60: return f"{s:.1f}s"
    return f"{int(s // 60)}m {s % 60:.0f}s"


# --- ripple maths -----------------------------------------------------------
def ripple_params(t, dur, max_r):
    """Wavefront radius and brightness envelope t seconds after spawn.
    Fast ease-out expansion, quick fade-in, long soft fade-out."""
    p = min(1.0, max(0.0, t / dur))
    r = max_r * 1.06 * (1.0 - (1.0 - p) ** 2.6)
    env = min(1.0, t / 0.045) * (1.0 - p) ** 1.45
    return r, env, p

def ring_stops(R, tail, lead):
    """Radial-gradient stops (position 0..1, strength 0..1) for a ring whose crest is at
    radius R: soft glow behind the crest (tail px), a bright crest, a short soft lead."""
    Rg = R + lead
    pts = ((R - tail, 0.0), (R - tail * 0.60, 0.04), (R - tail * 0.25, 0.16),
           (R - 2.0, 0.55), (R, 1.0), (Rg, 0.0))
    return Rg, [(min(1.0, max(0.0, d / Rg)), a) for d, a in pts]

def dot_level(d, R, band):
    """How strongly a lattice dot at distance d from the origin lights up (0..1)."""
    u = (d - (R - 0.35 * band)) / (0.5 * band)
    return math.exp(-u * u)


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
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(14, self.height() - 1, max(0, self.width() - 28), 1, QColor(255, 255, 255, 14))
        p.end()
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
#  Window surface — gradient body, corner glows, hairline border
# ─────────────────────────────────────────────────────────────
class Surface(QWidget):
    def __init__(self, radius=12, parent=None):
        super().__init__(parent)
        self._radius = radius

    def set_radius(self, r):
        self._radius = r
        self.update()

    def paintEvent(self, ev):
        w, h = self.width(), self.height()
        r = float(self._radius)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)

        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.0, QColor(14, 17, 21))
        base.setColorAt(1.0, QColor(7, 8, 10))
        p.fillPath(path, QBrush(base))

        glow = QRadialGradient(QPointF(w * 0.12, -h * 0.05), w * 0.65)
        glow.setColorAt(0.0, QColor(*TEAL, 26))
        glow.setColorAt(1.0, QColor(*TEAL, 0))
        p.fillPath(path, QBrush(glow))

        glow2 = QRadialGradient(QPointF(w * 0.95, h * 1.02), w * 0.55)
        glow2.setColorAt(0.0, QColor(*VIOLET, 24))
        glow2.setColorAt(1.0, QColor(*VIOLET, 0))
        p.fillPath(path, QBrush(glow2))

        if r > 0:   # hairline edge, teal → neutral → violet
            edge = QLinearGradient(0, 0, w, h)
            edge.setColorAt(0.0, QColor(*TEAL, 90))
            edge.setColorAt(0.5, QColor(255, 255, 255, 22))
            edge.setColorAt(1.0, QColor(*VIOLET, 90))
            p.setPen(QPen(QBrush(edge), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r - 0.5, r - 0.5)
        p.end()


# ─────────────────────────────────────────────────────────────
#  Shock ripple
#  A thin bright crest with a soft glow behind it, a violet echo
#  ring, a bloom at the origin, and a dot lattice that lights up
#  as the front passes.  Time-based (not frame-based), additive
#  light blending, several waves can overlap.
# ─────────────────────────────────────────────────────────────
class ShockRipple(QWidget):
    SPACING   = 18     # dot lattice pitch in px
    MAX_WAVES = 3
    GLOW      = 0.75   # strength of the soft glow behind the crest
    CREST     = (190, 255, 248)
    ECHO_BODY = VIOLET
    ECHO_CREST = (170, 150, 255)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self._waves = []
        self._clip_radius = 12
        self._brushes = {}
        self._t = QTimer(self)
        self._t.setTimerType(Qt.TimerType.PreciseTimer)
        self._t.timeout.connect(self._step)

    def set_clip_radius(self, r):
        self._clip_radius = max(0, int(r))
        self.update()

    def spawn(self, x, y, color=TEAL, strength=1.0):
        w, h = max(1, self.width()), max(1, self.height())
        max_r = max(math.hypot(cx - x, cy - y) for cx, cy in ((0, 0), (w, 0), (0, h), (w, h)))
        dur = min(1.7, max(0.85, 0.55 + max_r / 1100.0))
        lift = tuple(int(c * 0.65 + 255 * 0.35) for c in color)      # dots: lighter than the ring
        self._waves.append({"x": x, "y": y, "c": tuple(color), "dot": lift, "s": strength,
                            "t0": time.perf_counter(), "max_r": max_r, "dur": dur})
        del self._waves[:-self.MAX_WAVES]
        if not self._t.isActive():
            self._t.start(16)
        self.update()

    def _step(self):
        now = time.perf_counter()
        self._waves = [w for w in self._waves if now - w["t0"] < w["dur"]]
        if not self._waves:
            self._t.stop()
        self.update()

    # --- painting ---------------------------------------------------------
    def paintEvent(self, ev):
        if not self._waves:
            return
        now = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._clip_radius > 0:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), self._clip_radius, self._clip_radius)
            p.setClipPath(clip)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)   # light adds up
        p.setPen(Qt.PenStyle.NoPen)
        for w in self._waves:
            self._paint_wave(p, w, now - w["t0"])
        p.end()

    def _paint_wave(self, p, w, t):
        x, y, s = w["x"], w["y"], w["s"]
        R, env, prog = ripple_params(t, w["dur"], w["max_r"])
        a = env * s
        if R < 1.0 or a < 0.01:
            return
        c = QPointF(x, y)
        r, g, b = w["c"]

        if prog < 0.3:                                   # bloom at the origin
            k = 1.0 - prog / 0.3
            rad = 40.0 + 90.0 * prog / 0.3
            bloom = QRadialGradient(c, rad)
            bloom.setColorAt(0.0, QColor(r, g, b, int(110 * k * s)))
            bloom.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(QBrush(bloom))
            p.drawEllipse(c, rad, rad)

        te = t - 0.12                                    # delayed violet echo
        if te > 0:
            R2, env2, _ = ripple_params(te, w["dur"], w["max_r"])
            self._ring(p, c, R2, env2 * s * 0.5, self.ECHO_BODY, self.ECHO_CREST)

        self._ring(p, c, R, a, (r, g, b), self.CREST)
        if R > 24:
            self._dots(p, x, y, R, a, w["dot"])

    def _ring(self, p, c, R, a, body, crest):
        if R < 1.0 or a < 0.01:
            return
        tail = 0.20 * R + 22.0
        lead = 5.0 + 0.01 * R
        Rg, stops = ring_stops(R, tail, lead)
        grad = QRadialGradient(c, Rg)
        for pos, st in stops:
            mix = st * st
            col = tuple(int(body[i] + (crest[i] - body[i]) * mix) for i in range(3))
            alpha = int(255 * min(1.0, st * a * self.GLOW))
            grad.setColorAt(pos, QColor(col[0], col[1], col[2], alpha))
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addEllipse(c, Rg, Rg)
        inner = R - tail
        if inner > 0:
            path.addEllipse(c, inner, inner)
        p.fillPath(path, QBrush(grad))

        p.setPen(QPen(QColor(crest[0], crest[1], crest[2], int(255 * min(1.0, a * 0.75))), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R, R)
        p.setPen(Qt.PenStyle.NoPen)

    def _brush(self, color, level):
        key = (color, level)
        b = self._brushes.get(key)
        if b is None:
            b = QBrush(QColor(color[0], color[1], color[2], int(235 * level / 15)))
            self._brushes[key] = b
        return b

    def _dots(self, p, x, y, R, a, color):
        sp = self.SPACING
        band = 0.14 * R + 30.0
        outer = R + 8.0
        inner = max(0.0, R - band * 1.4)
        w, h = self.width(), self.height()
        row0 = max(0, int((y - outer) // sp))
        row1 = min(int(h // sp), int((y + outer) // sp))
        for row in range(row0, row1 + 1):
            cy = row * sp + sp / 2.0
            dy = cy - y
            ady = abs(dy)
            if ady > outer:
                continue
            xo = math.sqrt(outer * outer - dy * dy)
            if ady < inner:
                xi = math.sqrt(inner * inner - dy * dy)
                spans = ((x - xo, x - xi), (x + xi, x + xo))
            else:
                spans = ((x - xo, x + xo),)
            for lo, hi in spans:
                c0 = max(0, int(lo // sp))
                c1 = min(int(w // sp), int(hi // sp))
                for col in range(c0, c1 + 1):
                    cx = col * sp + sp / 2.0
                    d = math.hypot(cx - x, dy)
                    i = dot_level(d, R, band) * a
                    if i < 0.06:
                        continue
                    p.setBrush(self._brush(color, min(15, int(i * 16))))
                    rad = 0.9 + 1.9 * i
                    p.drawEllipse(QPointF(cx, cy), rad, rad)


# ─────────────────────────────────────────────────────────────
#  Glow input — soft field, gradient focus border, ghost suggestion
# ─────────────────────────────────────────────────────────────
class GlowInput(QLineEdit):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._phase = 0.0
        self._ghost = ""
        self._t = QTimer(self); self._t.timeout.connect(self._tick)   # only runs while focused

    def ghost(self): return self._ghost
    def set_ghost(self, s):
        if s != self._ghost:
            self._ghost = s; self.update()

    def focusInEvent(self, e):
        super().focusInEvent(e); self._t.start(40)
    def focusOutEvent(self, e):
        super().focusOutEvent(e); self._t.stop(); self.update()

    def _tick(self):
        self._phase = (self._phase + 0.08) % (6.2831 * 2); self.update()

    def paintEvent(self, ev):
        focus = self.hasFocus()
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 11 if focus else 6))       # soft field behind the text
        p.drawRoundedRect(box, 6, 6)
        p.end()

        super().paintEvent(ev)

        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if focus:
            k = 0.5 + 0.5 * math.sin(self._phase)
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0.0, QColor(*TEAL, int(80 + 60 * k)))
            g.setColorAt(1.0, QColor(*VIOLET, int(60 + 50 * (1 - k))))
            p.setPen(QPen(QBrush(g), 1.0))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
        p.drawRoundedRect(box, 6, 6)

        if focus and self._ghost and self.cursorPosition() == len(self.text()) \
                and not self.hasSelectedText():
            fm = self.fontMetrics()
            cr = self.cursorRect()
            x = cr.x() + 1
            room = self.width() - x - 10
            if room > 12:
                p.setFont(self.font())
                p.setPen(QColor(150, 170, 185, 95))
                p.drawText(QPointF(x, cr.y() + fm.ascent()),
                           fm.elidedText(self._ghost, Qt.TextElideMode.ElideRight, room))
        p.end()


# ─────────────────────────────────────────────────────────────
#  Progress bars
# ─────────────────────────────────────────────────────────────
class SmoothBar(QProgressBar):
    def __init__(self, name="", parent=None):
        super().__init__(parent)
        self.setTextVisible(False); self.setRange(0, 100); self.setFixedHeight(12)
        self._val = 0.0; self._target = 0.0
        self.setStyleSheet("""
            QProgressBar {
                background: rgba(10, 11, 13, 100);
                border: none;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #00d9c8, stop:1 #8060d0);
            }
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
#  Shell worker — streams raw chunks (prompts without newline,
#  \r progress bars), accepts stdin, kills the whole process tree
# ─────────────────────────────────────────────────────────────
class ShellWorker(QThread):
    chunk = pyqtSignal(str); done = pyqtSignal(int)

    def __init__(self, cmd, cwd=None, env=None):
        super().__init__(); self.cmd, self.cwd, self.env = cmd, cwd, env
        self.proc = None; self._killed = False
        self._pending = []; self._lock = threading.Lock()   # input typed before the process exists
        self._dec = codecs.getincrementaldecoder('utf-8')(errors='strict')
        self._fallback = 'latin-1'
        if os.name == 'nt':                       # cmd.exe & friends talk in the OEM code page
            try:
                import ctypes
                self._fallback = 'cp%d' % ctypes.windll.kernel32.GetOEMCP()
            except Exception:
                self._fallback = 'cp850'

    def _decode(self, data):
        try:
            return self._dec.decode(data)
        except UnicodeDecodeError:
            self._dec.reset()
            return data.decode(self._fallback, errors='replace')

    def run(self):
        try:
            kw = dict(shell=True, cwd=self.cwd, env=self.env, bufsize=0,
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if os.name == 'nt':
                kw['creationflags'] = subprocess.CREATE_NO_WINDOW
            else:
                kw['start_new_session'] = True    # own process group, so Ctrl+C reaches children
            self.proc = subprocess.Popen(self.cmd, **kw)
            with self._lock:
                early, self._pending = self._pending, None
            for line in early: self.send(line)
            fd = self.proc.stdout.fileno()
            while True:
                data = os.read(fd, 8192)
                if not data or self._killed:
                    break
                text = self._decode(data)
                if text:
                    self.chunk.emit(text)
            self.proc.wait()
            self.done.emit(130 if self._killed else self.proc.returncode)
        except Exception as e:
            self.chunk.emit(f"[error] {e}\n"); self.done.emit(1)

    def send(self, text):
        with self._lock:
            if self._pending is not None:
                self._pending.append(text); return
        p = self.proc
        if p and p.stdin and not p.stdin.closed:
            try: p.stdin.write((text + "\n").encode('utf-8', 'replace'))
            except Exception: pass

    def close_stdin(self):
        p = self.proc
        if p and p.stdin and not p.stdin.closed:
            try: p.stdin.close()
            except Exception: pass

    def kill(self):
        self._killed = True
        p = self.proc
        if not p or p.poll() is not None: return
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            try: p.kill()
            except Exception: pass


# ─────────────────────────────────────────────────────────────
#  Typewriter
#  - queue of (text, style) runs, no per-character tuples
#  - \r overwrites the current line (progress bars)
#  - follows new output only while you are at the bottom
#  - scrollback is capped
#  - timer only runs while there is something to type
# ─────────────────────────────────────────────────────────────
class Typewriter:
    DEFAULT = "#b8c8d4"

    def __init__(self, te: QTextEdit, max_blocks=8000):
        self.te = te
        self._q = deque(); self._n = 0
        self._fmts = {}
        self._cr = False
        self._last = "\n"
        self._follow = True; self._auto = False
        self.ansi = AnsiStream(self.DEFAULT)
        te.setUndoRedoEnabled(False)
        te.document().setMaximumBlockCount(max_blocks)
        te.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._t = QTimer(); self._t.timeout.connect(self._tick)

    # --- public API ---
    def write(self, text, color=DEFAULT, bold=False, underline=False):
        self._enqueue(text, (color, bold, underline))

    def write_ansi(self, text):
        for chunk, style in self.ansi.feed(text):
            self._enqueue(chunk, style)

    def ensure_newline(self):
        if self._last != "\n":
            self.write("\n")

    def follow(self):
        self._follow = True; self._scroll_bottom()

    def discard(self):
        self._q.clear(); self._n = 0; self._cr = False; self._last = "\n"
        self.follow()

    # --- internals ---
    def _enqueue(self, text, style):
        if not text: return
        self._q.append((text, style)); self._n += len(text); self._last = text[-1]
        if not self._t.isActive(): self._t.start(8)

    def _on_scroll(self, v):
        if not self._auto:
            self._follow = v >= self.te.verticalScrollBar().maximum() - 4

    def _scroll_bottom(self):
        sb = self.te.verticalScrollBar()
        self._auto = True; sb.setValue(sb.maximum()); self._auto = False

    def _settle(self):
        if self._follow: self._scroll_bottom()

    def _tick(self):
        n = self._n
        if n == 0:
            self._t.stop(); return
        if   n > 4000: batch = n
        elif n > 800:  batch = 500
        elif n > 200:  batch = 60
        elif n > 50:   batch = 8
        else:          batch = 2
        self._insert(batch)
        if self._n == 0:
            QTimer.singleShot(0, self._settle)     # layout is final now

    def _take(self, n):
        out = []
        while n > 0 and self._q:
            text, style = self._q[0]
            if len(text) <= n:
                self._q.popleft(); out.append((text, style)); n -= len(text); self._n -= len(text)
            else:
                out.append((text[:n], style)); self._q[0] = (text[n:], style)
                self._n -= n; n = 0
        return out

    def _fmt(self, style):
        f = self._fmts.get(style)
        if f is None:
            color, bold, underline = style
            f = QTextCharFormat(); f.setForeground(QColor(color))
            if bold: f.setFontWeight(700)
            if underline: f.setFontUnderline(True)
            self._fmts[style] = f
        return f

    def _insert(self, batch):
        runs = self._take(batch)
        if not runs: return
        cur = QTextCursor(self.te.document())     # private cursor: never touches the user's selection
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.beginEditBlock()
        for text, style in runs:
            fmt = self._fmt(style)
            for i, part in enumerate(text.split('\r')):
                if i: self._cr = True
                if not part: continue
                if self._cr:
                    self._cr = False
                    if part[0] != '\n':           # lone \r: rewrite the current line
                        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock,
                                         QTextCursor.MoveMode.KeepAnchor)
                        cur.removeSelectedText()
                cur.insertText(part, fmt)
        cur.endEditBlock()
        if self._follow: self._scroll_bottom()


# ─────────────────────────────────────────────────────────────
#  Main window
# ─────────────────────────────────────────────────────────────
class FancyTerminal(QWidget):
    RESIZE_MARGIN = 10
    RADIUS = 12
    KNOWN_CMDS = ["help","clear","exit","demo","cd","pwd","history",
                  "echo","alias","export","unset"]
    LINUX_CMDS = ("ls","cat","touch","mkdir","rmdir","rm","cp","mv","which","type","whoami",
                  "uname","env","date","df","du","head","tail","wc","grep","find","tree")
    WIN_CMDS   = ("dir","copy","del","cls","ren","rename","md","rd","set","start","ver","vol",
                  "move","title","color","path","pushd","popd","mklink","assoc")
    HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".fancy_terminal_history")
    HISTORY_MAX  = 2000
    PLACEHOLDER  = "type a command..."
    RUNNING_HINT = "running · Enter sends input · Ctrl+C stops · Ctrl+D closes stdin"
    INPUT_OK, INPUT_BAD = "#d0dde6", "#e8808e"
    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _FILTER_TYPES = {QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove,
                     QEvent.Type.Resize, QEvent.Type.KeyPress}

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fancy Terminal")
        # NoDropShadowWindowHint prevents the Windows 11 1px border outline;
        # the soft shadow is painted by hand in paintEvent instead.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
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
        # children are piped, not a tty: ask them to flush immediately, speak UTF-8 and keep colours
        for k, v in (("PYTHONUNBUFFERED", "1"), ("PYTHONUTF8", "1"), ("PYTHONIOENCODING", "utf-8"),
                     ("FORCE_COLOR", "1"), ("CLICOLOR_FORCE", "1"), ("PY_COLORS", "1")):
            self._env.setdefault(k, v)
        self._path_cache = None
        self._which_cache = {}
        self._cmd_start = None
        self._search_matches = None
        self._search_idx = 0
        self._font_size = 11
        self._busy = False
        self._input_bad = False
        self._spin_i = 0
        self._hist_prefix = None
        self._nav = False                 # True while Up/Down is filling the input
        self.worker = None
        self._history = self._load_history()
        self._hist_idx = len(self._history)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(self.RESIZE_MARGIN, self.RESIZE_MARGIN,
                                       self.RESIZE_MARGIN, self.RESIZE_MARGIN)
        self._outer.setSpacing(0)

        self._container = Surface(self.RADIUS); self._container.setObjectName("container")
        self._container.setMouseTracking(True)
        self._outer.addWidget(self._container)
        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(0, 0, 0, 0); inner.setSpacing(0)

        self._titlebar = TitleBar(self)
        inner.addWidget(self._titlebar)

        content = QWidget(); content.setStyleSheet("background:transparent;")
        c = QVBoxLayout(content)
        c.setContentsMargins(14, 6, 14, 10); c.setSpacing(6)
        inner.addWidget(content, stretch=1)

        # Output — transparent
        self.out = QTextEdit(); self.out.setReadOnly(True)
        self.out.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #c8d8e4;
                border: none;
                padding: 4px 2px;
                selection-background-color: rgba(0, 217, 200, 70);
                selection-color: #ffffff;
            }
            QScrollBar:vertical { background:transparent; width:8px; border:none; margin:0; }
            QScrollBar::handle:vertical { background: rgba(70, 84, 98, 150); min-height:24px; border-radius:4px; }
            QScrollBar::handle:vertical:hover { background: rgba(0, 217, 200, 140); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; background:none; border:none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }
            QScrollBar:horizontal { background:transparent; height:8px; border:none; margin:0; }
            QScrollBar::handle:horizontal { background: rgba(70, 84, 98, 150); min-width:24px; border-radius:4px; }
            QScrollBar::handle:horizontal:hover { background: rgba(0, 217, 200, 140); }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; background:none; border:none; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:none; }
        """)
        c.addWidget(self.out, stretch=1)

        self.prog_box = QVBoxLayout(); self.prog_box.setSpacing(2)
        c.addLayout(self.prog_box)
        self.progress = ProgressGroup(self.prog_box)

        irow = QHBoxLayout(); irow.setSpacing(6)
        self.prompt = QLabel("λ")
        self.prompt.setStyleSheet(self._prompt_css("#00d9c8"))
        self.prompt.setFixedWidth(14)
        self.input = GlowInput()
        self.input.setPlaceholderText(self.PLACEHOLDER)
        self.input.setStyleSheet(self._input_css(self.INPUT_OK))
        self.input.returnPressed.connect(self._submit)
        self.input.textChanged.connect(self._on_input_changed)
        self.input.textEdited.connect(self._on_input_edited)
        self.input.installEventFilter(self)
        irow.addWidget(self.prompt); irow.addWidget(self.input)
        c.addLayout(irow)

        self.wave = ShockRipple(self._container)
        self.wave.setGeometry(self._container.rect())
        self.wave.set_clip_radius(self.RADIUS)
        self.wave.lower()
        self._container.installEventFilter(self)

        self.setStyleSheet("QLabel { color:#b8c8d4; background:transparent; }")
        self.tw = Typewriter(self.out)
        self._spin_t = QTimer(self); self._spin_t.timeout.connect(self._spin_tick)

        self._apply_fonts()
        self._reset_output()
        self._update_cwd_label()
        self.input.setFocus()
        self._insert_logo()
        self._write_welcome()
        self._apply_shape()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        QTimer.singleShot(60, lambda: self._complete_command(""))     # warm the PATH cache

    # --- look & feel helpers ---
    @staticmethod
    def _mono(size):
        f = QFont()
        f.setFamilies(["Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Consolas",
                       "DejaVu Sans Mono", "Menlo", "Monospace"])
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(size)
        return f

    def _apply_fonts(self):
        self.out.setFont(self._mono(self._font_size))
        self.input.setFont(self._mono(self._font_size + 1))
        self.out.setTabStopDistance(self.out.fontMetrics().horizontalAdvance(' ') * 8)

    def _zoom(self, delta):
        self._font_size = 11 if delta == 0 else max(8, min(24, self._font_size + delta))
        self._apply_fonts()

    def _reset_output(self):
        """Clear the output and re-apply the line spacing (a cleared document forgets it)."""
        self.out.clear()
        try:
            cur = QTextCursor(self.out.document())
            bf = QTextBlockFormat()
            bf.setLineHeight(116.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            cur.setBlockFormat(bf)
        except Exception:
            pass

    def _insert_logo(self):
        """Logo with a teal → violet gradient across the columns."""
        cur = QTextCursor(self.out.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        lines = ASCII_LOGO.split("\n")
        width = max(len(l) for l in lines)
        for li, line in enumerate(lines):
            for ci, ch in enumerate(line):
                fmt = QTextCharFormat()
                t = min(1.0, ci / max(1, width - 1) * 0.9 + li * 0.05)
                fmt.setForeground(QColor(*_lerp_rgb(TEAL, VIOLET, t)))
                cur.insertText(ch, fmt)
            cur.insertText("\n")
        cur.insertText("\n")

    @staticmethod
    def _prompt_css(color):
        return f"color:{color}; font-family:Consolas; font-size:14px; background:transparent;"

    @staticmethod
    def _input_css(color):
        return ("QLineEdit { background: transparent; color:%s; border: none; border-radius: 4px;"
                " padding: 8px 8px; selection-background-color: #00d9c8; selection-color: #08090c; }" % color)

    def _short_cwd(self):
        home = os.path.expanduser("~"); p = self._cwd
        if p == home: p = "~"
        elif p.startswith(home + os.sep): p = "~" + p[len(home):]
        return p.replace(os.sep, "/")

    # --- history ---
    def _load_history(self):
        try:
            with open(self.HISTORY_FILE, 'r', encoding='utf-8', errors='replace') as fh:
                return [l.rstrip('\n') for l in fh if l.strip()][-self.HISTORY_MAX:]
        except OSError:
            return []

    def _remember(self, cmd):
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
            try:
                with open(self.HISTORY_FILE, 'a', encoding='utf-8') as fh:
                    fh.write(cmd + "\n")
            except OSError:
                pass
        self._hist_idx = len(self._history)
        self._hist_prefix = None

    def _history_step(self, d):
        """Up/Down: walk history entries that start with what you had typed (zsh/fish style)."""
        h = self._history
        if not h: return
        if self._hist_prefix is None:
            self._hist_prefix = self.input.text()
            self._hist_idx = len(h)
        pre, cur_text = self._hist_prefix, self.input.text()
        i = self._hist_idx + d
        while 0 <= i < len(h) and (not h[i].startswith(pre) or h[i] == cur_text):
            i += d
        if i < 0:
            return
        self._nav = True
        try:
            if i >= len(h):
                self._hist_idx = len(h)
                self.input.setText(pre)
            else:
                self._hist_idx = i
                self.input.setText(h[i])
            self.input.end(False)
        finally:
            self._nav = False

    # --- input reactions ---
    def _on_input_edited(self, text):
        self._hist_prefix = None
        self._hist_idx = len(self._history)

    def _on_input_changed(self, text):
        try:
            self.input.set_ghost("" if self._nav else suggest_from_history(self._history, text))
            bad = self._command_unknown(text)
            if bad != self._input_bad:
                self._input_bad = bad
                self.input.setStyleSheet(self._input_css(self.INPUT_BAD if bad else self.INPUT_OK))
        except Exception:
            pass

    def _command_unknown(self, text):
        t = text.lstrip()
        if not t: return False
        first = t.split(None, 1)[0]
        if first[0] in "!-" or any(ch in first for ch in "/\\:.~\"'=$%"):
            return False                                   # paths, env vars, history expansion…
        low = first.lower()
        if ' ' not in t:                                   # still typing the first word: prefix is enough
            return not (self._complete_command(first)
                        or any(a.startswith(low) for a in self._aliases)
                        or any(c.startswith(low) for c in self.LINUX_CMDS))
        return not self._command_exists(first)

    def _command_exists(self, name):
        low = name.lower()
        if low in self.KNOWN_CMDS or name in self._aliases or low in self.LINUX_CMDS:
            return True
        if os.name == 'nt' and low in self.WIN_CMDS:
            return True
        r = self._which_cache.get(name)
        if r is None:
            r = bool(shutil.which(name)); self._which_cache[name] = r
        return r

    # --- running state ---
    def _paint_prompt(self, ok):
        self.prompt.setStyleSheet(self._prompt_css("#00d9c8" if ok else "#e05a6a"))

    def _set_busy(self, busy):
        self._busy = busy
        if busy:
            self.prompt.setStyleSheet(self._prompt_css("#8060d0"))
            self.input.setPlaceholderText(self.RUNNING_HINT)
            self._spin_t.start(80)
        else:
            self._spin_t.stop()
            self.prompt.setText("λ")
            self.input.setPlaceholderText(self.PLACEHOLDER)

    def _spin_tick(self):
        self._spin_i = (self._spin_i + 1) % len(self.SPIN)
        self.prompt.setText(self.SPIN[self._spin_i])

    def _error_ripple(self):
        if self.wave.width() <= 0: return
        gp = self.input.mapToGlobal(QPoint(16, self.input.height() // 2))
        lp = self.wave.mapFromGlobal(gp)
        self.wave.spawn(lp.x(), lp.y(), color=(235, 80, 100), strength=0.7)

    def closeEvent(self, ev):
        try:
            if self._busy and self.worker is not None:
                self.worker.kill(); self.worker.wait(800)
        except Exception:
            pass
        super().closeEvent(ev)

    # --- columns (ls, tab completion) ---
    def _term_cols(self):
        cw = max(1, self.out.fontMetrics().horizontalAdvance('M'))
        return max(24, self.out.viewport().width() // cw - 2)

    def _write_columns(self, items, indent=0, gap=2):
        """items = [(label, colour)], laid out column-major like `ls`."""
        if not items: return
        nrows, colw = layout_columns([len(l) for l, _ in items], self._term_cols() - indent, gap)
        ncols, pad = len(colw), ' ' * indent
        for r in range(nrows):
            self.tw.write(pad)
            for c in range(ncols):
                idx = c * nrows + r
                if idx >= len(items): break
                label, color = items[idx]
                last = c == ncols - 1 or idx + nrows >= len(items)
                self.tw.write(label if last else label.ljust(colw[c] + gap), color)
            self.tw.write("\n")

    # --- system-stats helpers ---
    def _greeting(self):
        h = datetime.datetime.now().hour
        if 5 <= h < 12:  return "Good morning"
        if 12 <= h < 18: return "Good afternoon"
        if 18 <= h < 23: return "Good evening"
        return "Working late"

    def _write_bar(self, label, pct, width=14):
        tw, dim = self.tw, "#3a4450"
        tw.write(f"  {label:<9} ", color="#8fa8bc")
        try:
            p = max(0.0, min(100.0, float(pct)))
        except (TypeError, ValueError):
            tw.write("[" + "·" * width + "]   n/a\n", color=dim); return
        filled = int(round(width * p / 100.0))
        col = "#00d9c8" if p < 60 else "#e0b050" if p < 85 else "#e05a6a"
        tw.write("[", color=dim); tw.write("█" * filled, color=col)
        tw.write("░" * (width - filled), color=dim); tw.write("]", color=dim)
        tw.write(f" {p:5.1f}%\n", color="#8fa8bc")

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

        cwd_disp = self._short_cwd()

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
        self._write_bar("cpu", cpu_pct)
        self._write_bar("gpu", gpu_pct)
        self._write_bar("ram", ram_pct)
        self.tw.write(f"\n  {now.strftime('%A, %B %d %Y')} · {now.strftime('%H:%M')}\n\n",
                      color="#6f8898")
        self.tw.write("Type 'help' for commands · Tab completes · → accepts the grey suggestion.\n\n", color="#6f8898")

    # --- paint & shape ---
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        maximized = self.isMaximized() or self.isFullScreen()
        if not maximized:
            # hand-painted soft shadow in the transparent margin
            m = self.RESIZE_MARGIN
            base = QRectF(self._container.geometry())
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(m, 0, -1):
                p.setBrush(QColor(0, 0, 0, 2 + int(5 * (1.0 - i / m))))
                p.drawRoundedRect(base.adjusted(-i, -i + 2, i, i + 2), self.RADIUS + i, self.RADIUS + i)
        # (almost) invisible fill so the transparent margin still receives mouse events for resizing
        path = QPainterPath()
        if maximized:
            path.addRect(QRectF(self.rect()))
        else:
            path.addRoundedRect(QRectF(self.rect()), self.RADIUS + self.RESIZE_MARGIN,
                                self.RADIUS + self.RESIZE_MARGIN)
        p.fillPath(path, QColor(0, 0, 0, 1))

    def _apply_shape(self):
        maximized = self.isMaximized() or self.isFullScreen()
        m = 0 if maximized else self.RESIZE_MARGIN
        self._outer.setContentsMargins(m, m, m, m)
        r = 0 if maximized else self.RADIUS
        self._container.set_radius(r)
        if hasattr(self, "wave"):
            self.wave.set_clip_radius(r)
            self.wave.lower()

    def _update_cwd_label(self):
        self._titlebar.set_cwd(self._short_cwd())

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == ev.Type.WindowStateChange:
            self._apply_shape(); QTimer.singleShot(0, self._sync_wave)
    def _sync_wave(self):
        if hasattr(self, "wave"):
            self.wave.setGeometry(self._container.rect())
            self.wave.lower()

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

    # --- keyboard / event filter ---
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t not in self._FILTER_TYPES:          # app-wide filter: bail out fast for everything else
            return False

        if t == ev.Type.MouseButtonPress and isinstance(obj, QWidget):
            try:
                if obj.window() is self and obj is not self.input and obj is not self.wave:
                    self.input.setFocus()
            except Exception:
                pass

        if obj is self._container:
            if t == ev.Type.Resize:
                self._sync_wave()
            elif t == ev.Type.MouseMove and not self._resize_edge:
                wp = self._container.mapTo(self, ev.position().toPoint())
                e = self._edge_at(wp, expanded=True)
                self.setCursor(self._cursor_for(e)) if e else self.unsetCursor()
            elif (t == ev.Type.MouseButtonPress
                  and ev.button() == Qt.MouseButton.LeftButton
                  and not self._resize_edge):
                wp = self._container.mapTo(self, ev.position().toPoint())
                e = self._edge_at(wp, expanded=True)
                if e:
                    self._resize_edge = e
                    self._resize_start_geo = self.geometry()
                    self._resize_start_pos = ev.globalPosition().toPoint()
                    self.grabMouse(); return True
        if obj is self.input and t == ev.Type.KeyPress:
            if self._on_key(ev):
                return True
        return super().eventFilter(obj, ev)

    def _on_key(self, ev):
        """Returns True when the key was handled here."""
        key, mods, inp = ev.key(), ev.modifiers(), self.input
        K = Qt.Key
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        plain = not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                             | Qt.KeyboardModifier.ShiftModifier))
        if ctrl and key == K.Key_R:
            self._reverse_search(); return True
        self._search_matches = None

        if ctrl and key == K.Key_C:
            if self.out.textCursor().hasSelection():          # copy a selection from the output
                self.out.copy(); return True
            if inp.hasSelectedText(): return False             # normal copy inside the input
            if self._busy and self.worker is not None:
                self.worker.kill(); self.tw.write("^C\n", color="#e05a6a")
            elif inp.text():
                self.tw.write(f"{self._short_cwd()} λ {inp.text()}^C\n", color="#6f8898")
                inp.clear()
            return True
        if ctrl and key == K.Key_L:
            self.tw.discard(); self._reset_output(); return True
        if ctrl and key == K.Key_U: inp.clear(); return True
        if ctrl and key == K.Key_W:
            cur = inp.cursorPosition(); t = inp.text()
            new_t = re.sub(r'\S+\s*$', '', t[:cur])
            inp.setText(new_t + t[cur:]); inp.setCursorPosition(len(new_t)); return True
        if ctrl and key == K.Key_K:
            inp.setText(inp.text()[:inp.cursorPosition()]); return True
        if ctrl and key == K.Key_D:
            if not inp.text():
                if self._busy and self.worker is not None: self.worker.close_stdin()   # EOF
                else: self.close()
            return True
        if ctrl and key in (K.Key_Plus, K.Key_Equal): self._zoom(+1); return True
        if ctrl and key == K.Key_Minus:               self._zoom(-1); return True
        if ctrl and key == K.Key_0:                   self._zoom(0);  return True

        if key == K.Key_Escape and plain:
            inp.clear(); return True
        if key in (K.Key_PageUp, K.Key_PageDown):
            sb = self.out.verticalScrollBar()
            step = sb.pageStep() * (-1 if key == K.Key_PageUp else 1)
            sb.setValue(sb.value() + step); return True
        if key in (K.Key_Right, K.Key_End) and plain and inp.ghost() \
                and inp.cursorPosition() == len(inp.text()) and not inp.hasSelectedText():
            inp.setText(inp.text() + inp.ghost()); inp.end(False); return True   # accept suggestion
        if key == K.Key_Up:   self._history_step(-1); return True
        if key == K.Key_Down: self._history_step(+1); return True
        if key == K.Key_Tab:  self._tab_complete();   return True
        return False

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
        self._write_columns([(c, "#8060d0") for c in candidates], indent=2)

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

        # a command is running: Enter feeds its stdin
        if self._busy and self.worker is not None:
            self.input.clear()
            self.tw.write(raw + "\n", color="#8fa8bc")
            self.worker.send(raw)
            return

        if not raw.strip(): self.input.clear(); return

        # ripple starts under the last word you typed
        fm = self.input.fontMetrics()
        trimmed = raw.rstrip(); sp = trimmed.rfind(' ')
        last_word = trimmed if sp == -1 else trimmed[sp+1:]
        prefix_w = 0 if sp == -1 else fm.horizontalAdvance(raw[:sp+1])
        if last_word and self.wave.width() > 0:
            wx = 8 + prefix_w; ww = fm.horizontalAdvance(last_word)
            gp = self.input.mapToGlobal(QPoint(int(wx + ww/2), int(self.input.height()/2)))
            lp = self.wave.mapFromGlobal(gp)
            self.wave.spawn(lp.x(), lp.y())

        raw_cmd = self._expand_history(raw.strip())
        text = raw_cmd
        first = text.split()[0] if text.split() else ''
        if first not in self.KNOWN_CMDS and first in self._aliases:
            text = self._aliases[first] + text[len(first):]

        self.input.clear()
        self._remember(raw_cmd)
        self.tw.follow()
        self.tw.write(self._short_cwd() + " ", color="#4f5a66")
        self.tw.write("λ ", color="#00d9c8")
        self.tw.write(raw_cmd + "\n", color="#e4eef5")

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
                "Keys:  Tab complete · → accept suggestion · ↑↓ history (matches what you typed)\n"
                "       Ctrl+R search · Ctrl+C copy / stop · Ctrl+D EOF / exit · Ctrl+L clear\n"
                "       Ctrl+U W K edit · PgUp PgDn scroll · Ctrl + − 0 zoom · Esc clear line\n"
                "While a command runs, Enter sends a line to it.\n\n",
                color="#6f8898")
        elif text == 'clear':
            self.tw.discard(); self._reset_output()
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

    _EXT_ARCHIVE = {'.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.7z', '.rar', '.zst'}
    _EXT_MEDIA   = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico',
                    '.mp3', '.wav', '.flac', '.ogg', '.mp4', '.mkv', '.mov', '.avi', '.webm'}
    _EXT_EXEC    = {'.exe', '.bat', '.cmd', '.ps1', '.com', '.msi', '.sh'}

    def _ls_item(self, name, full):
        """-> (label, colour) for one directory entry."""
        try: st = os.lstat(full)
        except OSError: return name, "#b8c8d4"
        mode = st.st_mode
        if stat.S_ISLNK(mode):
            return name + ('/' if os.path.isdir(full) else '@'), "#00d9c8"
        if stat.S_ISDIR(mode):
            return name + '/', "#5a9fd0"
        ext = os.path.splitext(name)[1].lower()
        if name.startswith('.'):         return name, "#6f8898"
        if ext in self._EXT_ARCHIVE:     return name, "#e0b050"
        if ext in self._EXT_MEDIA:       return name, "#b08cf0"
        if ext in self._EXT_EXEC or (os.name != 'nt' and mode & 0o111):
            return name, "#6fd68f"
        return name, "#b8c8d4"

    def _ls_long(self, path, names):
        now = time.time()
        for e in names:
            full = os.path.join(path, e)
            try: st = os.lstat(full)
            except OSError: continue
            label, color = self._ls_item(e, full)
            if stat.S_ISLNK(st.st_mode) and label.endswith('@'): label = label[:-1]   # '->' says it already
            size = '-' if stat.S_ISDIR(st.st_mode) else self._human(st.st_size)
            try:
                mt = datetime.datetime.fromtimestamp(st.st_mtime)
                when = mt.strftime("%b %d %H:%M") if now - st.st_mtime < 15552000 else mt.strftime("%b %d  %Y")
            except (OSError, OverflowError, ValueError):
                when = "?"
            link = ''
            if stat.S_ISLNK(st.st_mode):
                try: link = ' -> ' + os.readlink(full)
                except OSError: pass
            self.tw.write(f"{stat.filemode(st.st_mode)}  ", color="#4f5a66")
            self.tw.write(f"{size:>6}  ", color="#8fa8bc")
            self.tw.write(f"{when:<12}  ", color="#6f8898")
            self.tw.write(label + link + "\n", color=color)

    def _cmd_ls(self, args):
        args = self._expand_globs(args)
        flags = ''.join(a[1:] for a in args if a.startswith('-') and not a.startswith('--'))
        show_all, long_fmt, one_col = ('a' in flags or 'A' in flags), 'l' in flags, '1' in flags
        targets = [a for a in args if not a.startswith('-')] or ['.']
        for i, t in enumerate(targets):
            path = self._resolve_path(t)
            if os.path.isfile(path):
                try: disp = os.path.relpath(path, self._cwd)
                except ValueError: disp = t
                self.tw.write(disp + "\n"); continue
            if not os.path.isdir(path):
                self.tw.write(f"ls: {t}: no such file or directory\n", color="#e05a6a"); continue
            try: entries = sorted(os.listdir(path), key=str.lower)
            except Exception as e:
                self.tw.write(f"ls: {t}: {e}\n", color="#e05a6a"); continue
            if len(targets) > 1:
                if i > 0: self.tw.write("\n")
                self.tw.write(f"{t}:\n", color="#8fa8bc")
            names = [e for e in entries if show_all or not e.startswith('.')]
            if long_fmt:
                self._ls_long(path, names)
            else:
                items = [self._ls_item(e, os.path.join(path, e)) for e in names]
                if one_col:
                    for label, color in items: self.tw.write(label + "\n", color=color)
                else:
                    self._write_columns(items)
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
        if self.worker is not None:
            self.worker.wait(500)                 # previous thread has fully finished before we drop it
        self._cmd_start = time.time()
        self.tw.ansi.reset()
        self.worker = ShellWorker(cmd, cwd=self._cwd, env=self._env)
        self.worker.chunk.connect(self.tw.write_ansi)
        self.worker.done.connect(self._on_shell_done)
        self._set_busy(True)
        self.worker.start()

    def _on_shell_done(self, code):
        elapsed = time.time() - self._cmd_start if self._cmd_start else 0.0
        killed = code == 130
        self._set_busy(False)
        self._paint_prompt(code == 0)
        self.tw.ensure_newline()
        if code == 0:
            if elapsed >= 1.0:                    # quiet on fast successes
                self.tw.write(f"✓ {fmt_elapsed(elapsed)}\n", color="#2f9d8f")
        else:
            label = "✗ interrupted" if killed else f"✗ exit {code}"
            self.tw.write(f"{label} · {fmt_elapsed(elapsed)}\n", color="#e05a6a")
            if not killed:
                self._error_ripple()
        self.tw.write("\n")


def main():
    def hook(t, v, tb): traceback.print_exception(t, v, tb)
    sys.excepthook = hook
    app = QApplication(sys.argv)
    win = FancyTerminal(); win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
