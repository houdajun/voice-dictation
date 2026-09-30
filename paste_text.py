#!/usr/bin/python3
"""把 stdin 的文字放进剪贴板并模拟粘贴（比 xdotool 逐字输入快得多），粘贴后恢复原来的剪贴板文字。"""
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Gdk

TERMINALS = {
    "gnome-terminal", "gnome-terminal-server", "xterm", "konsole", "tilix", "terminator",
    "alacritty", "kitty", "xfce4-terminal", "mate-terminal", "lxterminal", "urxvt", "st",
    "wezterm", "foot", "cinnamon-terminal",
}
# 恢复原内容后，最多保留多久（没有剪贴板管理器时，剪贴板内容靠本进程存活）
RESTORE_KEEPALIVE_MS = 10 * 60 * 1000


def focused_class():
    try:
        wid = subprocess.check_output(["xdotool", "getwindowfocus"], text=True).strip()
        out = subprocess.check_output(["xprop", "-id", wid, "WM_CLASS"], text=True)
        return out.split("=", 1)[1].lower()
    except Exception:
        return ""


def refocus(target):
    """如果焦点已经不在开始录音时的窗口（比如点了任务栏按钮），切回去再粘贴。"""
    if not target:
        return
    try:
        cur = subprocess.check_output(["xdotool", "getwindowfocus"], text=True, timeout=2).strip()
        if cur != target:
            subprocess.run(["xdotool", "windowfocus", "--sync", target], check=False, timeout=2)
    except Exception:
        pass


def main():
    refocus(sys.argv[1] if len(sys.argv) > 1 else "")
    text = sys.stdin.read()
    if not text:
        return
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    old = cb.wait_for_text()  # 只能保存文字；图片等其他内容无法恢复
    cb.set_text(text, -1)

    keys = "ctrl+shift+v" if any(t in focused_class() for t in TERMINALS) else "ctrl+v"

    done = []

    def quit_once(*_):
        if not done:
            done.append(1)
            Gtk.main_quit()
        return False

    def watch():
        # 恢复后过一会儿再开始监听，避免把自己 set_text 引起的事件当成别人复制
        cb.connect("owner-change", lambda c, e: quit_once() if c.get_owner() is None else None)
        return False

    def restore():
        if old:
            cb.set_text(old, -1)
            GLib.timeout_add(500, watch)
            GLib.timeout_add(RESTORE_KEEPALIVE_MS, quit_once)
        else:
            quit_once()
        return False

    def paste():
        subprocess.run(["xdotool", "key", "--clearmodifiers", keys], check=False)
        GLib.timeout_add(700, restore)  # 留时间让目标程序读取剪贴板
        return False

    GLib.timeout_add(80, paste)
    Gtk.main()


if __name__ == "__main__":
    main()
