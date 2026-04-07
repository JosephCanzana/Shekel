// ── Alpine stores ─────────────────────────────────────────
document.addEventListener('alpine:init', () => {

    Alpine.store('sidebar', {
        expanded: false,
        toggle() { this.expanded = !this.expanded }
    })

})

// ── QZ Tray Printer Store ─────────────────────────────────────────────────
document.addEventListener('alpine:init', () => {
Alpine.store('printer', {
    connected:  false,
    name:       null,
    status:     'Disconnected',
    printers:   [],
    method:     null,  // 'qz' | 'bluetooth' | 'none'

    get isMobile() {
        return /android|ipad|iphone|ipod/i.test(navigator.userAgent)
    },

    async connect() {
    if (this.isMobile) {
        this.method    = 'bluetooth'
        this.status    = 'Mobile — use Bluetooth print'
        this.connected = true
        return
    }
    try {
        if (qz.websocket.isActive()) {
            // Already connected — just set the method
            this.connected = true
            this.method    = 'qz'
            this.status    = 'Connected'
            await this.loadPrinters()
            return
        }
        await qz.websocket.connect()
        this.connected = true
        this.method    = 'qz'
        this.status    = 'Connected'
        await this.loadPrinters()
    } catch (err) {
        this.method    = 'none'
        this.status    = 'QZ Tray not running'
        this.connected = false
        console.error('[QZ]', err)
    }},
    

    async loadPrinters() {
        try {
            this.printers = await qz.printers.find()
            const thermal = this.printers.find(p =>
                /thermal|58|80|pos|receipt/i.test(p)
            )
            this.name = thermal || this.printers[0] || null
        } catch (err) {
            console.warn('[QZ] Could not list printers:', err)
        }
    },

    async print(commands) {
        if (this.method === 'qz')        return await this._printQZ(commands)
        if (this.method === 'bluetooth') return await this._printBluetooth(commands)
        throw new Error('No print method available.')
    },

    // ── Desktop: QZ Tray ──────────────────────────────────────────────
    async _printQZ(commands) {
        if (!this.name) throw new Error('No printer selected.')
        const config = qz.configs.create(this.name, {
            size: { width: 58, height: null }, units: 'mm', colorType: 'blackwhite'
        })
        await qz.print(config, commands)
    },

    // ── Mobile: Web Bluetooth (Android Chrome + some iOS) ─────────────
    async _printBluetooth(commands) {
        if (!navigator.bluetooth)
            throw new Error('Bluetooth not supported on this browser. Use Chrome on Android.')

        const device = await navigator.bluetooth.requestDevice({
            filters: [{ services: ['000018f0-0000-1000-8000-00805f9b34fb'] }]
            // ^ Standard BT thermal printer service UUID
        })
        const server  = await device.gatt.connect()
        const service = await server.getPrimaryService('000018f0-0000-1000-8000-00805f9b34fb')
        const char    = await service.getCharacteristic('00002af1-0000-1000-8000-00805f9b34fb')

        // Convert ESC/POS string array → single Uint8Array
        const raw = commands.join('')
        const buf = new Uint8Array(raw.length)
        for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i)

        // Write in 512-byte chunks (BT MTU limit)
        const CHUNK = 512
        for (let i = 0; i < buf.length; i += CHUNK) {
            await char.writeValue(buf.slice(i, i + CHUNK))
        }
    }
})
})

// ── QZ Security (dev mode — replace with signed cert in production) ────────
qz.security.setCertificatePromise(resolve => resolve('-----EMPTY-----'))
qz.security.setSignatureAlgorithm('SHA512')
qz.security.setSignaturePromise(hash => new Promise(resolve => resolve('')))