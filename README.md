# 本地中文语音听写 · Local Chinese Dictation for Linux

在任何软件里说中文，自动变成文字输入到光标处。完全在本地运行（[faster-whisper](https://github.com/SYSTRAN/faster-whisper) + GPU），音频不上传。

起因：写作时 Claude Code 自带的语音听写不支持普通话，于是自己做了一个。它不依赖 Claude Code，可以在任意 X11 桌面软件里使用。

## 功能

- **快捷键听写**：按一下 `Pause` 开始录音，再按一下结束，文字自动粘贴到光标处。
- **悬浮按钮**：鼠标指针变成输入框的“I”形时，指针旁边出现一个小按钮，点一下录音/结束；可拖动，会记住位置。
- **中文标点**：紧挨汉字的英文标点自动换成全角（`,` → `，`），英文句子、小数、网址不受影响。
- **不破坏剪贴板**：用剪贴板粘贴（比逐字输入快得多），粘贴后恢复你原来的剪贴板文字。
- **提示音 + 通知**：开始、转写中、完成各有提示音。
- **一条命令管理**：`dictate on | off | restart | status | rec | float on|off|reset`。

速度（RTX 5060 Ti，large-v3，`beam_size=1`）：转写耗时约为录音时长的 1/10～1/20，一段 20 秒的话按下结束后约 1.5 秒出字。常驻显存约 4 GB。

## 工作原理

```
Pause 键 / 悬浮按钮 / 任务栏图标
            │  向 unix socket 发送 "toggle"
            ▼
   dictate_daemon.py  ── arecord 录音 ──► faster-whisper (GPU) ──► 全角标点处理
            │                                                        │
            │                                                        ▼
            │                                      paste_text.py：写入剪贴板 → 模拟 Ctrl+V
            │                                      （终端用 Ctrl+Shift+V，粘贴后恢复剪贴板）
            ▼
   float_button.py 每 80ms 通过 "status" 查询状态，并读取鼠标指针形状
```

模型常驻显存并在启动时预热，所以每次按键只花转写本身的时间。

## 环境要求

- Linux + **X11** 会话（依赖 `XGrabKey`、`XFixes`、`xdotool`，**不支持 Wayland**）
- NVIDIA GPU + CUDA（也可以改用 CPU，见下文“配置”）
- 已在 Linux Mint 22（Cinnamon, X11）、RTX 5060 Ti 上测试

系统软件包（Debian/Ubuntu/Mint）：

```bash
sudo apt install xdotool x11-utils alsa-utils socat libnotify-bin pulseaudio-utils \
                 python3-xlib python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

另需一个装了 faster-whisper 的 Python 环境：

```bash
python3 -m venv ~/.venvs/dictate && ~/.venvs/dictate/bin/pip install faster-whisper
```

## 安装

```bash
git clone <本仓库地址> && cd <仓库目录>
cp config.example.sh config.sh     # 然后编辑 config.sh
./start_dictate.sh                 # 首次运行会下载 large-v3 模型（约 3 GB），之后约 20 秒就绪
```

`config.sh` 里设置：

| 变量 | 含义 | 默认 |
|---|---|---|
| `DICTATE_PYTHON` | 装了 faster-whisper 的 Python | `python3` |
| `DICTATE_MODEL` | 模型名（`large-v3`、`medium`…）或本地目录 | `large-v3` |
| `DICTATE_SYSTEM_PYTHON` | 悬浮按钮/快捷键监听用的系统 Python | `/usr/bin/python3` |

可选：让 `dictate` 命令在任何目录可用，并开机自启：

```bash
ln -s "$PWD/dictate" ~/.local/bin/dictate

mkdir -p ~/.config/autostart && cat > ~/.config/autostart/dictate.desktop <<EOF
[Desktop Entry]
Type=Application
Name=语音听写
Exec=$PWD/start_dictate.sh
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF
```

还可以把 `Exec=dictate rec`（开始/结束录音）或 `Exec=dictate toggle`（开关整套听写）做成 `.desktop` 启动器，固定到任务栏或桌面。

## 使用

1. 点一下你要输入文字的地方。
2. 按 `Pause`（或点悬浮按钮）开始录音，听到提示音。
3. 说话，再按一次结束；一两秒后文字出现。

紧凑键盘没有 `Pause` 键时，通常是 `Fn+PgUp`。

悬浮按钮颜色：深色话筒 = 待机，红色方块 = 录音中，黄色跳动的点 = 转写中。按住拖动可移动；点一下才是录音。

## 配置

| 想改什么 | 在哪改 |
|---|---|
| 快捷键 | `hotkey_listener.py` 里的 `HOTKEY`（X11 keysym 名）和 `MODIFIERS` |
| 悬浮按钮的出现延迟、大小、消失延迟 | `float_button.py` 顶部常量 |
| 悬浮按钮位置 | 直接拖动；`dictate float reset` 恢复默认 |
| 关闭悬浮按钮 | `dictate float off`（`on` 重新开启） |
| 识别语言/速度 | `dictate_daemon.py`：`LANGUAGE`、`beam_size`（越大越准越慢） |
| 用 CPU 运行 | `dictate_daemon.py`：`device="cpu", compute_type="int8"`（较慢） |
| 更快的模型 | `DICTATE_MODEL` 换成 `medium` / `small` / `large-v3-turbo` |

> **关于精度**：默认用 `float16`。在 RTX 5060 Ti（Blackwell）+ ctranslate2 4.7 上，`int8` 和 `int8_float16` 会报 `CUBLAS_STATUS_NOT_SUPPORTED`，`float16` 与 `float32` 正常。其他显卡可以自行试 `int8_float16` 以省显存。

## 文件

| 文件 | 作用 |
|---|---|
| `dictate_daemon.py` | 守护进程：录音、转写、标点处理、粘贴；通过 unix socket 接收 `toggle` / `status` |
| `hotkey_listener.py` | 全局快捷键监听（XGrabKey） |
| `float_button.py` | 悬浮按钮；通过 XFixes 读取指针形状判断是否在输入框上 |
| `paste_text.py` | 剪贴板粘贴助手，粘贴后恢复原剪贴板文字 |
| `dictate` | 命令行入口（`on/off/restart/toggle/status/rec/float`） |
| `start_dictate.sh` `stop_dictate.sh` `restart_dictate.sh` | 启停脚本 |
| `dictate_toggle.sh` | 向守护进程发送 `toggle` |
| `common.sh` `config.example.sh` | 配置加载与示例 |
| `warmup.wav` | 1 秒静音，启动时预热模型用 |

## 已知限制

- 只支持 X11，不支持 Wayland。
- “I”形指针是按**形状特征**识别的（不同软件的指针大小和样式不同，已在系统主题和微信的指针上验证）。个别软件的输入框用了特殊指针时可能不出现按钮，此时 `/tmp/dictate_float.log` 里会记录每种新指针形状的指标，便于调整 `float_button.py` 里的 `_looks_like_ibeam`。
- 在网页上阅读文字时指针也是“I”形，按钮也会出现；嫌烦可以 `dictate float off`。
- 只能恢复文字类剪贴板；剪贴板里原本是图片或文件时会被覆盖。
- 模型常驻显存，需要腾显存时运行 `dictate off`。

## 排查

日志：`/tmp/dictate.log`（守护进程，含每次的录音/转写/粘贴耗时）、`/tmp/dictate_hotkey.log`、`/tmp/dictate_float.log`。

- **按键没反应**：`dictate status` 看是否在运行；`pgrep -af hotkey_listener` 看监听是否在。
- **转写失败并出现 `cuBLAS ... NOT_SUPPORTED`**：换 `float16`（见上文精度说明）。
- **启动后第一句很慢**：正常，模型在启动时预热约 20 秒，出现“听写已就绪”通知后再用。

## 隐私

录音和转写全部在本机完成，除首次下载模型外不联网。录音文件是临时文件，转写后立即删除。

## 许可证

[MIT](LICENSE)
