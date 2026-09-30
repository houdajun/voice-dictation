#!/usr/bin/env python3
"""本地中文语音听写守护进程。

收到 "toggle"：第一次开始录音，第二次结束录音，用 faster-whisper 转写，
再用 xdotool 把文字输入到当前光标位置。
"""
import os
import re
import socket
import subprocess
import tempfile
import threading
import time

from faster_whisper import WhisperModel

# 模型名（如 large-v3，首次运行自动下载）或本地目录，由 config.sh / 环境变量 DICTATE_MODEL 指定
MODEL_PATH = os.environ.get("DICTATE_MODEL", "large-v3")
LANGUAGE = "zh"
# 提示词让模型倾向输出简体中文和标点
INITIAL_PROMPT = "以下是普通话的句子，使用简体中文和标点符号。"
SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "dictate.sock")


SOUND_DIR = "/usr/share/sounds/freedesktop/stereo/"


def beep(name):
    subprocess.Popen(["paplay", SOUND_DIR + name + ".oga"], stderr=subprocess.DEVNULL)


PASTE_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paste_text.py")


def paste(text, target=""):
    """剪贴板粘贴（快）；失败时退回 xdotool 逐字输入。"""
    try:
        p = subprocess.Popen([os.environ.get("DICTATE_SYSTEM_PYTHON", "/usr/bin/python3"), PASTE_HELPER, target], stdin=subprocess.PIPE, text=True)
        p.stdin.write(text)
        p.stdin.close()
    except OSError:
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "2", "--", text], check=False)


def focused_window():
    try:
        return subprocess.check_output(["xdotool", "getwindowfocus"], text=True, timeout=2).strip()
    except Exception:
        return ""


CJK = "\u3400-\u9fff\uf900-\ufaff"
FULLWIDTH = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}


def cjk_punctuation(text):
    """紧挨着汉字的英文标点换成全角中文标点（英文单词间、小数点、网址等不动）。"""
    # 前面是汉字（中间可有空格），或后面是汉字
    text = re.sub(rf"([{CJK}])[ \t]*([,.?!:;])", lambda m: m.group(1) + FULLWIDTH[m.group(2)], text)
    text = re.sub(rf"([,.?!:;])(?=[ \t]*[{CJK}])", lambda m: FULLWIDTH[m.group(1)], text)
    # 全角标点和后面的汉字之间不留空格
    return re.sub(rf"([，。？！：；])[ \t]+(?=[{CJK}])", r"\1", text)


def notify(msg):
    subprocess.Popen(["notify-send", "-t", "1500", "-h", "string:x-canonical-private-synchronous:dictate", "语音听写", msg])


class Dictation:
    def __init__(self):
        print("加载模型…", flush=True)
        self.model = WhisperModel(MODEL_PATH, device="cuda", compute_type="float16")
        t = time.time()
        list(self.model.transcribe(os.path.join(os.path.dirname(os.path.abspath(__file__)), "warmup.wav"), language=LANGUAGE)[0])
        print(f"模型就绪（预热 {time.time() - t:.1f}s）", flush=True)
        self.rec = None
        self.wav = None
        self.target = ""
        self.busy = False
        self.lock = threading.Lock()

    def state(self):
        return "recording" if self.rec is not None else ("busy" if self.busy else "idle")

    def toggle(self):
        with self.lock:
            if self.busy:
                notify("正在转写，请稍等")
                return
            if self.rec is None:
                self._start()
            else:
                self._stop()

    def _start(self):
        fd, self.wav = tempfile.mkstemp(suffix=".wav", prefix="dictate_")
        os.close(fd)
        self.target = focused_window()
        self.rec = subprocess.Popen(
            ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", self.wav],
            stderr=subprocess.DEVNULL,
        )
        beep("message-new-instant")
        notify("🎙 录音中… 再按一次结束")

    def _stop(self):
        self.rec.terminate()
        self.rec.wait()
        self.rec = None
        wav, self.wav = self.wav, None
        target = self.target
        self.busy = True
        beep("bell")
        notify("⏳ 转写中…")
        threading.Thread(target=self._transcribe, args=(wav, target), daemon=True).start()

    def _transcribe(self, wav, target=""):
        t0 = time.time()
        try:
            segments, info = self.model.transcribe(
                wav,
                language=LANGUAGE,
                initial_prompt=INITIAL_PROMPT,
                vad_filter=True,
                beam_size=1,
            )
            text = cjk_punctuation("".join(s.text for s in segments).strip())
            t1 = time.time()
            if not text:
                notify("没有识别到语音")
                return
            print("识别:", text, flush=True)
            beep("complete")
            paste(text, target)
            print(f"录音 {info.duration:.1f}s | 转写 {t1 - t0:.1f}s | 打字 {time.time() - t1:.1f}s | {len(text)} 字", flush=True)
        except Exception as e:
            print("转写失败:", e, flush=True)
            notify(f"转写失败: {e}")
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass
            self.busy = False


def main():
    d = Dictation()
    if os.path.exists(SOCK_PATH):
        os.remove(SOCK_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    srv.listen(4)
    print("监听", SOCK_PATH, flush=True)
    notify("听写已就绪")
    while True:
        conn, _ = srv.accept()
        with conn:
            cmd = conn.recv(64).strip()
            if cmd == b"toggle":
                d.toggle()
            elif cmd == b"status":
                conn.sendall(d.state().encode())


if __name__ == "__main__":
    main()
