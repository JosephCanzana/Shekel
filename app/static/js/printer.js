// ── QZ Security (dev mode) ─────────────────────────────
qz.security.setCertificatePromise(resolve => resolve('-----EMPTY-----'))
qz.security.setSignatureAlgorithm('SHA512')
qz.security.setSignaturePromise(hash => new Promise(resolve => resolve('')))

// ── Printer Store ──────────────────────────────────────
function printerStore() {
    return {
        connected: false,
        printerName: null,
        availablePrinters: [],
        status: 'Disconnected',

        async connect() {
            try {
                if (qz.websocket.isActive()) {
                    this.connected = true
                    this.status = 'Connected'
                    await this.loadPrinters()
                    return
                }
                await qz.websocket.connect()
                this.connected = true
                this.status = 'Connected'
                await this.loadPrinters()
            } catch (err) {
                this.status = 'QZ Tray not running. Please start it.'
                console.error('[QZ]', err)
            }
        },

        async loadPrinters() {
            try {
                this.availablePrinters = await qz.printers.find()
                const thermal = this.availablePrinters.find(p =>
                    /thermal|58|80|pos|receipt/i.test(p)
                )
                this.printerName = thermal || this.availablePrinters[0] || null
            } catch (err) {
                console.warn('[QZ] Could not list printers:', err)
            }
        },

        async printRaw(escposData) {
            if (!this.connected) await this.connect()
            if (!this.printerName) throw new Error('No printer found.')
            const config = qz.configs.create(this.printerName, {
                size: { width: 58, height: null },
                units: 'mm',
                colorType: 'blackwhite',
            })
            await qz.print(config, escposData)
        },

        async disconnect() {
            if (qz.websocket.isActive()) {
                await qz.websocket.disconnect()
                this.connected = false
                this.status = 'Disconnected'
            }
        }
    }
}