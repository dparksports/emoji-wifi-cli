#!/usr/bin/env python3
"""
emoji-wifi-cli — Ubuntu CLI port of EmojiWifi (macOS)
======================================================
Features:
  • Generate emoji-based WiFi SSIDs (single, combo, random, or custom)
  • Generate strong WPA3-compatible passwords (8-63 chars)
  • Display WiFi QR code directly in the terminal (Unicode block chars)
  • Copy SSID / password to clipboard (xclip / xsel / wl-copy)
  • Persistent history of generated networks (JSON file)
  • Auto-join: connect to a generated network via nmcli
  • Scan a WiFi QR image file (via zxingcpp if available)
"""

import os
import sys
import json
import secrets
import string
import datetime
import subprocess
import textwrap
import re
from pathlib import Path

# ── optional deps ────────────────────────────────────────────────────────────
try:
    import emoji as _emoji_mod
    EMOJI_DATA = list(_emoji_mod.EMOJI_DATA.keys())
    SINGLE_EMOJIS = [c for c in EMOJI_DATA if len(c) == 1 and c not in ['️', '⃣']]
except ImportError:
    SINGLE_EMOJIS = ["📶", "🏠", "💻", "📱", "🔒", "🌐", "🚀", "✨", "🔑", "🛡️"]

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    import zxingcpp
    from PIL import Image as PILImage
    HAS_ZXING = True
except ImportError:
    HAS_ZXING = False

# ── ANSI helpers ─────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
MAGENTA= "\033[95m"
RED    = "\033[91m"
WHITE  = "\033[97m"
BG_DARK= "\033[48;5;235m"

def c(text, *codes): return "".join(codes) + str(text) + RESET
def banner():
    print(c("╔══════════════════════════════════════════════════╗", CYAN, BOLD))
    print(c("║  📶  EmojiWifi CLI  —  Ubuntu Edition  📶        ║", CYAN, BOLD))
    print(c("╚══════════════════════════════════════════════════╝", CYAN, BOLD))
    print()

def hr(label=""):
    w = 52
    if label:
        side = (w - len(label) - 2) // 2
        print(c("─" * side + f" {label} " + "─" * side, DIM))
    else:
        print(c("─" * w, DIM))

def menu_item(key, desc):
    print(f"  {c(key, YELLOW, BOLD)}  {desc}")

# ── Clipboard ────────────────────────────────────────────────────────────────
def copy_to_clipboard(text: str) -> bool:
    """Try xclip → xsel → wl-copy → pbcopy in order."""
    for cmd in [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["wl-copy"],
        ["pbcopy"],
    ]:
        try:
            r = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=3)
            if r.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False

# ── Password generator ───────────────────────────────────────────────────────
SPECIAL = "!@$%^&*()-_=+[]{}|<>?~"

def generate_password(length: int = 60) -> str:
    length = max(8, min(63, length))
    sets = [string.ascii_lowercase, string.ascii_uppercase, string.digits, SPECIAL]
    while True:
        pw = [secrets.choice(s) for s in sets]
        all_chars = "".join(sets)
        pw += [secrets.choice(all_chars) for _ in range(length - len(pw))]
        secrets.SystemRandom().shuffle(pw)
        pw = "".join(pw)
        if (any(c.islower() for c in pw) and
            any(c.isupper() for c in pw) and
            any(c.isdigit() for c in pw) and
            any(not c.isalnum() for c in pw)):
            return pw

# ── QR code in terminal ──────────────────────────────────────────────────────
def make_wifi_qr_string(ssid: str, password: str) -> str:
    """Return the WIFI: URI string for a QR code."""
    pwd_escaped = password.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace('"', '\\"')
    ssid_escaped = ssid.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace('"', '\\"')
    return f"WIFI:S:{ssid_escaped};T:WPA;P:{pwd_escaped};;"

def print_qr(ssid: str, password: str, module_size: int = 1):
    if not HAS_QRCODE:
        print(c("  ⚠  Install 'qrcode' package for QR display: pip install qrcode[pil]", YELLOW))
        return

    data = make_wifi_qr_string(ssid, password)
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    # Render using half-block characters (▄ ▀ █ space)
    # Each pair of rows → one terminal row
    lines = []
    rows = len(matrix)
    for row_idx in range(0, rows, 2):
        top_row = matrix[row_idx]
        bot_row = matrix[row_idx + 1] if row_idx + 1 < rows else [False] * len(top_row)
        line = ""
        for top, bot in zip(top_row, bot_row):
            if top and bot:
                line += "█"
            elif top and not bot:
                line += "▀"
            elif not top and bot:
                line += "▄"
            else:
                line += " "
        lines.append(line)

    # Centre-pad and print with a surrounding box
    max_w = max(len(l) for l in lines)
    pad = 2
    print()
    print(c("  ┌" + "─" * (max_w + pad * 2) + "┐", CYAN))
    for line in lines:
        print(c("  │" + " " * pad + line + " " * (max_w - len(line)) + " " * pad + "│", CYAN))
    print(c("  └" + "─" * (max_w + pad * 2) + "┘", CYAN))
    print()

# ── History ──────────────────────────────────────────────────────────────────
HISTORY_FILE = Path.home() / ".emoji_wifi_history.json"

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []

def save_history(history: list):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))

def add_to_history(ssid: str, password: str, history: list) -> list:
    entry = {
        "ssid": ssid,
        "password": password,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    # deduplicate by ssid
    history = [h for h in history if h.get("ssid") != ssid]
    history.insert(0, entry)
    return history[:50]  # keep last 50

# ── SSID sources ─────────────────────────────────────────────────────────────
COMBOS_FILE = Path(__file__).parent / "combos.csv"
SINGLE_FILE = Path(__file__).parent / "single.csv"

def load_combos() -> list[dict]:
    combos = []
    if COMBOS_FILE.exists():
        for line in COMBOS_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) >= 2:
                combos.append({"name": parts[0].lstrip('"'), "emojis": parts[1].rstrip('"')})
    return combos

def load_singles() -> list[dict]:
    singles = []
    if SINGLE_FILE.exists():
        for line in SINGLE_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) >= 2:
                singles.append({"emoji": parts[0].lstrip('"'), "desc": parts[1].rstrip('"')})
    return singles

# ── nmcli auto-join ──────────────────────────────────────────────────────────
def list_wifi_interfaces() -> list[str]:
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            text=True, stderr=subprocess.DEVNULL
        )
        return [line.split(":")[0] for line in out.splitlines() if ":wifi" in line]
    except Exception:
        return []

def auto_join(ssid: str, password: str) -> bool:
    """Create a hotspot / connect to a network with the given SSID+password via nmcli."""
    ifaces = list_wifi_interfaces()
    if not ifaces:
        print(c("  ✗ No WiFi interfaces found.", RED))
        return False

    print(f"\n  {c('Available interfaces:', DIM)}", ", ".join(ifaces))
    iface = ifaces[0]
    print(f"  Using interface: {c(iface, CYAN)}")
    print(f"  Creating / connecting to: {c(ssid, YELLOW)} ...")

    # Try to create a new hotspot (access point) profile
    cmd = [
        "nmcli", "device", "wifi", "hotspot",
        "ifname", iface,
        "ssid", ssid,
        "password", password,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(c(f"\n  ✓ Hotspot '{ssid}' created successfully!", GREEN, BOLD))
            print(c(f"  Password: {password}", DIM))
            return True
        else:
            # Fall back: try to connect to an existing network
            print(c(f"  Hotspot creation failed (may need root): {result.stderr.strip()}", YELLOW))
            cmd2 = ["nmcli", "device", "wifi", "connect", ssid, "password", password, "ifname", iface]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
            if result2.returncode == 0:
                print(c(f"\n  ✓ Connected to '{ssid}'!", GREEN, BOLD))
                return True
            print(c(f"  ✗ Failed: {result2.stderr.strip()}", RED))
            return False
    except subprocess.TimeoutExpired:
        print(c("  ✗ nmcli timed out.", RED))
        return False
    except Exception as e:
        print(c(f"  ✗ Error: {e}", RED))
        return False

# ── QR scan from image file ──────────────────────────────────────────────────
def parse_wifi_qr_string(text: str) -> dict | None:
    if not text.startswith("WIFI:"):
        return None
    text = text[5:]
    parts = re.split(r'(?<!\\);', text)
    result = {}
    for p in parts:
        if p.startswith("S:"):  result["ssid"]     = p[2:]
        elif p.startswith("P:"): result["password"] = p[2:]
        elif p.startswith("T:"): result["type"]     = p[2:]
    return result if "ssid" in result else None

def scan_qr_image(path: str) -> dict | None:
    if not HAS_ZXING:
        print(c("  ⚠  zxingcpp not installed. Install with: pip install zxingcpp pillow", YELLOW))
        return None
    try:
        img = PILImage.open(path)
        import numpy as np
        results = zxingcpp.read_barcodes(np.array(img))
        if not results:
            print(c("  ✗ No QR code found in image.", RED))
            return None
        return parse_wifi_qr_string(results[0].text)
    except Exception as e:
        print(c(f"  ✗ Error reading image: {e}", RED))
        return None

# ── UI helpers ───────────────────────────────────────────────────────────────
def ask(prompt: str, default: str = "") -> str:
    try:
        val = input(f"  {c('▶', CYAN)} {prompt}" + (f" [{c(default, DIM)}]" if default else "") + ": ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        return default

def confirm(prompt: str) -> bool:
    ans = ask(f"{prompt} [y/N]", "n")
    return ans.lower() in ("y", "yes")

def print_network_card(ssid: str, password: str):
    print()
    print(c("  ╔════════════════════════════════════════════════════════════════════════╗", CYAN))
    print(c("  ║  ", CYAN) + c("WiFi Network Details                                                    ", BOLD, WHITE) + c("║", CYAN))
    print(c("  ╠════════════════════════════════════════════════════════════════════════╣", CYAN))
    ssid_disp = ssid[:60]
    print(c("  ║  SSID:  ", CYAN) + c(f"{ssid_disp:<60}", YELLOW, BOLD) + c("  ║", CYAN))
    print(c("  ║  Pass:  ", CYAN) + c(f"{password:<60}", GREEN) + c("  ║", CYAN))
    print(c("  ╚════════════════════════════════════════════════════════════════════════╝", CYAN))

# ── Sub-menus ────────────────────────────────────────────────────────────────
def choose_ssid_menu(combos, singles) -> str | None:
    print()
    hr("Choose SSID Type")
    menu_item("1", "Random single emoji (from full emoji set)")
    menu_item("2", "Pick from curated single emojis list")
    menu_item("3", "Pick from themed combo (emoji + name)")
    menu_item("4", "Enter custom WiFi name")
    menu_item("b", "Back")
    choice = ask("Select")
    if choice == "1":
        emoji_char = secrets.choice(SINGLE_EMOJIS)
        print(f"\n  Generated: {c(emoji_char, YELLOW, BOLD)}")
        return emoji_char
    elif choice == "2":
        if not singles:
            print(c("  singles.csv not found.", RED))
            return None
        print()
        for i, s in enumerate(singles, 1):
            print(f"  {c(str(i).rjust(2), DIM)}  {s['emoji']}  {c(s['desc'], DIM)}")
        num = ask("Enter number", "1")
        try:
            idx = int(num) - 1
            return singles[idx % len(singles)]["emoji"]
        except (ValueError, IndexError):
            return singles[0]["emoji"]
    elif choice == "3":
        if not combos:
            print(c("  combos.csv not found.", RED))
            return None
        print()
        for i, c_ in enumerate(combos, 1):
            print(f"  {c(str(i).rjust(2), DIM)}  {c_['emojis']}  {c(c_['name'], DIM)}")
        num = ask("Enter number (or Enter for random)", "")
        try:
            idx = int(num) - 1 if num else secrets.randbelow(len(combos))
            combo = combos[idx % len(combos)]
            return combo["emojis"]
        except (ValueError, IndexError):
            return combos[0]["emojis"]
    elif choice == "4":
        name = ask("WiFi name")
        return name if name else None
    return None

def history_menu(history: list, combos, singles):
    if not history:
        print(c("\n  No history yet.", DIM))
        return history

    print()
    hr("History  (most recent first)")
    for i, h in enumerate(history, 1):
        ts = h.get("created", "")[:16].replace("T", " ")
        print(f"  {c(str(i).rjust(2), DIM)}  {c(h['ssid'], YELLOW)}  {c(ts, DIM)}")

    print()
    menu_item("n", "Load a network from history")
    menu_item("d", "Delete a history entry")
    menu_item("c", "Clear all history")
    menu_item("b", "Back")
    choice = ask("Select")

    if choice == "n":
        num = ask("Enter number")
        try:
            idx = int(num) - 1
            h = history[idx]
            ssid, password = h["ssid"], h["password"]
            print_network_card(ssid, password)
            print_qr(ssid, password)
            network_actions(ssid, password, history, combos, singles, add_hist=False)
        except (ValueError, IndexError):
            print(c("  Invalid selection.", RED))
    elif choice == "d":
        num = ask("Enter number to delete")
        try:
            idx = int(num) - 1
            removed = history.pop(idx)
            print(c(f"  Deleted: {removed['ssid']}", DIM))
            save_history(history)
        except (ValueError, IndexError):
            print(c("  Invalid selection.", RED))
    elif choice == "c":
        if confirm("Clear all history?"):
            history.clear()
            save_history(history)
            print(c("  History cleared.", DIM))
    return history

def password_length_menu() -> int:
    print()
    hr("Password Length")
    print(f"  Current default: {c('60', YELLOW)} characters  (range: 8–63)")
    val = ask("Enter length", "60")
    try:
        return max(8, min(63, int(val)))
    except ValueError:
        return 60

def network_actions(ssid: str, password: str, history: list, combos, singles, pw_len: int = 60, add_hist: bool = True):
    """Actions once a network is generated: copy, join, regenerate pw, etc."""
    if add_hist:
        history = add_to_history(ssid, password, history)
        save_history(history)

    while True:
        print()
        hr("Actions")
        menu_item("c", f"Copy SSID to clipboard   ({c(ssid, YELLOW)})")
        menu_item("p", f"Copy password to clipboard")
        menu_item("q", "Show QR code again")
        menu_item("r", "Regenerate password (keep SSID)")
        menu_item("j", "Auto-join / create hotspot via nmcli")
        menu_item("n", "Generate a completely new network")
        menu_item("b", "Back to main menu")
        choice = ask("Select")

        if choice == "c":
            if copy_to_clipboard(ssid):
                print(c(f"  ✓ SSID copied!", GREEN))
            else:
                print(c(f"  ✗ Clipboard unavailable. Install xclip or xsel.", RED))
                print(f"  SSID: {c(ssid, YELLOW)}")
        elif choice == "p":
            if copy_to_clipboard(password):
                print(c(f"  ✓ Password copied!", GREEN))
            else:
                print(c(f"  ✗ Clipboard unavailable.", RED))
                print(f"  Password: {c(password, GREEN)}")
        elif choice == "q":
            print_qr(ssid, password)
        elif choice == "r":
            length = password_length_menu()
            password = generate_password(length)
            print_network_card(ssid, password)
            print_qr(ssid, password)
            history = add_to_history(ssid, password, history)
            save_history(history)
        elif choice == "j":
            auto_join(ssid, password)
        elif choice == "n":
            break
        elif choice in ("b", ""):
            break

    return history

def scan_menu(history: list, combos, singles):
    print()
    hr("Scan WiFi QR Code from Image")
    path = ask("Image file path (PNG/JPG)")
    if not path or not Path(path).exists():
        print(c("  ✗ File not found.", RED))
        return history
    wifi = scan_qr_image(path)
    if wifi:
        ssid = wifi.get("ssid", "")
        password = wifi.get("password", "")
        print(c(f"\n  ✓ QR code scanned!", GREEN, BOLD))
        print_network_card(ssid, password)
        print_qr(ssid, password)
        history = network_actions(ssid, password, history, combos, singles)
    return history

# ── Main loop ────────────────────────────────────────────────────────────────
def main():
    os.system("clear")
    banner()

    combos  = load_combos()
    singles = load_singles()
    history = load_history()
    pw_len  = 60

    while True:
        hr("Main Menu")
        menu_item("1", "Generate new WiFi network  🚀")
        menu_item("2", "History                    📋")
        menu_item("3", "Scan QR code from image    📷")
        menu_item("4", f"Password length            🔐  (current: {c(str(pw_len), YELLOW)})")
        menu_item("q", "Quit")
        print()
        choice = ask("Select")

        if choice == "1":
            ssid = choose_ssid_menu(combos, singles)
            if ssid:
                password = generate_password(pw_len)
                os.system("clear")
                banner()
                print_network_card(ssid, password)
                print_qr(ssid, password)
                history = network_actions(ssid, password, history, combos, singles, pw_len)
                os.system("clear")
                banner()
        elif choice == "2":
            history = history_menu(history, combos, singles)
        elif choice == "3":
            history = scan_menu(history, combos, singles)
        elif choice == "4":
            pw_len = password_length_menu()
        elif choice in ("q", "quit", "exit"):
            print(c("\n  Bye! 📶\n", CYAN, BOLD))
            sys.exit(0)
        print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(c("\n\n  Interrupted. Bye! 📶\n", CYAN))
        sys.exit(0)
