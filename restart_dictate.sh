#!/bin/bash
# 重启听写（先停止再启动）。
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
"$DIR/stop_dictate.sh"
"$DIR/start_dictate.sh"
