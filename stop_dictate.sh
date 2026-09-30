#!/bin/bash
# 停止听写守护进程、快捷键监听和悬浮按钮，释放约 4GB 显存。
. "$(dirname "$(readlink -f "$0")")/common.sh"

pkill -f "$DAEMON_RE"
pkill -f "$HOTKEY_RE"
pkill -f "$FLOAT_RE"
pkill -x arecord
# 等守护进程真正退出（释放显存需要一点时间）
for i in $(seq 1 20); do
    pgrep -f "$DAEMON_RE" >/dev/null || break
    sleep 1
done
echo "听写已停止"
