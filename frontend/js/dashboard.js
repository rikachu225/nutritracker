/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — Dashboard & Trends
   Daily summary, meal list, calorie ring, macro bars, trend charts
   ═══════════════════════════════════════════════════════════════════════════ */

const Dashboard = {
    currentDate: null,

    async load() {
        if (!App.state.currentUser) return;
        this.currentDate = App.todayISO();

        const user = App.state.currentUser;

        // Update header
        document.getElementById('header-app-name').textContent = App.state.appName;
        document.getElementById('header-date').textContent = App.formatDate(this.currentDate);
        const avatarBtn = document.getElementById('header-user-btn');
        avatarBtn.textContent = user.avatar_emoji || '🍎';

        await this.loadDayData();
        this.checkWeighinReminder();
    },

    async loadDayData() {
        if (!App.state.currentUser) return;
        const userId = App.state.currentUser.id;

        try {
            const data = await App.api(`/users/${userId}/meals?date=${this.currentDate}`);
            this.renderSummary(data);
            this.renderMeals(data.meals);
        } catch (err) {
            console.error('Failed to load day:', err);
        }
    },

    renderSummary(data) {
        const totals = data.totals;
        const targets = data.targets;

        // Calorie ring
        const consumed = totals.total_calories || 0;
        const target = targets.calories || 2000;
        const pct = Math.min(consumed / target, 1.5);

        document.getElementById('cal-consumed').textContent = consumed;
        document.getElementById('cal-target').textContent = target;

        const ring = document.getElementById('cal-ring');
        const circumference = 2 * Math.PI * 85; // r=85
        const offset = circumference * (1 - Math.min(pct, 1));
        ring.style.strokeDasharray = circumference;
        ring.style.strokeDashoffset = offset;

        // Color the ring based on how close to target
        if (pct > 1.1) {
            ring.style.stroke = '#ef4444'; // Over
        } else if (pct > 0.9) {
            ring.style.stroke = '#6ee7b7'; // On target
        } else {
            ring.style.stroke = '#6ee7b7'; // Under
        }

        // Macro bars
        this.updateMacroBar('protein', totals.total_protein, targets.protein_g);
        this.updateMacroBar('carbs', totals.total_carbs, targets.carbs_g);
        this.updateMacroBar('fat', totals.total_fat, targets.fat_g);
    },

    updateMacroBar(macro, consumed, target) {
        const pct = target ? Math.min((consumed / target) * 100, 100) : 0;
        document.getElementById(`${macro}-consumed`).textContent = Math.round(consumed);
        document.getElementById(`${macro}-target`).textContent = Math.round(target);
        document.getElementById(`${macro}-bar`).style.width = `${pct}%`;
    },

    async checkWeighinReminder() {
        if (!App.state.currentUser) return;
        const userId = App.state.currentUser.id;

        try {
            const status = await App.api(`/users/${userId}/weighin-status`);
            const banner = document.getElementById('weighin-reminder');

            if (status.is_due && banner) {
                // Build message
                let msg = '';
                if (status.days_since === null) {
                    msg = "You haven't logged your weight yet. Quick weigh-in?";
                } else if (status.days_since === 1) {
                    msg = "Time for your daily weigh-in!";
                } else {
                    msg = `It's been ${status.days_since} day${status.days_since !== 1 ? 's' : ''} since your last weigh-in.`;
                }

                banner.querySelector('.weighin-msg').textContent = msg;
                banner.style.display = '';

                // Quick weigh-in button
                const weighBtn = document.getElementById('weighin-quick-btn');
                if (weighBtn) {
                    const fresh = weighBtn.cloneNode(true);
                    weighBtn.parentNode.replaceChild(fresh, weighBtn);
                    fresh.addEventListener('click', () => {
                        // Scroll to settings check-in or show inline input
                        this._showQuickWeighin(banner);
                    });
                }

                // Dismiss
                const dismissBtn = document.getElementById('weighin-dismiss');
                if (dismissBtn) {
                    const fresh = dismissBtn.cloneNode(true);
                    dismissBtn.parentNode.replaceChild(fresh, dismissBtn);
                    fresh.addEventListener('click', () => {
                        banner.style.display = 'none';
                        // Don't remind again today
                        localStorage.setItem('weighin_dismissed_' + App.todayISO(), 'true');
                    });
                }

                // Don't show if already dismissed today
                if (localStorage.getItem('weighin_dismissed_' + App.todayISO())) {
                    banner.style.display = 'none';
                }

                // Try browser notification (if permission granted)
                this._tryBrowserNotification(msg);
            } else if (banner) {
                banner.style.display = 'none';
            }
        } catch (err) {
            console.warn('Weighin check failed:', err);
        }
    },

    _showQuickWeighin(banner) {
        const unit = App.state.currentUser?.unit_system || 'metric';
        const isImp = unit === 'imperial';

        banner.innerHTML = `
            <div class="weighin-inline">
                <div class="input-row" style="margin:0">
                    <input type="number" id="quick-weight" class="text-input"
                           placeholder="${isImp ? 'lbs' : 'kg'}" step="0.1"
                           style="flex:1;min-width:0">
                    <button id="quick-weight-save" class="btn btn-primary btn-sm">Save</button>
                    <button id="quick-weight-cancel" class="btn btn-ghost btn-sm">✕</button>
                </div>
            </div>
        `;

        document.getElementById('quick-weight-save')?.addEventListener('click', async () => {
            let w = parseFloat(document.getElementById('quick-weight').value);
            if (!w) { App.toast('Enter your weight', 'error'); return; }
            if (isImp) w = w / 2.205;
            try {
                await App.api(`/users/${App.state.currentUser.id}/daily-log`, {
                    method: 'POST',
                    body: { log_date: App.todayISO(), weight_kg: Math.round(w * 10) / 10 }
                });
                banner.style.display = 'none';
                App.toast('Weight logged ✓', 'success');
                localStorage.setItem('weighin_dismissed_' + App.todayISO(), 'true');
            } catch (err) {
                App.toast('Failed to save', 'error');
            }
        });

        document.getElementById('quick-weight-cancel')?.addEventListener('click', () => {
            banner.style.display = 'none';
            localStorage.setItem('weighin_dismissed_' + App.todayISO(), 'true');
        });

        document.getElementById('quick-weight')?.focus();
    },

    _tryBrowserNotification(msg) {
        // Only try if Notification API is available and permission is granted
        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') {
            // Only show once per day
            const key = 'weighin_notif_' + App.todayISO();
            if (localStorage.getItem(key)) return;
            localStorage.setItem(key, 'true');

            new Notification(App.state.appName || 'NutriTracker', {
                body: msg,
                icon: '/assets/favicon.svg',
                tag: 'weighin-reminder',
            });
        } else if (Notification.permission === 'default') {
            // Will request permission in settings
        }
    },

    renderMeals(meals) {
        const list = document.getElementById('meals-list');

        if (!meals.length) {
            list.innerHTML = `
                <div class="empty-state">
                    <p class="empty-icon">🍽️</p>
                    <p class="empty-text">No meals logged yet</p>
                    <p class="empty-subtext">Tap "Add Meal" to photograph your food</p>
                </div>
            `;
            return;
        }

        list.innerHTML = '';
        meals.forEach(meal => {
            const card = document.createElement('div');
            card.className = 'meal-card';

            const photoHtml = meal.photo_path
                ? `<img class="meal-photo" src="/${meal.photo_path}" alt="Food photo">`
                : `<div class="meal-photo" style="display:flex;align-items:center;justify-content:center;font-size:1.5rem">🍽️</div>`;

            const confBadge = meal.ai_confidence
                ? this.confidenceBadge(meal.ai_confidence)
                : '';

            const typeLabels = {
                breakfast: '🌅 Breakfast',
                lunch: '☀️ Lunch',
                dinner: '🌙 Dinner',
                snack: '🍿 Snack',
                meal: '🍽️ Meal',
            };

            card.innerHTML = `
                ${photoHtml}
                <div class="meal-info">
                    <div class="meal-type-badge">${typeLabels[meal.meal_type] || '🍽️ Meal'}</div>
                    <div class="meal-name">${meal.description || 'Logged meal'}${confBadge}</div>
                    <div class="meal-macros">
                        <span class="meal-calories">${meal.calories} cal</span>
                        <span>P ${Math.round(meal.protein_g)}g</span>
                        <span>C ${Math.round(meal.carbs_g)}g</span>
                        <span>F ${Math.round(meal.fat_g)}g</span>
                    </div>
                </div>
                <button class="meal-delete" data-meal-id="${meal.id}" title="Delete meal">🗑️</button>
            `;

            // Delete handler
            card.querySelector('.meal-delete').addEventListener('click', async (e) => {
                e.stopPropagation();
                if (!confirm('Delete this meal?')) return;
                try {
                    await App.api(`/users/${App.state.currentUser.id}/meals/${meal.id}`, {
                        method: 'DELETE'
                    });
                    this.loadDayData();
                    App.toast('Meal deleted', 'success');
                } catch (err) {
                    App.toast('Failed to delete', 'error');
                }
            });

            list.appendChild(card);
        });
    },

    confidenceBadge(confidence) {
        let cls, label;
        if (confidence >= 0.8) { cls = 'confidence-high'; label = 'High'; }
        else if (confidence >= 0.6) { cls = 'confidence-med'; label = 'Medium'; }
        else { cls = 'confidence-low'; label = 'Low'; }
        return `<span class="confidence-badge ${cls}">${label} confidence</span>`;
    },

    // ─── Trends ────────────────────────────────────────────────────────────

    _currentTrendDays: 7,

    async loadTrends(days = 7) {
        if (!App.state.currentUser) return;
        const userId = App.state.currentUser.id;
        this._currentTrendDays = days;

        // Period selector
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.loadTrends(parseInt(btn.dataset.days));
            });
        });

        // AI Analysis button
        this.initTrendAnalysis();

        try {
            const data = await App.api(`/users/${userId}/trends?days=${days}`);
            this.renderCaloriesChart(data.daily_totals, days);
            this.renderWeightChart(data.weight_history);
        } catch (err) {
            console.error('Trends load failed:', err);
        }
    },

    initTrendAnalysis() {
        const btn = document.getElementById('analyze-trends-btn');
        if (!btn) return;

        // Clone to remove old listeners
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);

        newBtn.addEventListener('click', async () => {
            newBtn.disabled = true;
            newBtn.innerHTML = '<span class="spinner"></span> Analyzing...';

            const resultEl = document.getElementById('trend-analysis-result');
            resultEl.style.display = 'none';

            try {
                const result = await App.api(
                    `/users/${App.state.currentUser.id}/analyze-trends`,
                    { method: 'POST', body: { days: this._currentTrendDays } }
                );

                // Render with markdown parsing (reuse Chat's parser)
                resultEl.innerHTML = Chat.parseMarkdown(result.analysis);
                resultEl.style.display = '';
                resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });

            } catch (err) {
                App.toast('Trend analysis failed: ' + err.message, 'error');
            } finally {
                newBtn.disabled = false;
                newBtn.innerHTML = '<span class="btn-icon">🧠</span> Analyze My Trends';
            }
        });
    },

    renderCaloriesChart(dailyTotals, days) {
        const canvas = document.getElementById('calories-chart');
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;

        canvas.width = canvas.offsetWidth * dpr;
        canvas.height = 200 * dpr;
        ctx.scale(dpr, dpr);

        const w = canvas.offsetWidth;
        const h = 200;
        const padding = { top: 20, right: 10, bottom: 30, left: 45 };
        const chartW = w - padding.left - padding.right;
        const chartH = h - padding.top - padding.bottom;

        ctx.clearRect(0, 0, w, h);

        if (!dailyTotals.length) {
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No data yet', w / 2, h / 2);
            return;
        }

        const target = App.state.currentUser?.calorie_target || 2000;
        const maxCal = Math.max(target * 1.3, ...dailyTotals.map(d => d.total_calories)) || 2500;

        // Grid lines
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (chartH / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(w - padding.right, y);
            ctx.stroke();

            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(Math.round(maxCal * (1 - i / 4)), padding.left - 6, y + 4);
        }

        // Target line
        const targetY = padding.top + chartH * (1 - target / maxCal);
        ctx.strokeStyle = 'rgba(110, 231, 183, 0.3)';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(padding.left, targetY);
        ctx.lineTo(w - padding.right, targetY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Bars
        const barWidth = Math.max(chartW / days - 4, 8);
        const gap = (chartW - barWidth * days) / (days + 1);

        // Create a map of date → totals
        const dateMap = {};
        dailyTotals.forEach(d => dateMap[d.meal_date] = d.total_calories);

        const today = new Date();
        for (let i = 0; i < days; i++) {
            const d = new Date(today);
            d.setDate(d.getDate() - (days - 1 - i));
            const dateStr = d.toISOString().split('T')[0];
            const cal = dateMap[dateStr] || 0;

            const x = padding.left + gap + i * (barWidth + gap);
            const barH = cal > 0 ? (cal / maxCal) * chartH : 0;
            const y = padding.top + chartH - barH;

            // Bar
            const gradient = ctx.createLinearGradient(x, y, x, padding.top + chartH);
            if (cal > target * 1.1) {
                gradient.addColorStop(0, 'rgba(239, 68, 68, 0.8)');
                gradient.addColorStop(1, 'rgba(239, 68, 68, 0.2)');
            } else {
                gradient.addColorStop(0, 'rgba(110, 231, 183, 0.8)');
                gradient.addColorStop(1, 'rgba(110, 231, 183, 0.2)');
            }
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barH, 3);
            ctx.fill();

            // Day label
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '10px Inter, sans-serif';
            ctx.textAlign = 'center';
            const dayLabel = d.toLocaleDateString('en-US', { weekday: 'short' }).charAt(0);
            ctx.fillText(dayLabel, x + barWidth / 2, h - 8);
        }
    },

    renderWeightChart(weightHistory) {
        const canvas = document.getElementById('weight-chart');
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;

        canvas.width = canvas.offsetWidth * dpr;
        canvas.height = 200 * dpr;
        ctx.scale(dpr, dpr);

        const w = canvas.offsetWidth;
        const h = 200;
        const padding = { top: 20, right: 10, bottom: 30, left: 45 };

        ctx.clearRect(0, 0, w, h);

        if (!weightHistory.length) {
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Log daily weight in Settings → Check-In', w / 2, h / 2);
            return;
        }

        const chartW = w - padding.left - padding.right;
        const chartH = h - padding.top - padding.bottom;
        const weights = weightHistory.map(w => w.weight_kg);
        const minW = Math.min(...weights) - 1;
        const maxW = Math.max(...weights) + 1;

        // Grid
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (chartH / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(w - padding.right, y);
            ctx.stroke();

            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText((maxW - (maxW - minW) * (i / 4)).toFixed(1), padding.left - 6, y + 4);
        }

        // Line
        ctx.strokeStyle = 'rgba(96, 165, 250, 0.8)';
        ctx.lineWidth = 2;
        ctx.beginPath();

        weightHistory.forEach((entry, i) => {
            const x = padding.left + (i / (weightHistory.length - 1 || 1)) * chartW;
            const y = padding.top + chartH * (1 - (entry.weight_kg - minW) / (maxW - minW));
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Dots
        ctx.fillStyle = 'rgba(96, 165, 250, 1)';
        weightHistory.forEach((entry, i) => {
            const x = padding.left + (i / (weightHistory.length - 1 || 1)) * chartW;
            const y = padding.top + chartH * (1 - (entry.weight_kg - minW) / (maxW - minW));
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fill();
        });
    },

    // ─── Settings ──────────────────────────────────────────────────────────

    async loadSettings() {
        if (!App.state.currentUser) return;

        // Refresh user data
        const user = await App.api(`/users/${App.state.currentUser.id}`);
        App.state.currentUser = user;

        // Customization card — app name + coach name
        const appNameInput = document.getElementById('settings-app-name');
        const coachNameInput = document.getElementById('settings-coach-name');
        if (appNameInput) appNameInput.value = App.state.appName || 'NutriTracker';
        if (coachNameInput) coachNameInput.value = user.coach_name || 'Coach';

        document.getElementById('save-app-name')?.addEventListener('click', async () => {
            const name = appNameInput.value.trim();
            if (!name) { App.toast('Enter a name', 'error'); return; }
            try {
                await App.api('/settings', { method: 'PUT', body: { app_name: name } });
                App.state.appName = name;
                document.title = name;
                document.getElementById('header-app-name').textContent = name;
                App.toast('App name updated', 'success');
            } catch (err) { App.toast('Failed to save', 'error'); }
        });

        document.getElementById('save-coach-name')?.addEventListener('click', async () => {
            const name = coachNameInput.value.trim() || 'Coach';
            try {
                await App.api(`/users/${user.id}`, { method: 'PUT', body: { coach_name: name } });
                App.state.currentUser.coach_name = name;
                App.toast(`Coach renamed to ${name}`, 'success');
            } catch (err) { App.toast('Failed to save', 'error'); }
        });

        // Profile card
        const unit = user.unit_system || 'metric';
        const heightStr = unit === 'imperial'
            ? `${(user.height_cm / 2.54).toFixed(0)} in`
            : `${user.height_cm} cm`;
        const weightStr = unit === 'imperial'
            ? `${(user.weight_kg * 2.205).toFixed(0)} lbs`
            : `${user.weight_kg} kg`;

        document.getElementById('settings-profile').innerHTML = `
            <div class="settings-row">
                <span class="settings-row-label">Name</span>
                <span class="settings-row-value">${user.avatar_emoji} ${user.name}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Age / Sex</span>
                <span class="settings-row-value">${user.age || '?'} / ${user.sex || '?'}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Height</span>
                <span class="settings-row-value">${heightStr}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Weight</span>
                <span class="settings-row-value">${weightStr}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Body Fat</span>
                <span class="settings-row-value">${user.body_fat_pct ? user.body_fat_pct + '%' : 'Not set'}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Activity</span>
                <span class="settings-row-value">${(user.activity_level || 'moderate').replace('_', ' ')}</span>
            </div>
        `;

        // Targets card
        const goalLabels = {
            lose_fat: '🔥 Lose Fat', gain_muscle: '💪 Build Muscle',
            maintain: '⚖️ Maintain', recomp: '🔄 Recomp'
        };
        document.getElementById('settings-targets').innerHTML = `
            <div class="settings-row">
                <span class="settings-row-label">Goal</span>
                <span class="settings-row-value">${goalLabels[user.goal_type] || '⚖️ Maintain'}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Calories</span>
                <span class="settings-row-value">${user.calorie_target || '—'} kcal</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Protein</span>
                <span class="settings-row-value">${user.protein_g || '—'}g</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Carbs</span>
                <span class="settings-row-value">${user.carbs_g || '—'}g</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Fat</span>
                <span class="settings-row-value">${user.fat_g || '—'}g</span>
            </div>
        `;

        // AI card
        const providerNames = { openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google Gemini' };
        document.getElementById('settings-ai').innerHTML = `
            <div class="settings-row">
                <span class="settings-row-label">Provider</span>
                <span class="settings-row-value">${providerNames[user.ai_provider] || '—'}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">Model</span>
                <span class="settings-row-value">${user.ai_model || '—'}</span>
            </div>
            <div class="settings-row">
                <span class="settings-row-label">API Key</span>
                <span class="settings-row-value">${user.has_ai_key ? '••••••••' : 'Not set'}</span>
            </div>
        `;

        // Daily check-in card
        const today = App.todayISO();
        let log = {};
        try { log = await App.api(`/users/${user.id}/daily-log?date=${today}`); } catch {}

        // Get weigh-in preferences
        let prefs = {};
        try { prefs = await App.api(`/users/${user.id}/preferences`) || {}; } catch {}
        const weighinFreq = prefs?.weighin_frequency || 'weekly';
        const notifPermission = ('Notification' in window) ? Notification.permission : 'unsupported';

        document.getElementById('settings-checkin').innerHTML = `
            <div class="input-group" style="margin-top:0">
                <label class="input-label">Today's Weight (${unit === 'imperial' ? 'lbs' : 'kg'})</label>
                <div class="input-row">
                    <input type="number" id="checkin-weight" class="text-input"
                           placeholder="${unit === 'imperial' ? '154' : '70'}" step="0.1"
                           value="${log.weight_kg ? (unit === 'imperial' ? (log.weight_kg * 2.205).toFixed(1) : log.weight_kg) : ''}">
                    <button id="save-checkin" class="btn btn-primary btn-sm">Save</button>
                </div>
            </div>
            <div class="input-group">
                <label class="input-label">Weigh-in Reminder Frequency</label>
                <select id="weighin-frequency" class="text-input">
                    <option value="daily" ${weighinFreq === 'daily' ? 'selected' : ''}>Daily</option>
                    <option value="weekly" ${weighinFreq === 'weekly' ? 'selected' : ''}>Weekly (recommended)</option>
                    <option value="biweekly" ${weighinFreq === 'biweekly' ? 'selected' : ''}>Every 2 weeks</option>
                    <option value="monthly" ${weighinFreq === 'monthly' ? 'selected' : ''}>Monthly</option>
                </select>
                <p class="input-hint">You'll see a reminder on the dashboard when it's time</p>
            </div>
            ${notifPermission !== 'unsupported' ? `
                <div class="input-group">
                    <label class="input-label">Browser Notifications</label>
                    <div class="settings-row" style="border:none;padding:0">
                        <span class="settings-row-label" style="flex:1">
                            ${notifPermission === 'granted' ? '✅ Enabled' : notifPermission === 'denied' ? '❌ Blocked (change in browser settings)' : '⬜ Not enabled'}
                        </span>
                        ${notifPermission === 'default' ? '<button id="enable-notifs-btn" class="btn btn-secondary btn-sm">Enable</button>' : ''}
                    </div>
                </div>
            ` : ''}
        `;

        document.getElementById('save-checkin')?.addEventListener('click', async () => {
            let w = parseFloat(document.getElementById('checkin-weight').value);
            if (!w) { App.toast('Enter a weight', 'error'); return; }
            if (unit === 'imperial') w = w / 2.205;
            try {
                await App.api(`/users/${user.id}/daily-log`, {
                    method: 'POST',
                    body: { log_date: today, weight_kg: Math.round(w * 10) / 10 }
                });
                App.toast('Weight logged ✓', 'success');
                // Dismiss reminder for today
                localStorage.setItem('weighin_dismissed_' + today, 'true');
            } catch (err) {
                App.toast('Failed to save', 'error');
            }
        });

        // Weigh-in frequency change
        document.getElementById('weighin-frequency')?.addEventListener('change', async (e) => {
            try {
                await App.api(`/users/${user.id}/preferences`, {
                    method: 'PUT',
                    body: { weighin_frequency: e.target.value }
                });
                App.toast('Reminder frequency updated', 'success');
            } catch (err) {
                App.toast('Failed to save', 'error');
            }
        });

        // Enable notifications button
        document.getElementById('enable-notifs-btn')?.addEventListener('click', async () => {
            try {
                const permission = await Notification.requestPermission();
                if (permission === 'granted') {
                    App.toast('Notifications enabled ✓', 'success');
                    this.loadSettings(); // Re-render to update status
                } else {
                    App.toast('Notifications blocked by browser', 'error');
                }
            } catch (err) {
                App.toast('Could not request permission', 'error');
            }
        });
    },
};
