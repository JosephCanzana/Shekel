import os
import sys
import logging
import threading
import time
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from zoneinfo import ZoneInfo 
from datetime import datetime

# ── Logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("shekel-agent.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ── Flask app ────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, origins=["*"])  # allow your web app to call this

PORT = 8765
COLS = 32

def wrap_words(text, width=COLS):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 <= width:
            current += (" " if current else "") + word
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines

def print_center_block(p, text):
    lines = wrap_words(text, COLS)
    for line in lines:
        p.text(line.center(COLS) + "\n")

# ── Printer helpers ──────────────────────────────────────────────
def get_printer():
    """
    Try USB first, fall back to Serial.
    Extend this later for Bluetooth.
    """
    # USB
    try:
        import usb.core
        from escpos.printer import Usb

        devices = list(usb.core.find(find_all=True))
        logger.info(f"USB scan found {len(devices)} device(s)")
        for d in devices:
            logger.info(f"  VID: {d.idVendor:04x}  PID: {d.idProduct:04x}")

        # Common POS58 VID/PID combos — extend as needed
        known = [
            (0x0fe6, 0x811e),
            (0x0416, 0x5011),
            (0x0483, 0x5743),
            (0x0519, 0x2013),
            (0x154f, 0x0520),
            (0x20d1, 0x7008),
        ]
        for vid, pid in known:
            dev = usb.core.find(idVendor=vid, idProduct=pid)
            if dev:
                logger.info(f"Found printer via USB: VID={vid:04x} PID={pid:04x}")
                try:
                    if dev.is_kernel_driver_active(0):
                        logger.info("Detaching kernel driver (usblp)...")
                        dev.detach_kernel_driver(0)
                except Exception as e:
                    logger.warning(f"Could not detach kernel driver: {e}")
                return Usb(vid, pid, profile="POS-5890")

    except Exception as e:
        logger.warning(f"USB probe failed: {e}")

    # Serial fallback
    try:
        import serial.tools.list_ports
        from escpos.printer import Serial

        ports = list(serial.tools.list_ports.comports())
        logger.info(f"Serial scan found {len(ports)} port(s)")
        for port in ports:
            logger.info(f"  {port.device} — {port.description}")
            if any(k in port.description.lower() for k in ["pos", "thermal", "printer", "usb serial"]):
                logger.info(f"Trying serial port: {port.device}")
                return Serial(port.device, baudrate=9600, profile="POS-5890")

    except Exception as e:
        logger.warning(f"Serial probe failed: {e}")

    raise RuntimeError("No printer found. Check USB connection and drivers.")


def rjust(left: str, right: str, width: int = COLS) -> str:
    gap = width - len(left) - len(right)
    return left + " " * max(gap, 1) + right


COLS = 32  # 58mm at normal font size

def do_print(receipt: dict):
    p = get_printer()

    try:
        # ── Reset printer to default state first ─────────────────
        p.hw('INIT')
        p.set(
            font='a',
            align='left',
            bold=False,
            underline=0,
            width=1,
            height=1,
            density=9,
        )

        # ── Header ───────────────────────────────────────────────
        p.set(align='center', bold=True, width=1, height=1)
        p.text("SHEKEL\n")
        p.set(align='center', bold=False, width=1, height=1)
        p.text("Sitio Kanto, Soledad, Sta. Rosa, N.E\n")
        p.text("-" * COLS + "\n")

        # ── Meta ─────────────────────────────────────────────────
        p.set(align='left', width=1, height=1)
        txn_id = int(receipt['transaction_id'])
        p.text(f"TXN#    : {txn_id:05d}\n")
        pht_now = datetime.now(ZoneInfo("Asia/Manila"))
        formatted_time = pht_now.strftime("%Y-%m-%d %I:%M %p")

        p.text(f"Date    : {formatted_time}\n")
        p.text(f"Cashier : {receipt['cashier'].title()}\n")
        p.text("-" * COLS + "\n")

        # ── Items ─────────────────────────────────────────────────
        for item in receipt["items"]:
            name = item["product_name"]
            if len(name) > COLS:
                name = name[:COLS - 1] + "."
            p.text(name + "\n")
            qty_price = f"  x{item['qty']} @ P{float(item['total_price']):.2f}"
            subtotal  = f"P{float(item['subtotal']):.2f}"
            p.text(rjust(qty_price, subtotal) + "\n")

        p.text("-" * COLS + "\n")

        # ── Totals ────────────────────────────────────────────────
        p.set(align='left', bold=True, width=1, height=1)
        p.text(rjust("TOTAL", f"P{float(receipt['total']):.2f}") + "\n")
        p.set(bold=False, width=1, height=1)
        p.text(rjust("Cash",   f"P{float(receipt['tendered']):.2f}") + "\n")
        p.text(rjust("Change", f"P{float(receipt['change']):.2f}")   + "\n")
        p.text("-" * COLS + "\n")

        # ── Footer ────────────────────────────────────────────
        p.set(align='center')
        p.text("\nThank you!\n")

        p.cut()

    finally:
        try:
            p.close()
        except Exception as e:
            logger.warning(f"Could not close printer: {e}")

# ── Routes ───────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    """Your web app pings this to check if the agent is running."""
    return jsonify({"ok": True, "agent": "shekel-print-agent", "version": "1.0.0"})


@app.route("/print", methods=["POST"])
def print_receipt():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "No data provided"}), 400

    try:
        do_print(data)
        logger.info(f"Printed TXN#{data.get('transaction_id','?')} OK")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Print failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/scan", methods=["GET"])
def scan_devices():
    """Utility route — lists all USB devices for debugging."""
    result = []
    try:
        import usb.core
        for d in usb.core.find(find_all=True):
            result.append({"vid": f"{d.idVendor:04x}", "pid": f"{d.idProduct:04x}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "devices": result})


# ── Entry point ──────────────────────────────────────────────────
def main():
    logger.info("=" * 40)
    logger.info("  Shekel Print Agent v1.0.0")
    logger.info(f"  Listening on http://localhost:{PORT}")
    logger.info("  Keep this window open while using Shekel")
    logger.info("=" * 40)
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()