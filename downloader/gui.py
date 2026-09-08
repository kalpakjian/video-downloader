"""Traditional Chinese Tk interface; worker threads communicate only by queue."""

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .engine import DownloadEngine
from .models import DownloadCancelled, DownloadError, DownloadRequest, PROFILES, validate_url
from .settings import load_settings, save_settings
from .tools import ToolManager


class DownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.operation = None
        self.closing = False
        self.finished = False
        self.last_path = None
        self.poll_id = None
        settings = load_settings()
        self.url = tk.StringVar()
        self.folder = tk.StringVar(value=settings["output_dir"])
        self.profile = tk.StringVar(value=next(p.label for p in PROFILES if p.id == settings["profile"]))
        self.description = tk.StringVar()
        self.status = tk.StringVar(value="準備就緒，請貼上單支影片網址。")
        self.metrics = tk.StringVar()
        self.tools_status = tk.StringVar()
        root.title("下載影片 — 簡單保存，清楚掌握")
        root.geometry("840x730")
        root.minsize(720, 650)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        root.configure(background="#f5f6fb")
        style.configure(".", background="#f5f6fb", foreground="#25324b", font=("Microsoft JhengHei UI", 10))
        style.configure("TEntry", fieldbackground="#ffffff", padding=4)
        style.configure("TCombobox", fieldbackground="#ffffff", padding=4)
        style.configure("TButton", padding=(10, 6))
        style.configure("Primary.TButton", background="#514ce3", foreground="white", padding=(24, 9))
        style.map("Primary.TButton", background=[("disabled", "#c1c0db"), ("active", "#403bca")],
                  foreground=[("disabled", "#f2f2f7")])
        style.configure("Horizontal.TProgressbar", background="#514ce3", troughcolor="#e4e7f2")
        style.configure("Title.TLabel", font=("Microsoft JhengHei UI", 23, "bold"))
        style.configure("Heading.TLabel", font=("Microsoft JhengHei UI", 11, "bold"))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(13, weight=1)
        ttk.Label(frame, text="下載影片", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="貼上網址・選擇格式・存到電腦　｜　無廣告，不需註冊本工具帳號\nYouTube · Instagram · Facebook · X · TikTok（依核心與平台限制）").grid(row=1, column=0, sticky="w", pady=(2, 16))
        ttk.Label(frame, text="1　影片網址", style="Heading.TLabel").grid(row=2, column=0, sticky="w")
        url_row = ttk.Frame(frame)
        url_row.grid(row=3, column=0, sticky="ew", pady=(6, 14))
        url_row.columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_row, textvariable=self.url)
        self.url_entry.grid(row=0, column=0, sticky="ew", ipady=5)
        self.paste_button = ttk.Button(url_row, text="貼上", command=self.paste)
        self.paste_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(frame, text="2　格式與畫質", style="Heading.TLabel").grid(row=4, column=0, sticky="w")
        self.profile_box = ttk.Combobox(frame, textvariable=self.profile, values=[p.label for p in PROFILES], state="readonly")
        self.profile_box.grid(row=5, column=0, sticky="ew", pady=(6, 4), ipady=4)
        self.profile_box.bind("<<ComboboxSelected>>", self.describe_profile)
        ttk.Label(frame, textvariable=self.description, wraplength=740).grid(row=6, column=0, sticky="w", pady=(0, 14))
        ttk.Label(frame, text="3　儲存位置", style="Heading.TLabel").grid(row=7, column=0, sticky="w")
        folder_row = ttk.Frame(frame)
        folder_row.grid(row=8, column=0, sticky="ew", pady=(6, 14))
        folder_row.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder)
        self.folder_entry.grid(row=0, column=0, sticky="ew", ipady=5)
        self.browse_button = ttk.Button(folder_row, text="選擇資料夾…", command=self.browse)
        self.browse_button.grid(row=0, column=1, padx=(8, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, sticky="ew", pady=(0, 12))
        self.start_button = ttk.Button(actions, text="開始下載", style="Primary.TButton", command=self.start_download)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        ttk.Button(actions, text="開啟資料夾", command=self.open_folder).pack(side="left")
        self.update_button = ttk.Button(actions, text="更新下載核心", command=self.start_update)
        self.update_button.pack(side="right")
        progress_frame = ttk.Frame(frame)
        progress_frame.grid(row=10, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.status, wraplength=740).pack(anchor="w")
        self.progress = ttk.Progressbar(progress_frame, maximum=100)
        self.progress.pack(fill="x", pady=(8, 4))
        ttk.Label(progress_frame, textvariable=self.metrics, wraplength=740).pack(anchor="w")
        ttk.Label(frame, textvariable=self.tools_status, wraplength=740).grid(row=11, column=0, sticky="w", pady=(8, 8))
        ttk.Label(frame, text="執行訊息（可能含網址／檔名，分享前請確認）").grid(row=12, column=0, sticky="w")
        self.log = ScrolledText(frame, height=6, wrap="word", state="disabled", background="white",
                                foreground="#25324b", relief="solid", borderwidth=1, font=("Microsoft JhengHei UI", 9))
        self.log.grid(row=13, column=0, sticky="nsew", pady=(4, 8))
        ttk.Label(frame, text="僅下載自己擁有或獲授權保存的內容。公開影片仍可能受登入、地區或平台限制；不解除 DRM。\n第一版僅支援單支影片，不下載播放清單或直播。最高畫質不代表提升來源畫質。", wraplength=740).grid(row=14, column=0, sticky="w")
        self.describe_profile()
        self.refresh_tools()
        self.url_entry.focus_set()
        root.bind("<Return>", lambda event: self.start_download())
        self.poll_id = root.after(100, self.poll)
        def resize_labels(event):
            if event.widget is frame:
                width = max(360, event.width - 52)
                for parent in (frame, progress_frame):
                    for widget in parent.winfo_children():
                        if isinstance(widget, ttk.Label) and int(widget.cget("wraplength")):
                            widget.configure(wraplength=width)
        frame.bind("<Configure>", resize_labels)

    def selected_profile(self):
        return next(p for p in PROFILES if p.label == self.profile.get())

    def describe_profile(self, event=None):
        self.description.set(self.selected_profile().description)

    def refresh_tools(self):
        tools = ToolManager().status()
        labels = (("yt_dlp", "下載核心"), ("ffmpeg", "FFmpeg"), ("ffprobe", "FFprobe"), ("node", "Node.js"))
        self.tools_status.set("工具偵測：" + "　｜　".join(f"{label} {'已找到' if tools[key] else '未找到'}" for key, label in labels))

    def paste(self):
        try:
            self.url.set(self.root.clipboard_get().strip())
        except tk.TclError:
            self.status.set("剪貼簿中沒有可貼上的文字。")

    def browse(self):
        chosen = filedialog.askdirectory(parent=self.root, title="選擇影片儲存資料夾", initialdir=self.folder.get(), mustexist=True)
        if chosen:
            self.folder.set(chosen)

    def open_folder(self):
        try:
            folder = self.last_path.parent if self.last_path else Path(self.folder.get()).expanduser()
            if not folder.is_absolute() or not folder.is_dir():
                raise OSError("資料夾尚不存在，請先選擇現有資料夾或完成一次下載。")
            os.startfile(str(folder.resolve()))
        except (OSError, ValueError, AttributeError) as exc:
            messagebox.showerror("無法開啟資料夾", str(exc), parent=self.root)

    def append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", str(message)[:4000] + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 500:
            self.log.delete("1.0", "101.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(self, busy):
        for widget in (self.url_entry, self.paste_button, self.folder_entry, self.browse_button, self.start_button, self.update_button):
            widget.configure(state="disabled" if busy else "normal")
        self.profile_box.configure(state="disabled" if busy else "readonly")
        self.cancel_button.configure(state="normal" if busy else "disabled")

    def start_download(self):
        if self.worker is not None or self.closing:
            return
        try:
            url = validate_url(self.url.get())
            folder = Path(self.folder.get().strip()).expanduser()
            if not folder.is_absolute() or "\x00" in str(folder):
                raise DownloadError("請選擇完整的儲存資料夾路徑。")
            profile = self.selected_profile().id
            request = DownloadRequest(url, folder, profile)
        except (DownloadError, ValueError) as exc:
            messagebox.showerror("請檢查輸入", str(exc), parent=self.root)
            return
        try:
            save_settings({"output_dir": str(folder), "profile": profile})
        except OSError as exc:
            self.append_log(f"偏好設定無法儲存，但仍可下載：{exc}")
        engine = DownloadEngine(self.events.put)
        self.operation = engine
        self.last_path = None
        self.begin(lambda: engine.run(request), "download")

    def start_update(self):
        if self.worker is not None or self.closing:
            return
        manager = ToolManager()
        self.operation = manager
        self.begin(lambda: manager.update_core(self.events.put), "update")

    def begin(self, action, kind):
        self.finished = False
        self.set_busy(True)
        self.status.set("正在準備下載…" if kind == "download" else "正在準備更新官方下載核心…")
        self.metrics.set("")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)

        def work():
            try:
                result = action()
                if kind == "update":
                    self.events.put({"type": "updated", "version": result})
            except DownloadCancelled as exc:
                self.events.put({"type": "cancelled", "message": str(exc)})
            except Exception as exc:
                self.events.put({"type": "error", "message": str(exc) or type(exc).__name__})
            finally:
                self.events.put({"type": "finished"})

        # Non-daemon: do not abandon child processes or atomic update cleanup.
        self.worker = threading.Thread(target=work, name="video-downloader-worker", daemon=False)
        self.worker.start()

    def cancel(self):
        if self.operation is None:
            return
        self.cancel_button.configure(state="disabled")
        self.status.set("正在取消，等待工具安全結束…（網路更新可能需等候逾時）")
        if isinstance(self.operation, DownloadEngine):
            self.operation.cancel()
        else:
            self.operation.cancel_update()

    def handle_event(self, event):
        kind = event.get("type")
        if kind == "log":
            self.append_log(event.get("message", ""))
        elif kind == "status":
            self.status.set(event.get("message", ""))
        elif kind == "progress":
            percent = event.get("percent")
            self.progress.stop()
            if percent is None:
                self.progress.configure(mode="indeterminate", value=0)
                self.progress.start(12)
                self.metrics.set("正在合併／處理媒體…" if event.get("phase") == "processing" else "正在取得資料…")
            else:
                self.progress.configure(mode="determinate", value=max(0, min(100, float(percent))))
                self.metrics.set("　｜　".join(part for part in (f"目前階段 {percent:.1f}%", event.get("speed", ""), f"預估剩餘 {event['eta']}" if event.get("eta") else "") if part))
        elif kind == "completed":
            self.last_path = Path(event["path"])
            self.status.set("下載完成，檔案已儲存。")
            self.metrics.set(self.last_path.name)
            self.progress.stop()
            self.progress.configure(mode="determinate", value=100)
            self.append_log(f"完成：{self.last_path}")
        elif kind == "updated":
            self.status.set(f"下載核心已更新至 {event['version']}。")
            self.metrics.set("已通過官方 SHA-256 與版本驗證。")
            self.progress.stop()
            self.progress.configure(mode="determinate", value=100)
        elif kind in {"cancelled", "error"}:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.metrics.set("")
            self.status.set("已取消。" if kind == "cancelled" else "工作未完成，請查看下方說明。")
            self.append_log(event["message"])
            if kind == "error" and not self.closing:
                messagebox.showerror("無法完成", event["message"], parent=self.root)
        elif kind == "finished":
            self.finished = True

    def poll(self):
        self.poll_id = None
        # Bound each batch so a noisy subprocess cannot starve Tk events.
        for _ in range(200):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self.handle_event(event)
        if self.finished and self.worker is not None and not self.worker.is_alive():
            self.worker.join(timeout=0)
            self.worker = None
            self.operation = None
            self.finished = False
            # Terminal event handlers already stopped animation. ttk.stop()
            # resets the value to zero, so do not erase a completed 100% bar.
            self.set_busy(False)
            self.refresh_tools()
        if self.closing and self.worker is None:
            self.destroy()
            return
        self.poll_id = self.root.after(100, self.poll)

    def close(self):
        if self.closing:
            return
        if self.worker is not None:
            if not messagebox.askyesno("取消並關閉？", "工作仍在執行。要取消工作，並在工具安全結束後關閉嗎？", parent=self.root):
                return
            self.closing = True
            self.cancel()
        else:
            self.destroy()

    def destroy(self):
        self.progress.stop()
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
            self.poll_id = None
        self.root.destroy()


def main():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


def smoke_test():
    """Construct all widgets and exercise progress without network or writes."""
    root = tk.Tk()
    root.withdraw()
    app = None
    try:
        app = DownloaderApp(root)
        root.update_idletasks()
        assert len(app.profile_box["values"]) == len(PROFILES)
        app.handle_event({"type": "progress", "percent": 42.5, "speed": "1 MiB/s", "eta": "00:03", "phase": "download"})
        assert app.progress["value"] == 42.5
        app.handle_event({"type": "progress", "percent": None, "phase": "processing"})
        app.handle_event({"type": "cancelled", "message": "Smoke test: cancellation event handled."})
        assert app.status.get() == "已取消。"
        root.update()
    finally:
        if app is not None:
            app.destroy()
        else:
            root.destroy()
    print("GUI smoke test passed")