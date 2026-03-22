/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — Core App Router & State
   Vanilla JS SPA — no frameworks, no build step
   ═══════════════════════════════════════════════════════════════════════════ */

const App = {
    state: {
        currentView: null,
        currentUser: null,
        appName: 'NutriTracker',
        providers: {},
    },

    // ─── View Management ───────────────────────────────────────────────────

    showView(viewId) {
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const view = document.getElementById(`view-${viewId}`);
        if (view) {
            view.classList.add('active');
            this.state.currentView = viewId;
        }

        // Show/hide global bottom nav (only when logged in, not during onboarding/setup)
        const nav = document.getElementById('global-bottom-nav');
        const navViews = ['dashboard', 'add-meal', 'trends', 'chat', 'settings', 'history'];
        if (nav) {
            nav.style.display = navViews.includes(viewId) ? '' : 'none';
        }

        // Update active nav button
        if (navViews.includes(viewId)) {
            const tabMap = { 'add-meal': 'add' };
            const activeTab = tabMap[viewId] || viewId;
            document.querySelectorAll('#global-bottom-nav .nav-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.tab === activeTab);
            });
        }
    },

    // ─── API Helpers ───────────────────────────────────────────────────────

    async api(endpoint, options = {}) {
        const url = `/api${endpoint}`;
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        };
        if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
            config.body = JSON.stringify(config.body);
        }
        if (config.body instanceof FormData) {
            delete config.headers['Content-Type'];
        }
        try {
            const resp = await fetch(url, config);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
            return data;
        } catch (err) {
            console.error(`API ${endpoint}:`, err);
            throw err;
        }
    },

    // ─── Toast Notifications ───────────────────────────────────────────────

    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    },

    // ─── Date Formatting ───────────────────────────────────────────────────

    formatDate(dateStr) {
        const d = new Date(dateStr + 'T00:00:00');
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const diff = Math.round((today - d) / 86400000);
        if (diff === 0) return 'Today';
        if (diff === 1) return 'Yesterday';
        return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
    },

    todayISO() {
        return new Date().toISOString().split('T')[0];
    },

    // ─── Device Detection ──────────────────────────────────────────────────

    isMobile() {
        return /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
               (navigator.maxTouchPoints > 0 && window.innerWidth < 768);
    },

    isIOS() {
        return /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
               (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    },

    isAndroid() {
        return /Android/i.test(navigator.userAgent);
    },

    isPWA() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    },

    // ─── Initialization ────────────────────────────────────────────────────

    async init() {
        try {
            // Check app status
            const status = await this.api('/status');
            this.state.appName = status.app_name || 'NutriTracker';
            document.title = this.state.appName;

            // Load providers
            this.state.providers = await this.api('/providers');

            if (status.first_run) {
                this.showView('setup');
                this.initSetup();
            } else if (status.user_count === 0) {
                this.showView('user-select');
                this.renderUserSelect([]);
            } else {
                // Check for saved user in localStorage
                const savedUserId = localStorage.getItem('nutritracker_user');
                if (savedUserId && status.users.find(u => u.id == savedUserId)) {
                    await this.selectUser(parseInt(savedUserId));
                } else if (status.user_count === 1) {
                    await this.selectUser(status.users[0].id);
                } else {
                    this.showView('user-select');
                    this.renderUserSelect(status.users);
                }
            }
        } catch (err) {
            console.error('Init failed:', err);
            this.toast('Failed to connect to server', 'error');
        }

        // Set up global event listeners
        this.initGlobalListeners();
    },

    // ─── Setup (First Run) ─────────────────────────────────────────────────

    initSetup() {
        const btn = document.getElementById('setup-continue');
        const input = document.getElementById('setup-app-name');

        btn.addEventListener('click', async () => {
            const name = input.value.trim() || 'NutriTracker';
            try {
                await this.api('/setup', {
                    method: 'POST',
                    body: { app_name: name }
                });
                this.state.appName = name;
                document.title = name;
                this.showView('user-select');
                this.renderUserSelect([]);
            } catch (err) {
                this.toast('Setup failed', 'error');
            }
        });

        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') btn.click();
        });
    },

    // ─── User Selection ────────────────────────────────────────────────────

    _editMode: false,

    renderUserSelect(users) {
        const title = document.getElementById('user-select-title');
        title.textContent = users.length ? "Who's tracking?" : 'Create your profile';

        const list = document.getElementById('user-list');
        list.innerHTML = '';

        users.forEach(user => {
            const wrapper = document.createElement('div');
            wrapper.className = 'user-card-wrapper';

            const card = document.createElement('button');
            card.className = 'user-card';
            card.innerHTML = `
                <span class="user-card-avatar">${user.avatar_emoji || '🍎'}</span>
                <span class="user-card-name">${user.name}</span>
            `;
            card.addEventListener('click', () => {
                if (!this._editMode) this.selectUser(user.id);
            });
            wrapper.appendChild(card);

            // Delete button (visible in edit mode)
            const delBtn = document.createElement('button');
            delBtn.className = 'user-delete-btn';
            delBtn.innerHTML = '✕';
            delBtn.title = `Delete ${user.name}`;
            delBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete "${user.name}" and all their data?\n\nThis cannot be undone.`)) return;
                try {
                    await this.api(`/users/${user.id}`, { method: 'DELETE' });
                    this.toast(`${user.name} deleted`, 'success');
                    const refreshed = await this.api('/users');
                    this.renderUserSelect(refreshed);
                } catch (err) {
                    this.toast('Failed to delete profile', 'error');
                }
            });
            wrapper.appendChild(delBtn);

            list.appendChild(wrapper);
        });

        // Edit/manage button (only show when profiles exist)
        const editBtn = document.getElementById('manage-profiles-btn');
        if (editBtn) {
            editBtn.style.display = users.length ? '' : 'none';
            editBtn.onclick = () => {
                this._editMode = !this._editMode;
                list.classList.toggle('edit-mode', this._editMode);
                editBtn.textContent = this._editMode ? 'Done' : 'Manage';
            };
        }

        // Reset edit mode on render
        this._editMode = false;
        list.classList.remove('edit-mode');

        const addBtn = document.getElementById('add-user-btn');
        addBtn.onclick = () => {
            Onboarding.start();
        };
    },

    async selectUser(userId) {
        try {
            const user = await this.api(`/users/${userId}`);
            this.state.currentUser = user;
            localStorage.setItem('nutritracker_user', userId);

            if (!user.onboarding_complete) {
                Onboarding.start(user);
            } else {
                this.showView('dashboard');
                Dashboard.load();
            }
        } catch (err) {
            this.toast('Failed to load profile', 'error');
        }
    },

    // ─── Global Listeners ──────────────────────────────────────────────────

    initGlobalListeners() {
        // Back buttons
        document.querySelectorAll('.back-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.back || 'dashboard';
                this.showView(target);
                if (target === 'dashboard') Dashboard.load();
            });
        });

        // Bottom navigation (global)
        document.querySelectorAll('#global-bottom-nav .nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                if (tab === 'add') {
                    this.showView('add-meal');
                    Meals.initAddMeal();
                } else if (tab === 'dashboard') {
                    this.showView('dashboard');
                    Dashboard.load();
                } else if (tab === 'trends') {
                    this.showView('trends');
                    Dashboard.loadTrends();
                } else if (tab === 'chat') {
                    this.showView('chat');
                    const chatTitle = document.getElementById('chat-conv-title');
                    if (chatTitle) chatTitle.textContent = this.state.currentUser?.coach_name || 'Coach';
                    Chat.init();
                } else if (tab === 'settings') {
                    this.showView('settings');
                    Dashboard.loadSettings();
                }
            });
        });

        // Header buttons
        document.getElementById('header-user-btn')?.addEventListener('click', async () => {
            const users = await this.api('/users');
            this.showView('user-select');
            this.renderUserSelect(users);
        });

        document.getElementById('header-settings-btn')?.addEventListener('click', () => {
            this.showView('settings');
            Dashboard.loadSettings();
        });

        document.getElementById('add-meal-btn')?.addEventListener('click', () => {
            this.showView('add-meal');
            Meals.initAddMeal();
        });

        document.getElementById('view-history-btn')?.addEventListener('click', () => {
            this.showView('history');
            History.load();
        });

        // Settings buttons
        document.getElementById('switch-user-btn')?.addEventListener('click', async () => {
            localStorage.removeItem('nutritracker_user');
            const users = await this.api('/users');
            this.showView('user-select');
            this.renderUserSelect(users);
        });

        document.getElementById('delete-profile-btn')?.addEventListener('click', async () => {
            if (!this.state.currentUser) return;
            if (!confirm(`Delete profile "${this.state.currentUser.name}"? This removes all data permanently.`)) return;
            try {
                await this.api(`/users/${this.state.currentUser.id}`, { method: 'DELETE' });
                localStorage.removeItem('nutritracker_user');
                this.state.currentUser = null;
                const users = await this.api('/users');
                this.showView('user-select');
                this.renderUserSelect(users);
                this.toast('Profile deleted', 'success');
            } catch (err) {
                this.toast('Failed to delete profile', 'error');
            }
        });
    },
};

// ─── Boot ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => App.init());
