# 被 start/stop/restart/dictate 共用：读取配置、定义进程匹配规则。
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
[ -f "$DIR/config.sh" ] && . "$DIR/config.sh"

# 运行守护进程（需要装了 faster-whisper 的 Python）和模型
DICTATE_PYTHON="${DICTATE_PYTHON:-python3}"
export DICTATE_MODEL="${DICTATE_MODEL:-large-v3}"
# 悬浮按钮/快捷键监听用系统 Python（需要 python3-xlib、python3-gi、python3-gi-cairo）
export DICTATE_SYSTEM_PYTHON="${DICTATE_SYSTEM_PYTHON:-/usr/bin/python3}"

# 用“以 python 开头的命令行”精确匹配，避免误伤自己
DAEMON_RE='^[^ ]*python[^ ]* .*/dictate_daemon\.py'
HOTKEY_RE='^[^ ]*python[^ ]* .*/hotkey_listener\.py'
FLOAT_RE='^[^ ]*python[^ ]* .*/float_button\.py'
