#!/bin/bash
# 启动听写守护进程、快捷键监听和悬浮按钮（后台运行，日志在 /tmp/dictate*.log）。
. "$(dirname "$(readlink -f "$0")")/common.sh"

if ! pgrep -f "$DAEMON_RE" >/dev/null; then
    nohup "$DICTATE_PYTHON" "$DIR/dictate_daemon.py" >/tmp/dictate.log 2>&1 &
    echo "听写守护进程已启动，日志: /tmp/dictate.log"
else
    echo "听写守护进程已经在运行"
fi
if ! pgrep -f "$HOTKEY_RE" >/dev/null; then
    nohup "$DICTATE_SYSTEM_PYTHON" "$DIR/hotkey_listener.py" >/tmp/dictate_hotkey.log 2>&1 &
    echo "快捷键监听已启动，日志: /tmp/dictate_hotkey.log"
else
    echo "快捷键监听已经在运行"
fi
# 悬浮录音按钮（用 `dictate float off` 可关闭）
if [ ! -e "$HOME/.config/dictate/float_disabled" ] && ! pgrep -f "$FLOAT_RE" >/dev/null; then
    nohup "$DICTATE_SYSTEM_PYTHON" "$DIR/float_button.py" >/tmp/dictate_float.log 2>&1 &
    echo "悬浮按钮已启动，日志: /tmp/dictate_float.log"
fi
