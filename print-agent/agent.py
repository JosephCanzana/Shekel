import sys
import os
import logging
import platform
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("shekel-agent.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])

PORT = 8765
COLS = 32


def rjust(left: str, right: str, width: int = COLS) -> str:
    gap = width - len(left) - len(right)
    return left + " " * max(gap, 1) + right


def get_printer_windows():
    """Use Windows printing API — no libusb or Zadig needed."""
    import win32print
    from escpos.printer import Win32Raw

    # Find the POS printer automatically
    printers = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )

    logger.info(f"Found {len(printers)} printer(s) on Windows:")
    for p in printers:
        logger.info(f"  {p[2]}")

    # Try to find POS/thermal printer automatically
    pos_keywords = ["pos", "thermal", "receipt", "xprinter", "58", "80", "shekel"]
    for p in printers:
        name = p[2].lower()
        if any(k in name for k in pos_keywords):
            logger.info(f"Auto-selected printer: {p[2]}")
            return Win32Raw(p[2])

    # Fall back to default printer
    default = win32print.GetDefaultPrinter()
    logger.info(f"No POS printer found, using default: {default}")
    return Win32Raw(default)


def get_printer_unix():
    """Use USB directly on Linux/macOS."""
    import usb.core
    from escpos.printer import Usb

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
            logger.info(f"Found printer: VID={vid:04x} PID={pid:04x}")
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass
            return Usb(vid, pid, profile="POS-5890")

    raise RuntimeError("No printer found. Check USB connection.")


def get_printer():
    if platform.system() == "Windows":
        return get_printer_windows()
    return get_printer_unix()


def do_print(receipt: dict):
    p = get_printer()

    try:
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
        p.text("DUDAY'S GROCERY STORE\n")
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

        # Items
        for item in receipt["items"]:
            name = item["product_name"]
            if len(name) > COLS:
                name = name[:COLS - 1] + "."
            p.text(name + "\n")
            qty_price = f"  x{item['qty']} @ P{float(item['total_price']):.2f}"
            subtotal  = f"P{float(item['subtotal']):.2f}"
            p.text(rjust(qty_price, subtotal) + "\n")

        p.text("-" * COLS + "\n")

        # Totals
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
    return jsonify({"ok": True, "agent": "shekel-print-agent", "version": "1.0.0"})


@app.route("/print", methods=["POST"])
def print_receipt():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "No data provided"}), 400
    try:
        do_print(data)
        logger.info(f"Printed TXN#{data.get('transaction_id', '?')} OK")
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Print failed: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/scan", methods=["GET"])
def scan_devices():
    result = []
    if platform.system() == "Windows":
        import win32print
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        result = [{"name": p[2]} for p in printers]
        return jsonify({"ok": True, "printers": result})
    else:
        try:
            import usb.core
            for d in usb.core.find(find_all=True):
                result.append({"vid": f"{d.idVendor:04x}", "pid": f"{d.idProduct:04x}"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "devices": result})


def main():
    logger.info("=" * 40)
    logger.info("  Shekel Print Agent v1.0.0")
    logger.info(f"  Platform: {platform.system()}")
    logger.info(f"  Listening on http://localhost:{PORT}")
    logger.info("  Keep this window open while using Shekel")
    logger.info("=" * 40)
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()