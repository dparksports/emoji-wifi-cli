# emoji-wifi-cli 📶

An interactive command-line application for Ubuntu to instantly generate WiFi names (SSIDs) and passwords based on Emojis. Features an interactive terminal interface, QR code display, clipboard integration, network history, and auto-joining using `nmcli`.

This is an Ubuntu CLI port of [EmojiWifi (macOS)](https://github.com/dparksports/emoji-wifi-mac).

---

## ✨ Features

- **Emoji-Based SSIDs**: Generate WiFi names using random emojis, curated single emojis, or themed emoji combos (e.g., "Gaming Hub" 🎮🎵🎧).
- **Strong Passwords**: Generate WPA3-compliant passwords (8–63 characters, default 60) excluding easily confused or problematic characters like `:,;\`'.,/`.
- **In-Terminal QR Code**: Displays a scannable QR code directly in the terminal using Unicode blocks for easy mobile connection.
- **Clipboard Integration**: Instantly copy SSID or Password to clipboard (supports `xclip`, `xsel`, `wl-copy`, and `pbcopy`).
- **Persistent History**: Keeps a local log of up to 50 previously generated networks (stored in `~/.emoji_wifi_history.json`).
- **Auto-Join / Hotspot**: Uses `nmcli` to automatically spin up a local hotspot or connect to the generated network on Ubuntu.
- **QR Code Scanning**: Scan a WiFi QR code from a local image file (PNG/JPG) using `zxingcpp` and import it directly.

---

## 🚀 Getting Started

### Prerequisites

You need Python 3 installed. Make sure you install the required dependencies:

```bash
pip install emoji qrcode[pil] pyperclip
```

*(Optional)* If you want to scan QR code images:
```bash
pip install zxingcpp pillow
```

### Installation

1. Clone or download this folder.
2. Make the script executable:
   ```bash
   chmod +x emoji_wifi_cli.py
   ```

### Usage

Run the script interactively:
```bash
./emoji_wifi_cli.py
```

Follow the on-screen options to generate networks, view histories, copy credentials, or automatically set up your WiFi interface.

---

## 🛠️ Files

- `emoji_wifi_cli.py`: The main Python application script.
- `combos.csv`: Themed emoji-name combinations.
- `single.csv`: Curated single emojis and their descriptions.

---

## 📜 License

Apache License 2.0. Feel free to use and modify it!
