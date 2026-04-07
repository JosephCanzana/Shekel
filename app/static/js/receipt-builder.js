// ── ESC/POS constants ─────────────────────────────────────────────────────
const ESC = '\x1B', GS = '\x1D'

const P = {
    INIT:         ESC + '@',
    LEFT:         ESC + 'a\x00',
    CENTER:       ESC + 'a\x01',
    RIGHT:        ESC + 'a\x02',
    BOLD_ON:      ESC + 'E\x01',
    BOLD_OFF:     ESC + 'E\x00',
    DOUBLE_ON:    ESC + '!\x30',   // double width + height
    DOUBLE_OFF:   ESC + '!\x00',
    CUT:          GS  + 'V\x41\x03',
    LF:           '\n',
    DIV:          '--------------------------------\n',  // 32 chars
}

// ── Helpers ───────────────────────────────────────────────────────────────
function rpad(label, value, width = 32) {
    const gap = width - label.length - value.length
    return label + ' '.repeat(Math.max(1, gap)) + value + '\n'
}

function money(n) {
    return '₱' + parseFloat(n).toFixed(2)
}

// Wrap text to 32 chars
function wrap(text, width = 32) {
    const words = text.split(' ')
    let lines = [], line = ''
    for (const w of words) {
        if ((line + w).length > width) { lines.push(line.trimEnd()); line = '' }
        line += w + ' '
    }
    if (line.trim()) lines.push(line.trimEnd())
    return lines.join('\n') + '\n'
}

// ── Main builder — matches your /api/charge response shape ────────────────
function buildReceipt(r, storeName = 'Duday', storeAddress = '') {
    // r = { transaction_id, cashier, datetime, items, total, tendered, change, warnings }
    let c = []

    c.push(P.INIT)

    // Header
    c.push(P.CENTER)
    c.push(P.BOLD_ON + P.DOUBLE_ON)
    c.push(storeName + '\n')
    c.push(P.DOUBLE_OFF + P.BOLD_OFF)
    if (storeAddress) c.push(storeAddress + '\n')
    c.push('\n')

    // Transaction meta
    c.push(P.LEFT)
    c.push(P.DIV)
    c.push(rpad('TXN #:', String(r.transaction_id)))
    c.push(rpad('Date :', r.datetime))
    c.push(rpad('By   :', r.cashier))
    c.push(P.DIV)

    // Column header
    c.push('ITEM                  QTY    TOTAL\n')
    c.push(P.DIV)

    // Line items
    for (const item of r.items) {
        const name = item.product_name.substring(0, 32)
        // If name fits on one line with qty + total, keep it compact
        const qtyStr   = `x${item.qty}`
        const totalStr = money(item.subtotal)
        const namePad  = 21
        if (name.length <= namePad) {
            const row = name.padEnd(namePad)
                      + qtyStr.padStart(5)
                      + totalStr.padStart(8)
            c.push(row + '\n')
        } else {
            // Long name: wrap onto its own line, then qty + total
            c.push(wrap(name))
            c.push(' '.repeat(21) + qtyStr.padStart(5) + totalStr.padStart(8) + '\n')
        }
    }

    c.push(P.DIV)

    // Totals
    c.push(P.BOLD_ON)
    c.push(rpad('TOTAL :', money(r.total)))
    c.push(P.BOLD_OFF)
    c.push(rpad('Cash  :', money(r.tendered)))
    c.push(rpad('Change:', money(r.change)))
    c.push(P.DIV)

    // Warnings (stock issues)
    if (r.warnings && r.warnings.length) {
        c.push(P.CENTER)
        for (const w of r.warnings) c.push(wrap('! ' + w))
        c.push(P.LEFT)
        c.push(P.DIV)
    }

    // Footer
    c.push(P.CENTER)
    c.push('\nThank you!\nPlease come again.\n\n\n')
    c.push(P.CUT)

    return c
}