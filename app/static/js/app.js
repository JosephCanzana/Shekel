// ── Alpine stores ─────────────────────────────────────────
document.addEventListener('alpine:init', () => {

    Alpine.store('sidebar', {
        expanded: false,
        toggle() { this.expanded = !this.expanded }
    })

})
