#!/bin/bash
# 快捷键调用：向听写守护进程发送 toggle。
SOCK="${XDG_RUNTIME_DIR:-/tmp}/dictate.sock"
if [ ! -S "$SOCK" ]; then
    notify-send "语音听写" "守护进程没有运行，请先运行 start_dictate.sh"
    exit 1
fi
echo toggle | socat - UNIX-CONNECT:"$SOCK"
