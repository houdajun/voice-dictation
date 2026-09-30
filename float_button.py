#!/usr/bin/python3
"""悬浮录音按钮：鼠标指针变成输入框的“I”形时，在指针旁边出现一个小按钮，点一下开始/结束听写。

用法:
  float_button.py            正常运行
  float_button.py --shapes   每出现一种新的指针形状就画出来并给出识别结果
  float_button.py --log      只打印“I”形检测的变化（用来调试识别）
  float_button.py --demo [idle|recording|busy]   在固定位置显示几秒（用来截图检查外观）
"""
import ctypes
import ctypes.util
import math
import os
import socket
import sys
import time

import json
import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "dictate.sock")
SIZE = 40                 # 按钮大小（像素）
DEFAULT_POINTER_SIZE = (16, 35)   # 指针不是“I”形时（比如录音中）用的大小
SHOW_DELAY = 0.4          # 指针保持“I”形多久后才出现按钮
HIDE_DELAY = 0.7          # 指针离开输入框多久后按钮消失
NEAR_DIST = 80            # 指针离按钮多近算“正在去点它”，不让它消失
REANCHOR_DIST = 260       # 指针离开原位置多远，按钮就挪到新位置
TICK_MS = 80
DRAG_THRESHOLD = 5        # 移动超过多少像素算“拖动”，否则算“点击”
OFFSET_FILE = os.path.expanduser("~/.config/dictate/float_offset.json")


def load_offset():
    """用户拖动后保存的位置；没拖动过返回 None，此时按指针大小自动计算。"""
    try:
        with open(OFFSET_FILE) as f:
            dx, dy = json.load(f)
        return (max(-300, min(300, int(dx))), max(-300, min(300, int(dy))))
    except Exception:
        return None


def default_offset(size):
    """默认位置：紧挨着指针右下方；指针越小（如微信的小号 I 形），按钮越近。"""
    bw, bh = size
    return (int(bw / 2) + 2, int(bh * 0.35))


def save_offset(off):
    try:
        os.makedirs(os.path.dirname(OFFSET_FILE), exist_ok=True)
        with open(OFFSET_FILE, "w") as f:
            json.dump(list(off), f)
    except OSError:
        pass


# ---------- 读取鼠标指针形状（XFixes） ----------
class CursorImage(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_short), ("y", ctypes.c_short),
        ("width", ctypes.c_ushort), ("height", ctypes.c_ushort),
        ("xhot", ctypes.c_ushort), ("yhot", ctypes.c_ushort),
        ("cursor_serial", ctypes.c_ulong), ("pixels", ctypes.POINTER(ctypes.c_ulong)),
        ("atom", ctypes.c_ulong), ("name", ctypes.c_char_p),
    ]


_x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
_xf = ctypes.CDLL(ctypes.util.find_library("Xfixes"))
_x11.XOpenDisplay.restype = ctypes.c_void_p
_xf.XFixesGetCursorImage.restype = ctypes.POINTER(CursorImage)
_xf.XFixesGetCursorImage.argtypes = [ctypes.c_void_p]
_dpy = _x11.XOpenDisplay(None)

_ibeam_cache = {}  # cursor_serial -> (是否I形, (可见宽, 可见高))


def _ibeam_metrics(c):
    """返回 (bw, bh, cx, cy, top, mid, bottom)；没有可见像素时返回 None。"""
    w, h = c.width, c.height
    if not w or not h:
        return None
    minx, maxx, miny, maxy = w, -1, h, -1
    rows = [0] * h
    for y in range(h):
        n = 0
        for x in range(w):
            if (c.pixels[y * w + x] >> 24) & 0xFF > 128:
                n += 1
                minx, maxx = min(minx, x), max(maxx, x)
        rows[y] = n
        if n:
            miny, maxy = min(miny, y), y
    if maxx < 0:
        return None
    bw, bh = maxx - minx + 1, maxy - miny + 1
    # 横杠不一定在最顶/最底那一行（可能有一行窄的小尖），所以看顶部/底部附近几行里最宽的一行
    top = max(rows[miny:miny + 5]) / bw
    bottom = max(rows[max(miny, maxy - 4):maxy + 1]) / bw
    return bw, bh, (minx + maxx) / 2, (miny + maxy) / 2, top, rows[(miny + maxy) // 2] / bw, bottom


def _looks_like_ibeam(c):
    """按形状判断：细长、居中，顶部有横杠、中间是细竖线。不依赖主题和大小。"""
    m = _ibeam_metrics(c)
    if m is None:
        return False
    bw, bh, cx, cy, top, mid, bottom = m
    if abs(cx - c.xhot) > max(4, bw * 0.3) or abs(cy - c.yhot) > max(4, bh * 0.3):
        return False  # 热点不在中部：是箭头、小手等
    if bh < 1.3 * bw:
        return False  # 不够细长
    return top >= 0.6 and bottom >= 0.6 and mid <= 0.65


def read_pointer():
    """返回 (x, y, 是否“I”形, 指针可见大小)。"""
    p = _xf.XFixesGetCursorImage(_dpy)
    try:
        c = p.contents
        serial = c.cursor_serial
        if serial not in _ibeam_cache:
            if len(_ibeam_cache) > 200:
                _ibeam_cache.clear()
            m = _ibeam_metrics(c)
            _ibeam_cache[serial] = (_looks_like_ibeam(c), (m[0], m[1]) if m else DEFAULT_POINTER_SIZE)
            print(f"{time.strftime('%H:%M:%S')} 新指针形状 {c.width}x{c.height} 热点({c.xhot},{c.yhot}) "
                  f"I形={_ibeam_cache[serial][0]} 指标={_ibeam_metrics(c)} 位置({c.x},{c.y})", flush=True)
        ibeam, size = _ibeam_cache[serial]
        return c.x, c.y, ibeam, size
    finally:
        _x11.XFree(p)


# ---------- 和听写守护进程通信 ----------
def _ask(cmd):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(SOCK_PATH)
            s.sendall(cmd)
            if cmd == b"status":
                return s.recv(32).decode().strip()
            return "ok"
    except OSError:
        return None  # 守护进程没开


# ---------- 按钮窗口 ----------
class Button(Gtk.Window):
    def __init__(self, on_click, on_moved=lambda: None):
        super().__init__(type=Gtk.WindowType.POPUP)  # 不受窗口管理器管理，不会抢焦点
        self.on_click = on_click
        self.on_moved = on_moved
        self.dragging = False
        self._press_info = None
        self.state = "idle"
        self.set_default_size(SIZE, SIZE)
        self.set_decorated(False)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("motion-notify-event", self._motion)
        self.connect("button-release-event", self._release)
        self.connect("realize", self._on_realize)

    def _press(self, _w, e):
        if e.button == 1:
            x, y = self.get_position()
            self._press_info = (e.x_root, e.y_root, x, y)
        return True

    def _motion(self, _w, e):
        if not self._press_info:
            return True
        sx, sy, x0, y0 = self._press_info
        dx, dy = e.x_root - sx, e.y_root - sy
        if not self.dragging and math.hypot(dx, dy) > DRAG_THRESHOLD:
            self.dragging = True
        if self.dragging:
            self.place(int(x0 + dx), int(y0 + dy))
        return True

    def _release(self, _w, e):
        if e.button != 1 or not self._press_info:
            return True
        was_drag = self.dragging
        self._press_info = None
        self.dragging = False
        if was_drag:
            self.on_moved()
        else:
            self.on_click()
        return True

    def _on_realize(self, *_):
        self.get_window().set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "pointer"))

    def _draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cx = cy = SIZE / 2
        t = time.monotonic()
        r = SIZE / 2 - 3
        if self.state == "recording":
            r += 1.5 * math.sin(t * 6)          # 呼吸感
            color = (0.90, 0.16, 0.16)
        elif self.state == "busy":
            color = (0.95, 0.65, 0.10)
        else:
            color = (0.16, 0.17, 0.20)
        # 阴影
        cr.arc(cx, cy + 1.2, r + 0.5, 0, 2 * math.pi)
        cr.set_source_rgba(0, 0, 0, 0.30)
        cr.fill()
        # 圆
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*color, 0.96)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.set_line_width(1.2)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 1)
        if self.state == "recording":            # 停止方块
            cr.rectangle(cx - 6, cy - 6, 12, 12)
            cr.fill()
        elif self.state == "busy":               # 三个跳动的点
            for i in range(3):
                dy = 3 * math.sin(t * 8 - i * 0.9)
                cr.arc(cx - 8 + i * 8, cy + dy, 2.4, 0, 2 * math.pi)
                cr.fill()
        else:                                    # 话筒
            cr.set_line_width(2)
            bw, bh = 7, 13
            _round_rect(cr, cx - bw / 2, cy - bh / 2 - 2, bw, bh, 3.5)
            cr.fill()
            cr.arc(cx, cy - 1, 7.5, 0.15 * math.pi, 0.85 * math.pi)
            cr.stroke()
            cr.move_to(cx, cy + 6.5)
            cr.line_to(cx, cy + 10)
            cr.stroke()
            cr.move_to(cx - 4, cy + 10)
            cr.line_to(cx + 4, cy + 10)
            cr.stroke()

    def place(self, x, y):
        geo = self.get_display().get_monitor_at_point(x, y).get_geometry()
        x = max(geo.x, min(x, geo.x + geo.width - SIZE))
        y = max(geo.y, min(y, geo.y + geo.height - SIZE))
        self.move(x, y)

    def center(self):
        x, y = self.get_position()
        return x + SIZE / 2, y + SIZE / 2


def _round_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


# ---------- 主逻辑 ----------
class Controller:
    def __init__(self):
        self.custom_offset = load_offset()   # 用户拖动保存的位置
        self.pointer_size = DEFAULT_POINTER_SIZE
        self.btn = Button(self.click, self.moved)
        self.visible = False
        self.anchor = (0, 0)
        self.ibeam_since = None
        self.lost_since = None
        self.status = "idle"
        self.status_at = 0.0

    def click(self):
        _ask(b"toggle")
        self.status_at = 0  # 马上刷新状态

    def moved(self):
        """用户拖动了按钮：记住它相对鼠标指针（出现时的位置）的偏移，下次按这个位置出现。"""
        bx, by = self.btn.get_position()
        self.custom_offset = (max(-300, min(300, bx - self.anchor[0])), max(-300, min(300, by - self.anchor[1])))
        save_offset(self.custom_offset)

    def show_at(self, px, py):
        self.anchor = (px, py)
        off = self.custom_offset or default_offset(self.pointer_size)
        self.btn.place(px + off[0], py + off[1])
        if not self.visible:
            self.btn.show_all()
            self.visible = True
        self.btn.get_window().raise_()

    def hide(self):
        if self.visible:
            self.btn.hide()
            self.visible = False
        self.ibeam_since = self.lost_since = None

    def tick(self):
        now = time.monotonic()
        if now - self.status_at > 0.3:
            self.status = _ask(b"status")
            self.status_at = now
        px, py, ibeam, size = read_pointer()
        if ibeam:
            self.pointer_size = size

        if self.btn.dragging or self.btn._press_info:   # 正在拖动/按住：保持原样
            self.btn.queue_draw()
            return True

        if self.status is None:          # 听写没开：不显示
            self.hide()
            return True

        self.btn.state = self.status if self.status in ("recording", "busy") else "idle"

        if self.status in ("recording", "busy"):
            if not self.visible:
                self.show_at(px, py)
            self.lost_since = None
        else:
            if ibeam:
                self.lost_since = None
                self.ibeam_since = self.ibeam_since or now
                if not self.visible and now - self.ibeam_since >= SHOW_DELAY:
                    self.show_at(px, py)
                elif self.visible and math.hypot(px - self.anchor[0], py - self.anchor[1]) > REANCHOR_DIST:
                    self.show_at(px, py)
            else:
                self.ibeam_since = None
                if self.visible:
                    bx, by = self.btn.center()
                    if math.hypot(px - bx, py - by) < NEAR_DIST:
                        self.lost_since = None
                    else:
                        self.lost_since = self.lost_since or now
                        if now - self.lost_since >= HIDE_DELAY:
                            self.hide()

        if self.visible:
            self.btn.queue_draw()       # 动画
        return True


def main():
    if "--shapes" in sys.argv:
        seen = set()
        while True:
            pt = _xf.XFixesGetCursorImage(_dpy)
            c = pt.contents
            w, h = c.width, c.height
            key = (c.cursor_serial)
            if key not in seen:
                seen.add(key)
                px = [c.pixels[i] & 0xFFFFFFFF for i in range(w * h)]
                rows = ["".join("#" if (px[r * w + cc] >> 24) > 128 else ("." if (px[r * w + cc] >> 24) > 20 else " ")
                                for cc in range(w)) for r in range(0, h, 2)]
                rows = [r for r in rows if r.strip()]
                print(f"\n== {time.strftime('%H:%M:%S')} {w}x{h} 热点({c.xhot},{c.yhot}) 识别为I形={_looks_like_ibeam(c)} 指针({c.x},{c.y}) 指标(宽,高,cx,cy,顶,中)={_ibeam_metrics(c)}", flush=True)
                print("\n".join(rows), flush=True)
            _x11.XFree(pt)
            time.sleep(0.1)
    if "--log" in sys.argv:
        last = None
        while True:
            x, y, ib, _ = read_pointer()
            if ib != last:
                print(time.strftime("%H:%M:%S"), "I形" if ib else "非I形", f"({x},{y})", flush=True)
                last = ib
            time.sleep(0.08)
    if "--demo" in sys.argv:
        i = sys.argv.index("--demo")
        state = sys.argv[i + 1] if len(sys.argv) > i + 2 or (len(sys.argv) > i + 1) else "idle"
        b = Button(lambda: None)
        b.state = state
        b.show_all()
        b.move(2000, 600)
        GLib.timeout_add(80, lambda: (b.queue_draw(), True)[1])
        GLib.timeout_add(6000, Gtk.main_quit)
        Gtk.main()
        return
    c = Controller()
    GLib.timeout_add(TICK_MS, c.tick)
    Gtk.main()


if __name__ == "__main__":
    main()
