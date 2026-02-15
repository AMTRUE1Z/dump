import os
import json
import subprocess
import winreg
import glob

# ======================================================
# CONFIG
# ======================================================

STEAM_ROOT = r"C:\Program Files (x86)\Steam"
EPIC_MANIFEST_DIR = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"

PROGRAM_FILES_DIRS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)"
]

APPDATA_DIRS = [
    os.path.expanduser(r"~\AppData\Local"),
    os.path.expanduser(r"~\AppData\Roaming")
]

BAD_KEYWORDS = [
    "uninstall", "setup", "install", "update", "helper",
    "service", "repair", "cleanup", "crash", "report",
    "bug", "debug", "maint", "patch", "upgrade", "driver",
    "redistributable", "runtime"
]


# ======================================================
# HELPERS
# ======================================================

def is_bad_exe(path: str) -> bool:
    if not path:
        return True
    lower = path.lower()
    return any(k in lower for k in BAD_KEYWORDS)


def safe_reg_get(key, value_name):
    try:
        val, _ = winreg.QueryValueEx(key, value_name)
        return val
    except OSError:
        return None


def normalize_display_icon(icon_value):
    if not icon_value:
        return None

    icon_value = icon_value.strip().strip('"')

    if "," in icon_value:
        icon_value = icon_value.split(",", 1)[0]

    if not os.path.isfile(icon_value):
        return None

    if is_bad_exe(icon_value):
        return None

    return icon_value


def find_primary_exe_in_folder(folder):
    if not folder or not os.path.isdir(folder):
        return None

    try:
        entries = [f for f in os.listdir(folder) if f.lower().endswith(".exe")]
        if not entries:
            return None

        good = [f for f in entries if not is_bad_exe(f)]
        if not good:
            return None

        folder_name = os.path.basename(folder).lower()

        for exe in good:
            if folder_name and folder_name in exe.lower():
                return os.path.join(folder, exe)

        launcher_keywords = ["steam", "client", "launcher", "main", "app", "run", "game"]
        for exe in good:
            if any(k in exe.lower() for k in launcher_keywords):
                return os.path.join(folder, exe)

        return os.path.join(folder, good[0])

    except Exception:
        return None


def resolve_lnk(path):
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(path)
        target = shortcut.TargetPath
        if target and os.path.isfile(target) and not is_bad_exe(target):
            return target
    except Exception:
        return None
    return None


def add_entry(results, name, exe, source, alt_exe=None):
    if not exe:
        return
    entry = {
        "name": name,
        "exe": exe,
        "alt_exe": alt_exe,
        "source": source
    }
    results.append(entry)


# ======================================================
# WINGET
# ======================================================

def scan_winget():
    apps = []
    try:
        result = subprocess.run(
            ["winget", "list", "--source", "winget", "--output", "json"],
            capture_output=True,
            text=True
        )
        if not result.stdout.strip():
            return apps

        data = json.loads(result.stdout)
        for entry in data:
            name = entry.get("Name")
            install_location = entry.get("InstallLocation") or entry.get("Path")
            if not name or not install_location:
                continue

            exe = find_primary_exe_in_folder(install_location)
            if exe and not is_bad_exe(exe):
                add_entry(apps, name, exe, "winget")
        return apps
    except Exception:
        return apps


# ======================================================
# REGISTRY
# ======================================================

def scan_registry():
    apps = []

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, path in registry_paths:
        try:
            key = winreg.OpenKey(hive, path)
        except OSError:
            continue

        count = winreg.QueryInfoKey(key)[0]

        for i in range(count):
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)

                name = safe_reg_get(subkey, "DisplayName")
                if not name:
                    continue

                icon = safe_reg_get(subkey, "DisplayIcon")
                install_location = safe_reg_get(subkey, "InstallLocation")

                exe = None

                if icon:
                    exe = normalize_display_icon(icon)

                if not exe and install_location:
                    exe = find_primary_exe_in_folder(install_location)

                if exe and os.path.isfile(exe) and not is_bad_exe(exe):
                    add_entry(apps, name, exe, "registry")

            except Exception:
                continue

    return apps


# ======================================================
# START MENU
# ======================================================

def scan_start_menu():
    apps = []
    shortcut_dirs = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs")
    ]

    for base in shortcut_dirs:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for file in files:
                if file.lower().endswith(".lnk"):
                    full = os.path.join(root, file)
                    target = resolve_lnk(full)
                    if target and not is_bad_exe(target):
                        name = os.path.splitext(file)[0]
                        add_entry(apps, name, target, "start_menu")
    return apps


# ======================================================
# STEAM
# ======================================================

def parse_steam_libraryfolders(library_file):
    libraries = []
    if not os.path.isfile(library_file):
        return libraries

    try:
        with open(library_file, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        # Very naive parse: look for "path" "X:\SteamLibrary"
        for line in text.splitlines():
            line = line.strip()
            if '"path"' in line:
                parts = line.split('"')
                # e.g. "path" "D:\\SteamLibrary"
                if len(parts) >= 4:
                    path = parts[3].replace("\\\\", "\\")
                    libraries.append(path)
    except Exception:
        pass

    # Always include main Steam root
    root_common = os.path.join(STEAM_ROOT, "steamapps")
    if os.path.isdir(root_common) and root_common not in libraries:
        libraries.append(root_common)

    # Convert to steamapps paths
    final = []
    for lib in libraries:
        sa = os.path.join(lib, "steamapps")
        if os.path.isdir(sa):
            final.append(sa)
    return final


def parse_steam_acf(acf_path):
    """
    Very naive ACF parser: just enough to get appid, name, installdir.
    """
    data = {}
    try:
        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith('"appid"'):
                    parts = line.split('"')
                    if len(parts) >= 4:
                        data["appid"] = parts[3]
                elif line.startswith('"name"'):
                    parts = line.split('"')
                    if len(parts) >= 4:
                        data["name"] = parts[3]
                elif line.startswith('"installdir"'):
                    parts = line.split('"')
                    if len(parts) >= 4:
                        data["installdir"] = parts[3]
    except Exception:
        pass
    return data


def scan_steam():
    apps = []

    steamapps_root = os.path.join(STEAM_ROOT, "steamapps")
    library_file = os.path.join(steamapps_root, "libraryfolders.vdf")

    libraries = parse_steam_libraryfolders(library_file)
    if steamapps_root not in libraries and os.path.isdir(steamapps_root):
        libraries.append(steamapps_root)

    for lib in libraries:
        pattern = os.path.join(lib, "appmanifest_*.acf")
        for acf in glob.glob(pattern):
            meta = parse_steam_acf(acf)
            appid = meta.get("appid")
            name = meta.get("name")
            installdir = meta.get("installdir")
            if not appid or not name or not installdir:
                continue

            game_dir = os.path.join(lib, "common", installdir)
            alt_exe = find_primary_exe_in_folder(game_dir)
            steam_uri = f"steam://rungameid/{appid}"

            add_entry(apps, name, steam_uri, "steam", alt_exe=alt_exe)

    # Also add Steam client itself if present
    steam_exe = os.path.join(STEAM_ROOT, "steam.exe")
    if os.path.isfile(steam_exe):
        add_entry(apps, "Steam", steam_exe, "steam_client")

    return apps


# ======================================================
# EPIC GAMES
# ======================================================

def scan_epic():
    apps = []
    if not os.path.isdir(EPIC_MANIFEST_DIR):
        return apps

    for item_path in glob.glob(os.path.join(EPIC_MANIFEST_DIR, "*.item")):
        try:
            with open(item_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            continue

        name = data.get("DisplayName")
        install_location = data.get("InstallLocation")
        launch_exe = data.get("LaunchExecutable")
        app_name = data.get("AppName")

        if not name or not app_name:
            continue

        epic_uri = f"com.epicgames.launcher://apps/{app_name}?action=launch"

        alt_exe = None
        if install_location and launch_exe:
            candidate = os.path.join(install_location, launch_exe)
            if os.path.isfile(candidate) and not is_bad_exe(candidate):
                alt_exe = candidate
        elif install_location:
            alt_exe = find_primary_exe_in_folder(install_location)

        add_entry(apps, name, epic_uri, "epic", alt_exe=alt_exe)

    # Epic Games Launcher itself
    possible_paths = [
        r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        r"C:\Program Files (x86)\Epic Games\Launcher\Engine\Binaries\Win64\EpicGamesLauncher.exe"
    ]
    for p in possible_paths:
        if os.path.isfile(p):
            add_entry(apps, "Epic Games Launcher", p, "epic_client")
            break

    return apps


# ======================================================
# MICROSOFT STORE (APPX)
# ======================================================

def scan_appx():
    apps = []
    try:
        cmd = [
            "powershell",
            "-Command",
            "Get-AppxPackage | Select Name,PackageFamilyName | ConvertTo-Json"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if not result.stdout.strip():
            return apps

        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]

        for pkg in data:
            name = pkg.get("Name")
            fam = pkg.get("PackageFamilyName")
            if not name or not fam:
                continue
            exe = f"shell:AppsFolder\\{fam}!App"
            add_entry(apps, name, exe, "appx", alt_exe=None)

        return apps
    except Exception:
        return apps


# ======================================================
# PROGRAM FILES / APPDATA FALLBACK
# ======================================================

def scan_program_files():
    apps = []
    for base in PROGRAM_FILES_DIRS:
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                full = os.path.join(base, entry)
                if not os.path.isdir(full):
                    continue
                exe = find_primary_exe_in_folder(full)
                if exe and not is_bad_exe(exe):
                    add_entry(apps, entry, exe, "program_files")
        except Exception:
            continue
    return apps


def scan_appdata():
    apps = []
    for base in APPDATA_DIRS:
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                full = os.path.join(base, entry)
                if not os.path.isdir(full):
                    continue
                exe = find_primary_exe_in_folder(full)
                if exe and not is_bad_exe(exe):
                    add_entry(apps, entry, exe, "appdata")
        except Exception:
            continue
    return apps


# ======================================================
# MERGE + DEDUPE
# ======================================================

def merge_and_dedupe(*lists):
    merged = []
    seen = set()

    for lst in lists:
        for app in lst:
            key = (app["name"].lower(), app["exe"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(app)

    return merged


# ======================================================
# MAIN
# ======================================================

def scan_all():
    print("Scanning WinGet...")
    winget_apps = scan_winget()

    print("Scanning Registry...")
    reg_apps = scan_registry()

    print("Scanning Start Menu...")
    start_apps = scan_start_menu()

    print("Scanning Steam...")
    steam_apps = scan_steam()

    print("Scanning Epic...")
    epic_apps = scan_epic()

    print("Scanning Microsoft Store (AppX)...")
    appx_apps = scan_appx()

    print("Scanning Program Files...")
    pf_apps = scan_program_files()

    print("Scanning AppData...")
    ad_apps = scan_appdata()

    all_apps = merge_and_dedupe(
        winget_apps,
        reg_apps,
        start_apps,
        steam_apps,
        epic_apps,
        appx_apps,
        pf_apps,
        ad_apps
    )

    return all_apps


if __name__ == "__main__":
    apps = scan_all()
    print("\n=== FINAL APPS/GAMES ===\n")
    for app in apps:
        name = app["name"]
        exe = app["exe"]
        alt = app.get("alt_exe")
        src = app["source"]
        if alt:
            print(f"{src:12} | {name} -> {exe}  [alt: {alt}]")
        else:
            print(f"{src:12} | {name} -> {exe}")