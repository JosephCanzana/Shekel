
// static/js/theme.js
const html     = document.documentElement;
const DARK_KEY = 'shekel-theme';

function applyTheme(isDark) {
    isDark ? html.classList.add('dark') : html.classList.remove('dark');
    document.querySelectorAll('.theme-icon').forEach(icon => {
        icon.textContent = isDark ? 'light_mode' : 'dark_mode';
    });
}

const savedTheme = localStorage.getItem(DARK_KEY);
const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
applyTheme(savedTheme === 'dark' || (!savedTheme && systemDark));

document.querySelectorAll('.theme-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
        const isDark = !html.classList.contains('dark');
        applyTheme(isDark);
        localStorage.setItem(DARK_KEY, isDark ? 'dark' : 'light');
    });
});