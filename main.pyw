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

if "--allow-launch" not in sys.argv:
    raise SystemExit("This program must be launched through the bootstrapper.")

# ======================================================
# HIDE CONSOLE WINDOW
# ======================================================
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# ======================================================
# CONFIG
# ======================================================

GITHUB_RAW_SCANNER_URL = (
    "https://raw.githubusercontent.com/AMTRUE1Z/dump/refs/heads/main/scanner.py"
)

SCANNER_FILENAME = "scanner.py"
DUMP_DIR = "dump"
CUSTOM_APPS_FILE = "custom_apps.txt"

# conversational default model (dropdown default)
DEFAULT_MODEL = "llama3"

# intent classifier model
INTENT_MODEL = "phi3:mini"

PERSONALITY_PROMPTS = {
    "JARVIS": "Respond in a formal, elegant, respectful tone, like Marvel's JARVIS.",
    "Playful": "Respond in a fun, energetic, expressive tone with humor.",
    "Neutral": "Respond in a friendly, calm, helpful tone.",
    "Sarcastic": "Respond with dry humor, light sarcasm, but still helpful.",
    "Hacker": "Respond in a calm, technical, hacker‑assistant tone, minimal emotion."
}


# ======================================================
# HELPERS
# ======================================================

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
        subprocess.run(
            [sys.executable, SCANNER_FILENAME, "--allow-scan"],
            capture_output=True,
            text=True
        )
        if console:
            write_console(console, "Scanner finished.\n")
    except Exception as e:
        if console:
            write_console(console, f"Scanner error: {e}\n")


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

    write_console(console, f"Added custom app: {name} -> {path}\n")


def find_app_by_name(name, apps_list):
    import difflib

    name = name.lower().replace(" ", "")
    best_match = None
    best_score = 0

    for app in apps_list:
        app_name = app.get("name", "").lower()
        app_name_compact = app_name.replace(" ", "")

        # direct match
        if name == app_name_compact:
            return app

        # partial match
        if name in app_name_compact:
            return app

        # fuzzy match
        score = difflib.SequenceMatcher(None, name, app_name_compact).ratio()
        if score > best_score:
            best_score = score
            best_match = app

    if best_score >= 0.55:
        return best_match

    return None


def launch_executable(path, args=None):
    try:
        if args:
            subprocess.Popen([path] + args)
        else:
            os.startfile(path)
        return True
    except Exception:
        return False


# ======================================================
# READ‑ONLY CONSOLE WRITER
# ======================================================

def write_console(widget, text):
    widget.config(state="normal")
    widget.insert("end", text)
    widget.see("end")
    widget.config(state="disabled")


# ======================================================
# REAL OLLAMA AI
# ======================================================

def ai_response_ollama(model, prompt):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt},
            stream=True,
            timeout=120
        )

        full_text = ""

        for line in response.iter_lines():
            if not line:
                continue

            try:
                data = json.loads(line.decode("utf-8"))
            except:
                continue

            chunk = data.get("response")
            if chunk:
                full_text += chunk

            if data.get("done"):
                break

        return full_text.strip() if full_text else "(no response)"

    except Exception as e:
        return f"[AI ERROR] {e}"


# ======================================================
# INTENT CLASSIFIER
# ======================================================

def classify_intent(text: str):
    prompt = f"""
You are an intent classifier for a desktop assistant.

Your job is to read the user's message and respond ONLY with JSON.

You must output an object with:
- "actions": a list of actions to perform, in order.

Each action is an object with:
- "type": one of ["open_app", "web_search", "run_scanner", "type_text", "none"]
- For "open_app": include "app_name"
- For "web_search": include "query"
- For "type_text": include "text"

Examples:

User: "open brave and roblox"
JSON:
{{
  "actions": [
    {{"type": "open_app", "app_name": "brave"}},
    {{"type": "open_app", "app_name": "roblox"}}
  ]
}}

User: "open notepad and type hello world"
JSON:
{{
  "actions": [
    {{"type": "open_app", "app_name": "notepad"}},
    {{"type": "type_text", "text": "hello world"}}
  ]
}}

User: "scan my apps again"
JSON:
{{
  "actions": [
    {{"type": "run_scanner"}}
  ]
}}

User: "where do birds live"
JSON:
{{
  "actions": [
    {{"type": "none"}}
  ]
}}

Respond ONLY with JSON. No extra text.

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
# BROWSER + URL HELPERS
# ======================================================

BROWSER_NAMES = {
    "brave": ["brave"],
    "chrome": ["chrome", "google chrome"],
    "edge": ["edge", "microsoft edge"],
    "firefox": ["firefox", "mozilla firefox"],
    "opera": ["opera"],
    "vivaldi": ["vivaldi"],
}

def detect_url(text: str):
    pattern = re.compile(r"(https?://\S+|\b[\w\-]+\.(com|net|org|io|gg|dev|app|tv|gg|ai)\b)")
    match = pattern.search(text)
    if match:
        url = match.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return url
    return None


def open_url_with_browser(url, preferred_browser_name, console_widget):
    """
    preferred_browser_name: e.g. 'chrome', 'brave', 'edge', etc.
    If preferred is None -> use default browser.
    If preferred is set but not installed -> message.
    """
    ensure_dump_folder()
    installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
    custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

    installed_apps = load_json_file(installed_path, [])
    custom_apps = load_json_file(custom_path, [])

    if not preferred_browser_name:
        # default browser
        try:
            webbrowser.open(url)
            write_console(console_widget, f"AI: Opening {url} in default browser.\n")
        except Exception:
            write_console(console_widget, f"AI: Failed to open {url} in default browser.\n")
        return

    # try to find browser in installed/custom apps
    candidates = BROWSER_NAMES.get(preferred_browser_name.lower(), [preferred_browser_name.lower()])

    def find_browser(cands, apps):
        for c in cands:
            app = find_app_by_name(c, apps)
            if app:
                return app
        return None

    app = find_browser(candidates, custom_apps)
    if not app:
        app = find_browser(candidates, installed_apps)

    if not app:
        write_console(console_widget, f"AI: I couldn't find {preferred_browser_name} installed on this PC.\n")
        return

    exe = app.get("alt_exe") or app.get("exe")
    if not exe:
        write_console(console_widget, f"AI: {preferred_browser_name} entry has no executable path.\n")
        return

    if launch_executable(exe, args=[url]):
        write_console(console_widget, f"AI: Opening {url} in {app.get('name')}.\n")
    else:
        write_console(console_widget, f"AI: Failed to launch {app.get('name')} with URL.\n")


# ======================================================
# WINDOW FOCUS HELPER
# ======================================================

def focus_window_by_name(name, console_widget):
    """
    Try to focus a window whose title contains the given name (case-insensitive).
    """
    try:
        app = Application(backend="uia")
        # This is a best-effort approach; may not catch everything but works for many apps.
        app.connect(title_re=".*", timeout=3)
        for w in app.windows():
            title = w.window_text() or ""
            if name.lower() in title.lower():
                w.set_focus()
                write_console(console_widget, f"AI: Focused window '{title}'.\n")
                return True
    except Exception:
        pass

    write_console(console_widget, f"AI: Could not find a window matching '{name}'.\n")
    return False


# ======================================================
# INTERPRETER (TEXT COMMANDS)
# ======================================================

def interpret_command(text: str, console_widget) -> bool:
    lower = text.lower().strip()

    # --------------------------------------------------
    # DETERMINISTIC RULES (RUN BEFORE CLASSIFIER)
    # --------------------------------------------------

    # --- Direct typing: "type hello world" ---
    if lower.startswith("type "):
        to_type = text[len("type "):]
        if to_type:
            write_console(console_widget, f"AI: Typing: '{to_type}'\n")
            time.sleep(0.5)
            pyautogui.typewrite(to_type, interval=0.03)
        return True

    # --- Focus window: "focus notepad" / "focus brave" ---
    if lower.startswith("focus "):
        target = text[len("focus "):].strip()
        if target:
            focus_window_by_name(target, console_widget)
        return True

    # --- Keyboard shortcuts: "press ctrl+s", "press alt+f4" ---
    if lower.startswith("press "):
        combo = text[len("press "):].strip()
        if combo:
            try:
                keyboard.send(combo)
                write_console(console_widget, f"AI: Pressed shortcut '{combo}'.\n")
            except Exception:
                write_console(console_widget, f"AI: Failed to press shortcut '{combo}'.\n")
        return True

    # --- Write a note: "write a note: buy milk" ---
    if lower.startswith("write a note:") or lower.startswith("write note:"):
        note_text = text.split(":", 1)[1].strip() if ":" in text else ""
        if not note_text:
            write_console(console_widget, "AI: You must provide note text after 'write a note:'.\n")
            return True

        # Open notepad, type note, save to timestamped file on Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filename = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(desktop, filename)

        write_console(console_widget, f"AI: Creating note on Desktop: {filename}\n")

        # Open notepad with file path
        try:
            subprocess.Popen(["notepad.exe", filepath])
            time.sleep(1.5)
            pyautogui.typewrite(note_text, interval=0.03)
            write_console(console_widget, "AI: Note written.\n")
        except Exception as e:
            write_console(console_widget, f"AI: Failed to write note: {e}\n")

        return True

    # --- YouTube search: "search youtube for lofi beats" ---
    if lower.startswith("search youtube for "):
        query = text[len("search youtube for "):].strip()
        if query:
            url = "https://www.youtube.com/results?search_query=" + query.replace(" ", "+")
            write_console(console_widget, f"AI: Searching YouTube for '{query}'.\n")
            open_url_with_browser(url, None, console_widget)
        return True

    # --- Open folders: downloads/documents/pictures/desktop ---
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
            path = folder_map[folder_name]
            if os.path.isdir(path):
                try:
                    os.startfile(path)
                    write_console(console_widget, f"AI: Opened folder '{folder_name}'.\n")
                except Exception:
                    write_console(console_widget, f"AI: Failed to open folder '{folder_name}'.\n")
            else:
                write_console(console_widget, f"AI: Folder '{folder_name}' does not exist.\n")
            return True

    # --- Categorized app listing: "show games", "show browsers", etc. ---
    if lower.startswith("show "):
        category = lower[len("show "):].strip()
        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        apps = load_json_file(installed_path, [])

        if not apps:
            write_console(console_widget, "AI: No installed apps found (run scanner first).\n\n")
            return True

        categories = {
            "games": ["steam", "roblox", "epic", "game", "launcher"],
            "browsers": ["chrome", "brave", "edge", "firefox", "opera", "vivaldi"],
            "editors": ["vscode", "code", "notepad", "sublime", "pycharm"],
            "utilities": ["7zip", "winrar", "obs", "discord", "spotify"],
        }

        if category in categories:
            keywords = categories[category]
            write_console(console_widget, f"AI: {category.capitalize()} detected:\n")
            count = 0
            for app in apps:
                name = app.get("name", "").lower()
                if any(k in name for k in keywords):
                    write_console(console_widget, f" - {app.get('name')}\n")
                    count += 1
            if count == 0:
                write_console(console_widget, " (none found)\n")
            write_console(console_widget, "\n")
            return True

    # --- Direct website opening + browser override ---
    # Patterns like:
    # "open youtube.com"
    # "go to github.com"
    # "open youtube.com in chrome"
    # "use brave to open github.com"
    url = detect_url(lower)
    if url:
        preferred_browser = None

        # detect explicit browser mentions
        for bname in BROWSER_NAMES.keys():
            if f"in {bname}" in lower or f"use {bname}" in lower or f"open {bname}" in lower:
                preferred_browser = bname
                break

        open_url_with_browser(url, preferred_browser, console_widget)
        return True

    # --- Smart "open X and type Y" combo (fallback) ---
    if "open " in lower and " and type " in lower:
        # naive parse: "open notepad and type hello world"
        try:
            before, after = lower.split(" and type ", 1)
            if before.startswith("open "):
                app_name = text[len("open "):len(text) - len(after) - len(" and type ")].strip()
                to_type = text.split(" and type ", 1)[1]
                if app_name and to_type:
                    write_console(console_widget, f"AI: Opening '{app_name}' then typing.\n")
                    interpret_command(f"open {app_name}", console_widget)
                    time.sleep(1.5)
                    pyautogui.typewrite(to_type, interval=0.03)
                    return True
        except Exception:
            pass

    # --- Smart "open X and go to URL" combo ---
    if "open " in lower and " and go to " in lower:
        # "open brave and go to youtube.com"
        try:
            before, after = lower.split(" and go to ", 1)
            if before.startswith("open "):
                app_name = before[len("open "):].strip()
                url2 = detect_url(after)
                if app_name and url2:
                    # try to open specific browser if it's a known browser name
                    preferred = None
                    for bname in BROWSER_NAMES.keys():
                        if bname in app_name.lower():
                            preferred = bname
                            break
                    write_console(console_widget, f"AI: Opening '{app_name}' and going to {url2}.\n")
                    open_url_with_browser(url2, preferred, console_widget)
                    return True
        except Exception:
            pass

    # --------------------------------------------------
    # ORIGINAL RULES (APPS, SCANNER, ETC.)
    # --------------------------------------------------

    # --- Scanner commands ---
    if any(kw in lower for kw in ["run scanner", "scan apps", "rescan", "update apps"]):
        write_console(console_widget, "AI: Running scanner...\n")
        run_scanner_silently(console_widget)
        return True

    # --- Show installed apps ---
    if "show installed apps" in lower or "list installed apps" in lower:
        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        apps = load_json_file(installed_path, [])
        if not apps:
            write_console(console_widget, "AI: No installed apps found (run scanner first).\n\n")
            return True
        write_console(console_widget, "AI: Installed apps:\n")
        for app in apps[:50]:
            write_console(console_widget, f" - {app.get('name')} ({app.get('source')})\n")
        write_console(console_widget, "\n")
        return True

    # --- Show custom apps ---
    if "show custom apps" in lower or "list custom apps" in lower:
        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)
        apps = load_json_file(custom_path, [])
        if not apps:
            write_console(console_widget, "AI: No custom apps defined.\n\n")
            return True
        write_console(console_widget, "AI: Custom apps:\n")
        for app in apps:
            write_console(console_widget, f" - {app.get('name')} -> {app.get('exe')}\n")
        write_console(console_widget, "\n")
        return True

    # --- Open / launch app (installed or custom) ---
    if any(lower.startswith(cmd) for cmd in ["open ", "launch ", "start ", "run ", "play ", "open up "]):
        app_name = None
        for cmd in ["open ", "launch ", "start ", "run ", "play ", "open up "]:
            if lower.startswith(cmd):
                app_name = text[len(cmd):].strip()
                break

        if not app_name:
            write_console(console_widget, "AI: You need to specify an app name.\n\n")
            return True

        installed_path = os.path.join(DUMP_DIR, "installed_apps.txt")
        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

        installed_apps = load_json_file(installed_path, [])
        custom_apps = load_json_file(custom_path, [])

        # 1) check custom apps first
        app = find_app_by_name(app_name, custom_apps)
        if app:
            exe = app.get("exe")
            if exe and launch_executable(exe):
                write_console(console_widget, f"AI: Launched custom app '{app['name']}'.\n\n")
            else:
                write_console(console_widget, f"AI: Failed to launch '{app['name']}'.\n\n")
            return True

        # 2) check installed apps
        app = find_app_by_name(app_name, installed_apps)
        if app:
            exe = app.get("alt_exe") or app.get("exe")

            if exe and exe.startswith("steam://"):
                if launch_executable(exe):
                    write_console(console_widget, f"AI: Launched Steam app '{app['name']}'.\n\n")
                else:
                    write_console(console_widget, f"AI: Failed to launch Steam app '{app['name']}'.\n\n")
                return True

            if exe and launch_executable(exe):
                write_console(console_widget, f"AI: Launched '{app['name']}'.\n\n")
            else:
                write_console(console_widget, f"AI: Failed to launch '{app['name']}'.\n\n")
            return True

        write_console(console_widget, f"AI: I couldn't find an app named '{app_name}'.\n\n")
        return True

    # --- Switch model (just guidance) ---
    if "switch model to " in lower or "use model " in lower:
        write_console(console_widget, "AI: You can change the model from the dropdown above.\n\n")
        return True

    # --- Delete custom app ---
    if lower.startswith("delete custom app "):
        name = text[len("delete custom app "):].strip()
        if not name:
            write_console(console_widget, "AI: You must specify the custom app name.\n\n")
            return True

        custom_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)
        apps = load_json_file(custom_path, [])

        new_apps = [a for a in apps if a.get("name", "").lower() != name.lower()]

        if len(new_apps) == len(apps):
            write_console(console_widget, f"AI: No custom app named '{name}' found.\n\n")
            return True

        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(new_apps, f, indent=4)

        write_console(console_widget, f"AI: Deleted custom app '{name}'.\n\n")
        return True

    return False


# ======================================================
# ACTION EXECUTION
# ======================================================

def perform_actions(actions, console_widget):
    for action in actions:
        atype = action.get("type")

        # --- open app ---
        if atype == "open_app":
            app_name = action.get("app_name", "").strip()
            if app_name:
                interpret_command(f"open {app_name}", console_widget)

        # --- run scanner ---
        elif atype == "run_scanner":
            interpret_command("run scanner", console_widget)

        # --- web search ---
        elif atype == "web_search":
            query = action.get("query", "").strip()
            if query:
                write_console(console_widget, f"AI: Searching the web for '{query}'...\n")
                try:
                    url = "https://www.google.com/search?q=" + query.replace(" ", "+")
                    webbrowser.open(url)
                except Exception:
                    write_console(console_widget, "AI: Failed to open browser.\n\n")

        # --- type text into current window ---
        elif atype == "type_text":
            text = action.get("text", "")
            if text:
                write_console(console_widget, f"AI: Typing into active window: '{text}'\n")
                time.sleep(1)
                pyautogui.typewrite(text, interval=0.03)

        # --- none / unknown ---
        else:
            continue


# ======================================================
# UI APPLICATION (MODERNIZED LAYOUT)
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

        # Automatically run scanner on startup (in background)
        threading.Thread(
            target=lambda: run_scanner_silently(None),
            daemon=True
        ).start()

    # --------------------------------------------------
    # TAB 1 — Assistant (AI Console)
    # --------------------------------------------------
    def create_assistant_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Assistant")

        top_frame = ttk.Frame(frame)
        top_frame.pack(fill="x", padx=10, pady=5)

        # Model selector
        ttk.Label(top_frame, text="Model:").grid(row=0, column=0, sticky="w", padx=5)
        self.models = ["llama3", "mistral", "phi3", "qwen2", "codellama"]
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        ttk.Combobox(top_frame, textvariable=self.model_var, values=self.models, width=15).grid(
            row=0, column=1, padx=5
        )

        # Personality selector
        ttk.Label(top_frame, text="Personality:").grid(row=0, column=2, sticky="w", padx=5)
        self.personalities = ["JARVIS", "Playful", "Neutral", "Sarcastic", "Hacker"]
        self.personality_var = tk.StringVar(value="JARVIS")
        ttk.Combobox(top_frame, textvariable=self.personality_var, values=self.personalities, width=15).grid(
            row=0, column=3, padx=5
        )

        # Console output (read‑only)
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

        model = self.model_var.get()

        write_console(self.console, f"You ({model}): {text}\n")
        self.input_entry.delete(0, "end")

        threading.Thread(
            target=self.run_ai_thread,
            args=(model, text),
            daemon=True
        ).start()

    def run_ai_thread(self, model, text):
        # 1) try deterministic interpreter first
        handled = interpret_command(text, self.console)

        # 2) classify into actions (phi3:mini) if not handled
        if not handled:
            intent_data = classify_intent(text)
            actions = intent_data.get("actions", [])

            if actions:
                perform_actions(actions, self.console)

        # 3) conversational response with selected model + personality
        personality = self.personality_var.get()
        style_prompt = PERSONALITY_PROMPTS.get(personality, "")
        full_prompt = f"{style_prompt}\nUser: {text}\nAssistant:"

        reply = ai_response_ollama(model, full_prompt)
        write_console(self.console, f"AI: {reply}\n\n")

    # --------------------------------------------------
    # TAB 2 — Automation Tools (Custom Apps + Quick Actions)
    # --------------------------------------------------
    def create_automation_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Automation Tools")

        # Left: Custom Apps
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

        add_btn = ttk.Button(
            left,
            text="Add Custom App",
            bootstyle="success",
            command=self.add_custom_app
        )
        add_btn.pack(pady=8)

        ttk.Separator(left).pack(fill="x", pady=10)

        ttk.Label(left, text="Manage Custom Apps", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)

        self.custom_app_var = tk.StringVar()
        self.custom_app_dropdown = ttk.Combobox(left, textvariable=self.custom_app_var, state="readonly")
        self.custom_app_dropdown.pack(fill="x")

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", pady=8)

        refresh_btn = ttk.Button(btn_frame, text="Refresh", bootstyle="info", command=self.refresh_custom_apps)
        refresh_btn.pack(side="left", padx=5)

        delete_btn = ttk.Button(btn_frame, text="Delete", bootstyle="danger", command=self.delete_custom_app)
        delete_btn.pack(side="left", padx=5)

        self.refresh_custom_apps()

        # Right: Quick Help / Examples
        right = ttk.Frame(frame)
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        ttk.Label(right, text="Quick Commands", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=5)

        examples = [
            "open notepad and type hello world",
            "open youtube.com",
            "open youtube.com in chrome",
            "search youtube for lofi beats",
            "write a note: remember to test this",
            "open downloads",
            "show games",
            "press ctrl+shift+n",
            "focus notepad",
        ]

        txt = tk.Text(right, height=18, bg="#1e1e1e", fg="white")
        txt.pack(fill="both", expand=True)
        txt.insert("end", "Examples you can try:\n\n")
        for ex in examples:
            txt.insert("end", f" - {ex}\n")
        txt.config(state="disabled")

    def browse_exe(self):
        path = filedialog.askopenfilename(
            title="Select Executable",
            filetypes=[("Executable Files", "*.exe")]
        )
        if path:
            self.custom_path.delete(0, "end")
            self.custom_path.insert(0, path)

    def add_custom_app(self):
        name = self.custom_name.get().strip()
        path = self.custom_path.get().strip()

        if not name or not path:
            messagebox.showerror("Error", "Both fields are required.")
            return

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

        data.append({"name": name, "exe": path})

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        self.custom_name.delete(0, "end")
        self.custom_path.delete(0, "end")

        self.refresh_custom_apps()

        messagebox.showinfo("Success", f"Added custom app: {name}")

    def refresh_custom_apps(self):
        ensure_dump_folder()
        file_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

        if not os.path.isfile(file_path):
            self.custom_app_dropdown["values"] = []
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = []

        names = [entry["name"] for entry in data]
        self.custom_app_dropdown["values"] = names

        if names:
            self.custom_app_dropdown.current(0)

    def delete_custom_app(self):
        selected = self.custom_app_var.get()
        if not selected:
            messagebox.showerror("Error", "No app selected.")
            return

        file_path = os.path.join(DUMP_DIR, CUSTOM_APPS_FILE)

        if not os.path.isfile(file_path):
            return

        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except:
                data = []

        data = [entry for entry in data if entry["name"] != selected]

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        self.refresh_custom_apps()
        messagebox.showinfo("Deleted", f"Removed custom app: {selected}")

    # --------------------------------------------------
    # TAB 3 — Settings (Scanner + Maintenance)
    # --------------------------------------------------
    def create_settings_tab(self):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Settings")

        ttk.Label(frame, text="Scanner & Maintenance", font=("Segoe UI", 14)).pack(pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)

        run_btn = ttk.Button(
            btn_frame,
            text="Run Scanner",
            bootstyle="primary",
            command=lambda: run_scanner_silently(self.scan_console)
        )
        run_btn.pack(side="left", padx=5)

        download_btn = ttk.Button(
            btn_frame,
            text="Download Latest Scanner",
            bootstyle="info",
            command=download_scanner
        )
        download_btn.pack(side="left", padx=5)

        self.scan_console = tk.Text(frame, height=20, bg="#1e1e1e", fg="white", state="disabled")
        self.scan_console.pack(fill="both", expand=True, padx=10, pady=10)

    def run(self):
        self.window.mainloop()


# ======================================================
# START APP
# ======================================================
if __name__ == "__main__":
    ensure_dump_folder()
    download_scanner()
    ui = AppUI()
    ui.run()
