import sys
import os
import subprocess
import time
import json
import threading

import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as tb

# Hide console window on Windows
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# -----------------------------
# CONFIG
# -----------------------------
BIN_DIR = "bin"
MAIN_FILE = os.path.join(BIN_DIR, "main.pyw")

MAIN_URL = "https://raw.githubusercontent.com/AMTRUE1Z/dump/refs/heads/main/main.pyw"

REQUIRED_PACKAGES = [
    "requests",
    "pyautogui",
    "pywinauto",
    "keyboard",
    "ttkbootstrap",
]

REQUIRED_MODELS = [
    "llama3",
    "phi3:mini",
    "mistral",
    "qwen2",
    "codellama"
]

OLLAMA_DOWNLOAD = "https://ollama.com/download"


# -----------------------------
# UI LOGGER
# -----------------------------
class BootstrapUI:
    def __init__(self):
        self.app = tb.Window(themename="darkly")
        self.app.title("JARVIS Bootstrapper")
        self.app.geometry("650x400")
        self.app.resizable(False, False)

        main_frame = ttk.Frame(self.app)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(main_frame, text="Initializing JARVIS Environment...", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        self.progress = ttk.Progressbar(main_frame, mode="determinate", maximum=6)
        self.progress.pack(fill="x", pady=8)

        self.log = tk.Text(main_frame, height=16, bg="#1e1e1e", fg="white", state="disabled")
        self.log.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=5)

        self.close_btn = ttk.Button(btn_frame, text="Close", command=self.app.destroy, state="disabled")
        self.close_btn.pack(side="right")

    def write(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
        self.app.update_idletasks()

    def set_step(self, step):
        self.progress["value"] = step
        self.app.update_idletasks()

    def enable_close(self):
        self.close_btn.config(state="normal")

    def run(self):
        self.app.mainloop()


ui = BootstrapUI()


# -----------------------------
# HELPERS
# -----------------------------
def ensure_bin_folder():
    ui.write("[1/6] Creating bin folder...")
    if not os.path.isdir(BIN_DIR):
        os.makedirs(BIN_DIR)
    ui.set_step(1)


def download_file(url, dest):
    import urllib.request
    try:
        ui.write(f"  - Downloading {os.path.basename(dest)}...")
        urllib.request.urlretrieve(url, dest)
        ui.write(f"    -> Saved to {dest}")
    except Exception as e:
        ui.write(f"    [ERROR] Failed to download {url}: {e}")
        raise


def download_main():
    ui.write("[2/6] Downloading main.pyw...")
    download_file(MAIN_URL, MAIN_FILE)
    ui.set_step(2)


def ensure_python_packages():
    ui.write("[3/6] Checking Python dependencies...")
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            ui.write(f"  - {pkg}: OK")
        except ImportError:
            ui.write(f"  - {pkg}: MISSING")
            missing.append(pkg)

    if not missing:
        ui.write("All required packages are already installed.")
        ui.set_step(3)
        return

    ui.write("Installing missing packages...")
    for pkg in missing:
        try:
            ui.write(f"  - Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            ui.write(f"    -> {pkg} installed.")
        except Exception as e:
            ui.write(f"    [ERROR] Failed to install {pkg}: {e}")
    ui.set_step(3)


def is_ollama_installed():
    try:
        subprocess.run(["ollama", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def copy_to_clipboard(text):
    try:
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
    except Exception:
        pass


def is_ollama_running():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


def start_ollama():
    ui.write("[4/6] Checking Ollama installation...")
    if not is_ollama_installed():
        ui.write("  - Ollama is NOT installed.")
        copy_to_clipboard(OLLAMA_DOWNLOAD)
        messagebox.showwarning(
            "Ollama Not Installed",
            "Ollama is not installed on this system.\n\n"
            "The download link has been copied to your clipboard:\n"
            f"{OLLAMA_DOWNLOAD}"
        )
        ui.enable_close()
        return False

    ui.write("  - Ollama is installed.")
    if is_ollama_running():
        ui.write("  - Ollama is already running.")
        ui.set_step(4)
        return True

    ui.write("  - Starting Ollama server in background...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        ui.write(f"    [ERROR] Failed to start Ollama: {e}")
        ui.enable_close()
        return False

    ui.write("  - Waiting for Ollama to respond...")
    for _ in range(60):
        if is_ollama_running():
            ui.write("    -> Ollama is now responding.")
            ui.set_step(4)
            return True
        time.sleep(1)

    ui.write("    [ERROR] Ollama did not respond in time.")
    ui.enable_close()
    return False


def ensure_models():
    ui.write("[5/6] Checking required Ollama models...")
    import requests

    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        installed = [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        ui.write(f"  [ERROR] Failed to query Ollama models: {e}")
        installed = []

    ui.write(f"  - Installed models: {', '.join(installed) if installed else '(none)'}")

    missing = [m for m in REQUIRED_MODELS if m not in installed]
    if not missing:
        ui.write("  - All required models are already installed.")
        ui.set_step(5)
        return

    ui.write(f"  - Missing models: {', '.join(missing)}")
    for model in missing:
        ui.write(f"    -> Pulling {model}...")
        try:
            subprocess.run(
                ["ollama", "pull", model],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            ui.write(f"       {model} pulled.")
        except Exception as e:
            ui.write(f"       [ERROR] Failed to pull {model}: {e}")

    ui.set_step(5)


def launch_main():
    ui.write("[6/6] Launching JARVIS main UI...")
    if not os.path.isfile(MAIN_FILE):
        ui.write(f"  [ERROR] main.pyw not found at {MAIN_FILE}")
        messagebox.showerror("Error", f"main.pyw not found at {MAIN_FILE}")
        ui.enable_close()
        return

    try:
        subprocess.Popen([sys.executable, MAIN_FILE, "--allow-launch"])
        ui.write("  -> JARVIS launched.")
    except Exception as e:
        ui.write(f"  [ERROR] Failed to launch main.pyw: {e}")
        messagebox.showerror("Error", f"Failed to launch main.pyw:\n{e}")
        ui.enable_close()
        return

    ui.write("Bootstrap complete. You can close this window.")
    ui.enable_close()


def bootstrap_flow():
    try:
        ensure_bin_folder()
        download_main()
        ensure_python_packages()
        if not start_ollama():
            return
        ensure_models()
        launch_main()
    except Exception as e:
        ui.write(f"[FATAL] {e}")
        messagebox.showerror("Fatal Error", str(e))
        ui.enable_close()


def main():
    threading.Thread(target=bootstrap_flow, daemon=True).start()
    ui.run()


if __name__ == "__main__":
    main()