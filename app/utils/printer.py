# printer.py
from escpos.printer import Usb
import logging

# Replace with YOUR actual IDs from lsusb
VENDOR_ID  = 0x0416
PRODUCT_ID = 0x5011
IN_EP      = 0x81
OUT_EP     = 0x03

def get_printer():
    try:
        return Usb(VENDOR_ID, PRODUCT_ID, in_ep=IN_EP, out_ep=OUT_EP)
    except Exception as e:
        logging.error(f"Printer connection failed: {e}")
        return None

def print_receipt(receipt: dict):
    p = get_printer()
    if not p:
        return False
    try:
        p.set(align='center')
        p.text("DUDAY\n")
        p.text("Your Store Address\n")
        p.text("Tel: 09XX-XXX-XXXX\n")
        p.text("-" * 32 + "\n")

        p.set(align='left')
        p.text(f"TXN#: {receipt['transaction_id']}\n")
        p.text(f"Date: {receipt['datetime']}\n")
        p.text(f"Cashier: {receipt['cashier']}\n")
        p.text("-" * 32 + "\n")

        for item in receipt['items']:
            name = item['product_name'][:20]  # truncate for 58mm
            subtotal = f"P{item['subtotal']:.2f}"
            line = f"{name:<20} {subtotal:>10}\n"
            p.text(line)
            p.text(f"  x{item['qty']} @ P{item['total_price']:.2f}\n")

        p.text("-" * 32 + "\n")
        p.text(f"{'TOTAL':<20} {'P'+str(f\"{receipt['total']:.2f}\"):>10}\n")
        p.text(f"{'Cash':<20} {'P'+str(f\"{receipt['tendered']:.2f}\"):>10}\n")
        p.text(f"{'Change':<20} {'P'+str(f\"{receipt['change']:.2f}\"):>10}\n")
        p.text("-" * 32 + "\n")

        p.set(align='center')
        p.text("\nThank you for your purchase!\n")
        p.text("Please come again.\n\n\n")
        p.cut()
        return True
    except Exception as e:
        logging.error(f"Print failed: {e}")
        return False