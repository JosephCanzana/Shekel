# test_print.py — run with: docker compose exec web python test_print.py
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def get_printer():
    ptype = os.getenv("PRINTER_TYPE", "usb").lower()
    print(f"[config] PRINTER_TYPE={ptype}")

    if ptype == "usb":
        from escpos.printer import Usb
        vid = int(os.getenv("PRINTER_USB_VID", "0x0416"), 16)
        pid = int(os.getenv("PRINTER_USB_PID", "0x5011"), 16)
        in_ep  = int(os.getenv("PRINTER_USB_IN_EP",  "0x81"), 16)
        out_ep = int(os.getenv("PRINTER_USB_OUT_EP", "0x03"), 16)
        print(f"[config] VID=0x{vid:04x}  PID=0x{pid:04x}  IN=0x{in_ep:02x}  OUT=0x{out_ep:02x}")
        return Usb(vid, pid, in_ep=in_ep, out_ep=out_ep, profile="POS-5890")

    if ptype == "file":
        from escpos.printer import File
        path = os.getenv("PRINTER_FILE_PATH", "/dev/usb/lp0")
        print(f"[config] FILE={path}")
        return File(path, profile="POS-5890")

    if ptype == "serial":
        from escpos.printer import Serial
        port = os.getenv("PRINTER_SERIAL_PORT", "/dev/ttyUSB0")
        baud = int(os.getenv("PRINTER_SERIAL_BAUD", "9600"))
        print(f"[config] PORT={port}  BAUD={baud}")
        return Serial(port, baudrate=baud, profile="POS-5890")

    if ptype == "network":
        from escpos.printer import Network
        host = os.getenv("PRINTER_NETWORK_HOST", "192.168.1.100")
        port = int(os.getenv("PRINTER_NETWORK_PORT", "9100"))
        print(f"[config] HOST={host}  PORT={port}")
        return Network(host, port, profile="POS-5890")

    print(f"[error] Unknown PRINTER_TYPE: {ptype!r}")
    sys.exit(1)


def list_usb_devices():
    """List all USB devices visible to the container."""
    print("\n[usb] Scanning for USB devices...")
    try:
        import usb.core
        devices = list(usb.core.find(find_all=True))
        if not devices:
            print("[usb] No USB devices found at all — check volume/device mounts")
            return
        for d in devices:
            print(f"       VID: {d.idVendor:04x}  PID: {d.idProduct:04x}")
    except Exception as e:
        print(f"[usb] Could not scan USB: {e}")


def main():
    print("=" * 40)
    print("  POS58 Printer Test")
    print("=" * 40)

    # Always show what USB devices are visible first
    list_usb_devices()

    print("\n[test] Connecting to printer...")
    try:
        p = get_printer()
    except Exception as e:
        print(f"\n[FAIL] Could not connect: {e}")
        print("\nCommon fixes:")
        print("  NoBackendError  → libusb not installed in container, or /dev/bus/usb not mounted")
        print("  No such device  → wrong VID/PID in .env")
        print("  Access denied   → missing udev rule or user not in plugdev group")
        print("  Pipe error      → wrong IN/OUT endpoints, run find_printer.py to check")
        sys.exit(1)

    print("[test] Connected. Printing test page...")
    try:
        COLS = 32

        # Header
        p.set(align="center", bold=True, double_height=True, double_width=True)
        p.text("SHEKEL\n")
        p.set(align="center", bold=False, double_height=False, double_width=False)
        p.text("Printer Test Page\n")
        p.text("-" * COLS + "\n")

        # Connection info
        p.set(align="left")
        p.text(f"Type : {os.getenv('PRINTER_TYPE','usb').upper()}\n")
        p.text(f"VID  : {os.getenv('PRINTER_USB_VID','0x0416')}\n")
        p.text(f"PID  : {os.getenv('PRINTER_USB_PID','0x5011')}\n")
        p.text("-" * COLS + "\n")

        # Formatting test
        p.set(align="left", bold=True)
        p.text("Bold text\n")
        p.set(bold=False)
        p.text("Normal text\n")
        p.set(underline=1)
        p.text("Underlined text\n")
        p.set(underline=0)
        p.text("-" * COLS + "\n")

        # Alignment test
        p.set(align="left");   p.text("Left aligned\n")
        p.set(align="center"); p.text("Center aligned\n")
        p.set(align="right");  p.text("Right aligned\n")
        p.text("-" * COLS + "\n")

        # Receipt simulation
        p.set(align="left")
        p.text(f"{'Sample Item A':<20}{'P25.00':>12}\n")
        p.text(f"{'Sample Item B':<20}{'P50.00':>12}\n")
        p.text(f"{'Sample Item C':<20}{'P15.00':>12}\n")
        p.text("-" * COLS + "\n")
        p.set(bold=True)
        p.text(f"{'TOTAL':<20}{'P90.00':>12}\n")
        p.set(bold=False)
        p.text(f"{'Cash':<20}{'P100.00':>12}\n")
        p.text(f"{'Change':<20}{'P10.00':>12}\n")
        p.text("-" * COLS + "\n")

        # Footer
        p.set(align="center")
        p.text("\nTest complete!\n")
        p.text("If you can read this,\n")
        p.text("your printer is working.\n\n\n")

        p.cut()

        print("[OK] Test page printed successfully.")

    except Exception as e:
        print(f"\n[FAIL] Printer connected but printing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()