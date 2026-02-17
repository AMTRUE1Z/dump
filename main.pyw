import sys
import os
import json
import subprocess
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ttkbootstrap as tb
import requests
import threading
import webbrowser
import pyautogui
from pywinauto import Application
import keyboard
import time
import re
from datetime import datetime

# Must be launched by bootstrapper
if "--allow-launch" not in sys.argv:
    raise SystemExit("This program must be launched through the bootstrapper.")

# Hide console window
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# ======================================================
# CONFIG
# ======================================================

GITHUB_RAW_SCANNER_URL = (
    "https://raw.githubusercontent.com/AMTRUE1Z/dump/refs/heads/main/scanner.py"
)

SCANNER_FILENAME = os.path.join("bin", "scanner.py")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_DIR = os.path.join(BASE_DIR, "dump")
CUSTOM_APPS_FILE = "custom_apps.txt"

DEFAULT_MODEL = "llama3"
INTENT_MODEL = "phi3:mini"

# ======================================================
# HELPERS
# ======================================================

def write_console(widget, text):
    widget.config(state="normal")
    widget.insert("end", text)
    widget.see("end")
    widget.config(state="disabled")

def ensure_dump_folder():
    if not os.path.isdir(DUMP_DIR):
        os.makedirs(DUMP_DIR)

def download_scanner():
    try:
        urllib.request.urlretrieve(GITHUB_RAW_SCANNER_URL, SCANNER_FILENAME)
    except Exception:
        pass

def run_scanner_silently(console=None):
    try:
        result = subprocess.run(
            [sys.executable, SCANNER_FILENAME, "--allow-scan"],
            capture_output=True,
            text=True
        )
        if console:
            write_console(console, "[SYSTEM] Scanner output:\n" + result.stdout + "\n")
            if result.stderr:
                write_console(console, "[SYSTEM] Scanner errors:\n" + result.stderr + "\n")
    except Exception as e:
        if console:
            write_console(console, f"[ERROR] Scanner error: {e}\n")

def load_json_file(path, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_custom_app(name, path, console):
    ensure_dump_folder()
    file_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

    if os.path.isfile(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                data = []
    else:
        data = []

    entry = {"name": name, "exe": path}
    data.append(entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    write_console(console, f"[BOT] Added custom app: {name} -> {path}\n")

def find_app_by_name(name, apps_list):
    import difflib

    name = name.lower().replace(" ", "")
    best_match = None
    best_score = 0

    for app in apps_list:
        app_name = app.get("name", "").lower()
        app_name_compact = app_name.replace(" ", "")

        if name == app_name_compact:
            return app

        if name in app_name_compact:
            return app

        score = difflib.SequenceMatcher(None, name, app_name_compact).ratio()
        if score > best_score:
            best_score = score
            best_match = app

    if best_score >= 0.55:
        return best_match

    return None

def launch_executable(path, args=None, console=None):
    try:
        if args:
            subprocess.Popen([path] + args)
        else:
            os.startfile(path)

        if console:
            write_console(console, f"[SYSTEM] Launching: {path}\n")
        return True
    except Exception as e:
        if console:
            write_console(console, f"[ERROR] Failed to launch {path}: {e}\n")
        return False

# ======================================================
# INTENT CLASSIFIER
# ======================================================

def classify_intent(text: str):
    prompt = f"""
You are an intent classifier for a desktop assistant.

Respond ONLY with JSON:
{{
  "actions": [
    {{"type": "..."}}
  ]
}}

User message: "{text}"
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": INTENT_MODEL, "prompt": prompt, "stream": False},
            timeout=30
        )
        data = response.json()
        raw = data.get("response", "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        obj = json.loads(raw)
        actions = obj.get("actions", [])
        if not isinstance(actions, list):
            actions = []
        return {"actions": actions}
    except Exception:
        return {"actions": [{"type": "none"}]}

# ======================================================
# URL DETECTION
# ======================================================

BROWSER_NAMES = {
    "brave": ["brave"],
    "edge": ["edge", "microsoft edge"],
    "firefox": ["firefox"],
    "opera": ["opera"],
    "vivaldi": ["vivaldi"],
}

def detect_url(text: str):
    pattern = re.compile(r"(https?://\S+|\b[\w\-]+\.(com|net|org|io|gg|dev|app|tv|ai)\b)")
    match = pattern.search(text)
    if match:
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return url
    return None

def open_url_with_browser(url, preferred_browser_name, console_widget):
    ensure_dump_folder()
    installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
    custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

    installed_apps = load_json_file(installed_path, [])
    custom_apps = load_json_file(custom_path, [])

    if not preferred_browser_name:
        try:
            webbrowser.open(url)
            write_console(console_widget, f"[SYSTEM] Opening {url} in default browser.\n")
        except Exception:
            write_console(console_widget, f"[ERROR] Failed to open {url}.\n")
        return

    candidates = BROWSER_NAMES.get(preferred_browser_name.lower(), [preferred_browser_name.lower()])

    def find_browser(cands, apps):
        for c in cands:
            app = find_app_by_name(c, apps)
            if app:
                return app
        return None

    app = find_browser(candidates, custom_apps) or find_browser(candidates, installed_apps)

    if not app:
        write_console(console_widget, f"[ERROR] Browser '{preferred_browser_name}' not found.\n")
        return

    exe = app.get("alt_exe") or app.get("exe")
    if not exe:
        write_console(console_widget, f"[ERROR] No executable for {preferred_browser_name}.\n")
        return

    if launch_executable(exe, args=[url], console=console_widget):
        write_console(console_widget, f"[SYSTEM] Opening {url} in {app.get('name')}.\n")

# ======================================================
# WINDOW FOCUS
# ======================================================

def focus_window_by_name(name, console_widget):
    try:
        app = Application(backend="uia")
        app.connect(title_re=".*", timeout=3)
        for w in app.windows():
            title = w.window_text() or ""
            if name.lower() in title.lower():
                w.set_focus()
                write_console(console_widget, f"[SYSTEM] Focused window '{title}'.\n")
                return True
    except Exception:
        pass

    write_console(console_widget, f"[ERROR] Could not find window '{name}'.\n")
    return False

# ======================================================
# INTERPRETER
# ======================================================

def interpret_command(text: str, console_widget) -> bool:
    lower = text.lower().strip()
    write_console(console_widget, f"[BOT] Checking deterministic rules...\n")

    # TYPE
    if lower.startswith("type "):
        to_type = text[len("type "):]
        write_console(console_widget, f"[BOT] Matched rule: type\n")
        time.sleep(0.5)
        pyautogui.typewrite(to_type, interval=0.03)
        return True

    # FOCUS
    if lower.startswith("focus "):
        target = text[len("focus "):].strip()
        write_console(console_widget, f"[BOT] Matched rule: focus window\n")
        focus_window_by_name(target, console_widget)
        return True

    # SHORTCUTS
    if lower.startswith("press "):
        combo = text[len("press "):].strip()
        write_console(console_widget, f"[BOT] Matched rule: keyboard shortcut\n")
        try:
            keyboard.send(combo)
        except Exception:
            write_console(console_widget, f"[ERROR] Failed shortcut '{combo}'.\n")
        return True

    # NOTES
    if lower.startswith("write a note:") or lower.startswith("write note:"):
        write_console(console_widget, f"[BOT] Matched rule: write note\n")
        note_text = text.split(":", 1)[1].strip()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filename = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(desktop, filename)
        try:
            subprocess.Popen(["notepad.exe", filepath])
            time.sleep(1.5)
            pyautogui.typewrite(note_text, interval=0.03)
        except Exception as e:
            write_console(console_widget, f"[ERROR] Note error: {e}\n")
        return True

    # YOUTUBE SEARCH
    if lower.startswith("search youtube for "):
        write_console(console_widget, f"[BOT] Matched rule: youtube search\n")
        query = text[len("search youtube for "):].strip()
        url = "https://www.youtube.com/results?search_query=" + query.replace(" ", "+")
        open_url_with_browser(url, None, console_widget)
        return True

    # FOLDER OPEN
    if lower.startswith("open "):
        folder_name = lower[len("open "):].strip()
        user_home = os.path.expanduser("~")
        folder_map = {
            "downloads": os.path.join(user_home, "Downloads"),
            "documents": os.path.join(user_home, "Documents"),
            "pictures": os.path.join(user_home, "Pictures"),
            "desktop": os.path.join(user_home, "Desktop"),
        }
        if folder_name in folder_map:
            write_console(console_widget, f"[BOT] Matched rule: open folder\n")
            try:
                os.startfile(folder_map[folder_name])
            except Exception:
                write_console(console_widget, f"[ERROR] Failed to open folder.\n")
            return True

    # CATEGORY LISTING
    if lower.startswith("show "):
        write_console(console_widget, f"[BOT] Matched rule: category listing\n")
        category = lower[len("show "):].strip()
        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        apps = load_json_file(installed_path, [])
        if not apps:
            write_console(console_widget, "[ERROR] No installed apps.\n")
            return True

        categories = {
            "games": ["steam", "roblox", "epic", "game", "launcher"],
            "browsers": ["brave", "edge", "firefox", "opera", "vivaldi"],
            "editors": ["vscode", "code", "notepad", "sublime", "pycharm"],
            "utilities": ["7zip", "winrar", "obs", "discord", "spotify"],
        }

        if category in categories:
            write_console(console_widget, f"[SYSTEM] {category.capitalize()}:\n")
            for app in apps:
                name = app.get("name", "").lower()
                if any(k in name for k in categories[category]):
                    write_console(console_widget, f" - {app.get('name')}\n")
            return True

    # URL DETECTION
    url = detect_url(lower)
    if url:
        write_console(console_widget, f"[BOT] Matched rule: URL open\n")
        preferred_browser = None
        for bname in BROWSER_NAMES.keys():
            if f"in {bname}" in lower or f"use {bname}" in lower:
                preferred_browser = bname
                break
        open_url_with_browser(url, preferred_browser, console_widget)
        return True

    # SMART OPEN + TYPE
    if "open " in lower and " and type " in lower:
        write_console(console_widget, f"[BOT] Matched rule: open + type\n")
        try:
            before, after = lower.split(" and type ", 1)
            if before.startswith("open "):
                app_name = before[len("open "):].strip()
                interpret_command(f"open {app_name}", console_widget)
                time.sleep(1.5)
                pyautogui.typewrite(after, interval=0.03)
                return True
        except:
            pass

    # SMART OPEN + URL
    if "open " in lower and " and go to " in lower:
        write_console(console_widget, f"[BOT] Matched rule: open + go to URL\n")
        try:
            before, after = lower.split(" and go to ", 1)
            if before.startswith("open "):
                app_name = before[len("open "):].strip()
                url2 = detect_url(after)
                preferred = None
                for bname in BROWSER_NAMES.keys():
                    if bname in app_name.lower():
                        preferred = bname
                        break
                open_url_with_browser(url2, preferred, console_widget)
                return True
        except:
            pass

    # SCANNER
    if any(kw in lower for kw in ["run scanner", "scan apps", "rescan", "update apps"]):
        write_console(console_widget, "[BOT] Matched rule: scanner\n")
        run_scanner_silently(console_widget)
        return True

    # INSTALLED APPS
    if "show installed apps" in lower:
        write_console(console_widget, "[BOT] Matched rule: show installed apps\n")
        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        apps = load_json_file(installed_path, [])
        for app in apps[:50]:
            write_console(console_widget, f" - {app.get('name')} ({app.get('source')})\n")
        return True

    # CUSTOM APPS
    if "show custom apps" in lower:
        write_console(console_widget, "[BOT] Matched rule: show custom apps\n")
        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)
        apps = load_json_file(custom_path, [])
        for app in apps:
            write_console(console_widget, f" - {app.get('name')} -> {app.get('exe')}\n")
        return True

    # OPEN APP
    if any(lower.startswith(cmd) for cmd in ["open ", "launch ", "start ", "run ", "play ", "open up "]):
        write_console(console_widget, "[BOT] Matched rule: open app\n")
        app_name = None
        for cmd in ["open ", "launch ", "start ", "run ", "play ", "open up "]:
            if lower.startswith(cmd):
                app_name = text[len(cmd):].strip()
                break

        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

        installed_apps = load_json_file(installed_path, [])
        custom_apps = load_json_file(custom_path, [])

        # Custom apps
        app = find_app_by_name(app_name, custom_apps)
        if app:
            exe = app.get("exe")
            launch_executable(exe, console=console_widget)
            return True

        # Installed apps
        app = find_app_by_name(app_name, installed_apps)
        if app:
            exe = app.get("alt_exe") or app.get("exe")
            launch_executable(exe, console=console_widget)
            return True

        write_console(console_widget, f"[ERROR] App '{app_name}' not found.\n")
        return True

    # DELETE CUSTOM APP
    if lower.startswith("delete custom app "):
        write_console(console_widget, "[BOT] Matched rule: delete custom app\n")
        name = text[len("delete custom app "):].strip()
        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)
        apps = load_json_file(custom_path, [])
        new_apps = [a for a in apps if a.get("name", "").lower() != name.lower()]
        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(new_apps, f, indent=4)
        write_console(console_widget, f"[SYSTEM] Deleted custom app '{name}'.\n")
        return True

    return False

# ======================================================
# ACTION EXECUTION
# ======================================================

def perform_actions(actions, console_widget):
    for action in actions:
        atype = action.get("type")
        write_console(console_widget, f"[BOT] Performing action: {atype}\n")

        if atype == "open_app":
            app_name = action.get("app_name", "").strip()
            interpret_command(f"open {app_name}", console_widget)

        elif atype == "run_scanner":
            interpret_command("run scanner", console_widget)

        elif atype == "web_search":
            query = action.get("query", "").strip()
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            webbrowser.open(url)

        elif atype == "type_text":
            text = action.get("text", "")
            pyautogui.typewrite(text, interval=0.03)
            return

        # Unknown / none
        else:
            continue


# ======================================================
# UI APPLICATION
# ======================================================

class AppUI:
    def __init__(self):
        self.window = tb.Window(themename="darkly")
        self.window.title("JARVIS Control Panel")
        self.window.geometry("950x700")

        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True)

        self.create_assistant_tab()
        self.create_automation_tab()
        self.create_settings_tab()

        # Run scanner on startup
        threading.Thread(
            target=lambda: run_scanner_silently(self.console),
            daemon=True
        ).start()

    # --------------------------------------------------
    # TAB 1 — Assistant (Console)
    # --------------------------------------------------
    def create_assistant_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Assistant")

        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", padx=10, pady=5)

        # Model selector (kept)
        ttk.Label(top_frame, text="Model:").grid(row=0, column=0, sticky="w", padx=5)
        self.models = ["llama3", "mistral", "phi3", "qwen2", "codellama"]
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(top_frame, textvariable=self.model_var, values=self.models, width=15).grid(
            row=0, column=1, padx=5
        )

        # Console output
        self.console = tk.Text(frame, height=22, bg="#1e1e1e", fg="white", state="disabled")
        self.console.pack(fill="both", expand=True, padx=10, pady=10)

        # Input field
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill="x", padx=10, pady=5)

        self.input_entry = ttk.Entry(input_frame)
        self.input_entry.pack(side="left", fill="x", expand=True)

        send_btn = ttk.Button(input_frame, text="Send", command=self.send_ai_command)
        send_btn.pack(side="left", padx=5)

    def send_ai_command(self):
        text = self.input_entry.get().strip()
        if not text:
            return

        write_console(self.console, f"[USER] {text}\n")
        self.input_entry.delete(0, "end")

        threading.Thread(
            target=self.run_ai_thread,
            args=(text,),
            daemon=True
        ).start()

    def run_ai_thread(self, text):
        # 1) deterministic rules
        handled = interpret_command(text, self.console)

        # 2) classifier if not handled
        if not handled:
            intent_data = classify_intent(text)
            write_console(self.console, f"[BOT] Intent: {intent_data}\n")
            actions = intent_data.get("actions", [])
            if actions:
                perform_actions(actions, self.console)

        # 3) NO conversational AI reply (removed)

    # --------------------------------------------------
    # TAB 2 — Automation Tools
    # --------------------------------------------------
    def create_automation_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Automation Tools")

        # Left side: Custom Apps
        left = ttk.Frame(frame)
        left.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        ttk.Label(left, text="Custom Apps", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=5)

        ttk.Label(left, text="App Name:").pack(anchor="w", pady=2)
        self.custom_name = ttk.Entry(left)
        self.custom_name.pack(fill="x")

        ttk.Label(left, text="Executable Path:").pack(anchor="w", pady=2)
        path_frame = ttk.Frame(left)
        path_frame.pack(fill="x")

        self.custom_path = ttk.Entry(path_frame)
        self.custom_path.pack(side="left", fill="x", expand=True)

        browse_btn = ttk.Button(path_frame, text="Browse", command=self.browse_exe)
        browse_btn.pack(side="left", padx=5)

        add_btn = ttk.Button(left, text="Add Custom App", command=self.add_custom_app)
        add_btn.pack(pady=5)

    def browse_exe(self):
        path = filedialog.askopenfilename(title="Select Executable", filetypes=[("Executable Files", "*.exe")])
        if path:
            self.custom_path.delete(0, "end")
            self.custom_path.insert(0, path)

    def add_custom_app(self):
        name = self.custom_name.get().strip()
        path = self.custom_path.get().strip()

        if not name or not path:
            write_console(self.console, "[ERROR] Name or path missing.\n")
            return

        save_custom_app(name, path, self.console)
        write_console(self.console, f"[SYSTEM] Custom app '{name}' added.\n")

    # --------------------------------------------------
    # TAB 3 — Settings (placeholder)
    # --------------------------------------------------
    def create_settings_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Settings")

        ttk.Label(frame, text="Settings will go here.", font=("Segoe UI", 12)).pack(pady=20)


# ======================================================
# MAIN ENTRY
# ======================================================

if __name__ == "__main__":
    app = AppUI()
    app.window.mainloop()
