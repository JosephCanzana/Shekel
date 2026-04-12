#!/bin/bash
# Shekel Print Agent — Linux Setup
# Run once: bash setup-linux.sh

set -e

echo "========================================"
echo "  Shekel Print Agent - Linux Setup"
echo "========================================"
echo ""

# ── Check not running as root ────────────────────────────────────
if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Do not run as root. Run as your normal user."
    echo "The script will ask for sudo when needed."
    exit 1
fi

# ── Detect distro ────────────────────────────────────────────────
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    DISTRO="unknown"
fi
echo "[1/6] Detected distro: $DISTRO"

# ── Install libusb ───────────────────────────────────────────────
echo "[2/6] Installing libusb..."
case $DISTRO in
    ubuntu|debian|linuxmint|pop)
        sudo apt-get update -q && sudo apt-get install -y libusb-1.0-0
        ;;
    arch|manjaro|endeavouros)
        sudo pacman -Sy --noconfirm libusb
        ;;
    fedora|rhel|centos)
        sudo dnf install -y libusb1
        ;;
    opensuse*)
        sudo zypper install -y libusb-1_0-0
        ;;
    *)
        echo "  Unknown distro — skipping libusb install."
        echo "  Install libusb manually if printing fails."
        ;;
esac

# ── Blacklist usblp ──────────────────────────────────────────────
echo "[3/6] Blacklisting usblp kernel module..."
echo "blacklist usblp" | sudo tee /etc/modprobe.d/blacklist-usblp.conf > /dev/null
sudo rmmod usblp 2>/dev/null && echo "  usblp unloaded." || echo "  usblp was not loaded (OK)."
sudo depmod -a

# ── udev rule ────────────────────────────────────────────────────
echo "[4/6] Creating udev rule..."

# Try to detect VID/PID automatically
VID=""
PID=""
if command -v lsusb &>/dev/null; then
    # Common POS58 VID/PIDs
    for combo in "0fe6:811e" "0416:5011" "0483:5743" "0519:2013" "154f:0520" "20d1:7008"; do
        v=$(echo $combo | cut -d: -f1)
        p=$(echo $combo | cut -d: -f2)
        if lsusb | grep -qi "$v:$p"; then
            VID=$v
            PID=$p
            echo "  Found printer: VID=$VID PID=$PID"
            break
        fi
    done
fi

if [ -z "$VID" ]; then
    echo "  Printer not detected automatically."
    echo "  Available USB devices:"
    lsusb
    echo ""
    read -p "  Enter VID (e.g. 0fe6): " VID
    read -p "  Enter PID (e.g. 811e): " PID
fi

sudo tee /etc/udev/rules.d/99-pos58.rules > /dev/null <<EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="$VID", ATTRS{idProduct}=="$PID", MODE="0666", GROUP="plugdev"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
echo "  udev rule created for $VID:$PID"

# ── plugdev group ────────────────────────────────────────────────
echo "[5/6] Adding user to plugdev group..."
sudo groupadd -f plugdev
sudo usermod -aG plugdev "$USER"
echo "  Added $USER to plugdev."

# ── Auto-start via systemd ───────────────────────────────────────
echo "[6/6] Setting up auto-start..."
AGENT_PATH="$(cd "$(dirname "$0")/.." && pwd)/dist/shekel-agent"

if [ ! -f "$AGENT_PATH" ]; then
    echo "  WARNING: Binary not found at $AGENT_PATH"
    echo "  Run 'python build.py' first to build the agent."
else
    mkdir -p ~/.config/systemd/user
    cat > ~/.config/systemd/user/shekel-agent.service <<EOF
[Unit]
Description=Shekel Print Agent
After=network.target

[Service]
ExecStart=$AGENT_PATH
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable shekel-agent
    systemctl --user start shekel-agent
    echo "  Auto-start enabled."
    echo "  Status: $(systemctl --user is-active shekel-agent)"
fi

echo ""
echo "========================================"
echo "  Setup complete!"
echo ""
echo "  IMPORTANT: You must log out and"
echo "  log back in for group changes to"
echo "  take effect."
echo ""
echo "  After logging back in, the agent"
echo "  will start automatically."
echo "========================================"