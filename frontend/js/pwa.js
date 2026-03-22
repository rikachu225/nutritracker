/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — PWA Install & Service Worker
   Handles home screen install prompts for iOS and Android
   ═══════════════════════════════════════════════════════════════════════════ */

const PWA = {
    deferredPrompt: null,

    init() {
        this.registerServiceWorker();
        this.handleInstallPrompt();
        this.checkStandaloneMode();
    },

    // ─── Service Worker ────────────────────────────────────────────────────

    async registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                await navigator.serviceWorker.register('/sw.js');
            } catch (err) {
                console.warn('SW registration failed:', err);
            }
        }
    },

    // ─── Install Prompt (Android / Chrome) ─────────────────────────────────

    handleInstallPrompt() {
        // Chrome/Android fires this event when the app is installable
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            this.deferredPrompt = e;
            this.showInstallBanner('android');
        });

        // iOS doesn't fire beforeinstallprompt — detect manually
        if (App.isIOS() && !App.isPWA()) {
            // Show on first visit only
            const dismissed = localStorage.getItem('nutritracker_install_dismissed');
            if (!dismissed) {
                setTimeout(() => this.showInstallBanner('ios'), 2000);
            }
        }
    },

    showInstallBanner(platform) {
        const banner = document.getElementById('install-banner');
        const instructions = document.getElementById('install-instructions');

        if (platform === 'ios') {
            instructions.innerHTML = 'Tap <strong>Share</strong> ↗️ then <strong>"Add to Home Screen"</strong>';
        } else {
            instructions.innerHTML = 'Tap <strong>"Install"</strong> to add to your home screen';
        }

        banner.classList.remove('hidden');

        // Dismiss button
        document.getElementById('install-dismiss')?.addEventListener('click', () => {
            banner.classList.add('hidden');
            localStorage.setItem('nutritracker_install_dismissed', 'true');
        });

        // For Android, clicking the banner triggers the native prompt
        if (platform === 'android' && this.deferredPrompt) {
            banner.addEventListener('click', async (e) => {
                if (e.target.id === 'install-dismiss') return;
                this.deferredPrompt.prompt();
                const result = await this.deferredPrompt.userChoice;
                if (result.outcome === 'accepted') {
                    banner.classList.add('hidden');
                }
                this.deferredPrompt = null;
            });
        }
    },

    // ─── Standalone Mode Detection ─────────────────────────────────────────

    checkStandaloneMode() {
        // If running as installed PWA, hide the install banner
        if (App.isPWA()) {
            document.getElementById('install-banner')?.classList.add('hidden');
        }
    },
};

// Auto-init after DOM ready
document.addEventListener('DOMContentLoaded', () => PWA.init());
