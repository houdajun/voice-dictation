#!/usr/bin/python3
"""监听全局快捷键（默认 Pause 键），触发时向听写守护进程发送 toggle。（X11）"""
import os
import socket
import subprocess

from Xlib import X, XK, display

SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "dictate.sock")
# 要监听的按键（X11 keysym 名）和修饰键；单键就把 MODIFIERS 设为 0
HOTKEY = "Pause"
MODIFIERS = 0  # 例如 X.ControlMask | X.Mod1Mask 表示 Ctrl+Alt
# NumLock(Mod2) / CapsLock(Lock) 也要一并抓取，否则它们开着时快捷键失效
EXTRA_MASKS = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]


def send_toggle():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(SOCK_PATH)
            s.sendall(b"toggle")
    except OSError:
        subprocess.Popen(["notify-send", "语音听写", "守护进程没有运行，请先运行 start_dictate.sh"])


def main():
    d = display.Display()
    root = d.screen().root
    keycode = d.keysym_to_keycode(XK.string_to_keysym(HOTKEY))
    base = MODIFIERS
    for extra in EXTRA_MASKS:
        root.grab_key(keycode, base | extra, True, X.GrabModeAsync, X.GrabModeAsync)
    d.sync()
    print("监听", HOTKEY, flush=True)
    while True:
        ev = d.next_event()
        if ev.type == X.KeyPress and ev.detail == keycode:
            send_toggle()


if __name__ == "__main__":
    main()
