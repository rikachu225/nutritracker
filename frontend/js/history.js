/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — Meal History
   Browse past days, expand day details, bulk delete by day/range/selection
   ═══════════════════════════════════════════════════════════════════════════ */

const History = {
    _days: [],
    _totalDays: 0,
    _offset: 0,
    _pageSize: 30,
    _selectMode: false,
    _selectedDates: new Set(),
    _expandedDates: new Set(),
    _mealCache: {},   // date → meals[]

    async load() {
        if (!App.state.currentUser) return;
        this._offset = 0;
        this._days = [];
        this._selectedDates.clear();
        this._expandedDates.clear();
        this._mealCache = {};
        this._selectMode = false;
        this._updateBulkBar();

        await this._fetchPage();
        this._initControls();
    },

    async _fetchPage() {
        try {
            const data = await App.api(
                `/users/${App.state.currentUser.id}/meals/history?offset=${this._offset}&limit=${this._pageSize}`
            );
            this._days = this._days.concat(data.days);
            this._totalDays = data.total_days;
            this._offset += data.days.length;

            this._render();

            // Show/hide load more
            const loadMore = document.getElementById('history-load-more');
            if (loadMore) {
                loadMore.style.display = this._offset < this._totalDays ? '' : 'none';
            }
        } catch (err) {
            console.error('History load failed:', err);
            App.toast('Failed to load history', 'error');
        }
    },

    _render() {
        const list = document.getElementById('history-list');
        if (!list) return;

        if (this._days.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <p class="empty-icon">📅</p>
                    <p class="empty-text">No meal history yet</p>
                    <p class="empty-subtext">Your meals will appear here after you log them</p>
                </div>
            `;
            return;
        }

        // Group by month for section headers
        let currentMonth = '';
        let html = '';

        this._days.forEach(day => {
            const d = new Date(day.meal_date + 'T00:00:00');
            const monthKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
            const monthLabel = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

            if (monthKey !== currentMonth) {
                currentMonth = monthKey;
                html += `<div class="history-month-header">${monthLabel}</div>`;
            }

            const dayLabel = this._formatDayLabel(day.meal_date);
            const isExpanded = this._expandedDates.has(day.meal_date);
            const isSelected = this._selectedDates.has(day.meal_date);
            const checkboxHtml = this._selectMode
                ? `<label class="history-checkbox">
                       <input type="checkbox" ${isSelected ? 'checked' : ''} data-date-check="${day.meal_date}">
                       <span class="checkmark"></span>
                   </label>`
                : '';

            html += `
                <div class="history-day ${isExpanded ? 'expanded' : ''}" data-date="${day.meal_date}">
                    <div class="history-day-header" data-date-toggle="${day.meal_date}">
                        ${checkboxHtml}
                        <div class="history-day-info">
                            <span class="history-day-label">${dayLabel}</span>
                            <span class="history-day-date">${day.meal_date}</span>
                        </div>
                        <div class="history-day-stats">
                            <span class="history-day-cals">${day.total_calories} cal</span>
                            <span class="history-day-count">${day.meal_count} meal${day.meal_count !== 1 ? 's' : ''}</span>
                        </div>
                        <span class="history-day-chevron">${isExpanded ? '▾' : '▸'}</span>
                    </div>
                    <div class="history-day-meals" id="meals-${day.meal_date}" style="display:${isExpanded ? '' : 'none'}"></div>
                </div>
            `;
        });

        list.innerHTML = html;

        // Wire up day toggles
        list.querySelectorAll('[data-date-toggle]').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.history-checkbox')) return;
                this._toggleDay(el.dataset.dateToggle);
            });
        });

        // Wire up checkboxes
        list.querySelectorAll('[data-date-check]').forEach(cb => {
            cb.addEventListener('change', () => {
                const date = cb.dataset.dateCheck;
                if (cb.checked) {
                    this._selectedDates.add(date);
                } else {
                    this._selectedDates.delete(date);
                }
                this._updateBulkBar();
            });
        });

        // Render expanded days that have cached meals
        this._expandedDates.forEach(date => {
            if (this._mealCache[date]) {
                this._renderDayMeals(date, this._mealCache[date]);
            }
        });
    },

    async _toggleDay(date) {
        if (this._expandedDates.has(date)) {
            this._expandedDates.delete(date);
            const container = document.getElementById(`meals-${date}`);
            if (container) container.style.display = 'none';
            const dayEl = document.querySelector(`.history-day[data-date="${date}"]`);
            if (dayEl) {
                dayEl.classList.remove('expanded');
                dayEl.querySelector('.history-day-chevron').textContent = '▸';
            }
        } else {
            this._expandedDates.add(date);
            const dayEl = document.querySelector(`.history-day[data-date="${date}"]`);
            if (dayEl) {
                dayEl.classList.add('expanded');
                dayEl.querySelector('.history-day-chevron').textContent = '▾';
            }
            const container = document.getElementById(`meals-${date}`);
            if (container) container.style.display = '';

            // Fetch meals if not cached
            if (!this._mealCache[date]) {
                await this._loadDayMeals(date);
            } else {
                this._renderDayMeals(date, this._mealCache[date]);
            }
        }
    },

    async _loadDayMeals(date) {
        const container = document.getElementById(`meals-${date}`);
        if (!container) return;
        container.innerHTML = '<div class="history-loading">Loading...</div>';

        try {
            const data = await App.api(
                `/users/${App.state.currentUser.id}/meals?date=${date}`
            );
            this._mealCache[date] = data.meals;
            this._renderDayMeals(date, data.meals);
        } catch (err) {
            container.innerHTML = '<div class="history-loading">Failed to load</div>';
        }
    },

    _renderDayMeals(date, meals) {
        const container = document.getElementById(`meals-${date}`);
        if (!container) return;

        const typeLabels = {
            breakfast: '🌅 Breakfast', lunch: '☀️ Lunch',
            dinner: '🌙 Dinner', snack: '🍿 Snack', meal: '🍽️ Meal',
        };

        container.innerHTML = meals.map(meal => {
            const photoHtml = meal.photo_path
                ? `<img class="history-meal-photo" src="/${meal.photo_path}" alt="">`
                : '';

            return `
                <div class="history-meal-item">
                    ${photoHtml}
                    <div class="history-meal-info">
                        <span class="history-meal-type">${typeLabels[meal.meal_type] || '🍽️'}</span>
                        <span class="history-meal-desc">${meal.description || 'Logged meal'}</span>
                    </div>
                    <div class="history-meal-macros">
                        <span class="history-meal-cals">${meal.calories} cal</span>
                        <span class="history-meal-macro">P${Math.round(meal.protein_g)}g C${Math.round(meal.carbs_g)}g F${Math.round(meal.fat_g)}g</span>
                    </div>
                </div>
            `;
        }).join('');
    },

    // ─── Controls ────────────────────────────────────────────────────────────

    _initControls() {
        // Select/Done toggle
        const manageBtn = document.getElementById('history-manage-btn');
        if (manageBtn) {
            const fresh = manageBtn.cloneNode(true);
            manageBtn.parentNode.replaceChild(fresh, manageBtn);
            fresh.addEventListener('click', () => {
                this._selectMode = !this._selectMode;
                fresh.textContent = this._selectMode ? 'Done' : 'Select';
                this._selectedDates.clear();
                this._updateBulkBar();
                this._render();
            });
        }

        // Load more
        const loadMoreBtn = document.getElementById('load-more-btn');
        if (loadMoreBtn) {
            const fresh = loadMoreBtn.cloneNode(true);
            loadMoreBtn.parentNode.replaceChild(fresh, loadMoreBtn);
            fresh.addEventListener('click', () => this._fetchPage());
        }

        // Select all
        const selectAllBtn = document.getElementById('bulk-select-all');
        if (selectAllBtn) {
            const fresh = selectAllBtn.cloneNode(true);
            selectAllBtn.parentNode.replaceChild(fresh, selectAllBtn);
            fresh.addEventListener('click', () => {
                const allSelected = this._selectedDates.size === this._days.length;
                this._selectedDates.clear();
                if (!allSelected) {
                    this._days.forEach(d => this._selectedDates.add(d.meal_date));
                }
                this._updateBulkBar();
                this._render();
            });
        }

        // Bulk delete selected
        const bulkDelBtn = document.getElementById('bulk-delete-btn');
        if (bulkDelBtn) {
            const fresh = bulkDelBtn.cloneNode(true);
            bulkDelBtn.parentNode.replaceChild(fresh, bulkDelBtn);
            fresh.addEventListener('click', () => this._bulkDeleteSelected());
        }

        // Range delete button
        const rangeBtn = document.getElementById('bulk-delete-range');
        if (rangeBtn) {
            const fresh = rangeBtn.cloneNode(true);
            rangeBtn.parentNode.replaceChild(fresh, rangeBtn);
            fresh.addEventListener('click', () => this._showRangeModal());
        }

        // Range modal buttons
        const rangeCancel = document.getElementById('range-cancel');
        if (rangeCancel) {
            const fresh = rangeCancel.cloneNode(true);
            rangeCancel.parentNode.replaceChild(fresh, rangeCancel);
            fresh.addEventListener('click', () => this._hideRangeModal());
        }

        const rangeConfirm = document.getElementById('range-confirm');
        if (rangeConfirm) {
            const fresh = rangeConfirm.cloneNode(true);
            rangeConfirm.parentNode.replaceChild(fresh, rangeConfirm);
            fresh.addEventListener('click', () => this._rangeDelete());
        }
    },

    _updateBulkBar() {
        const bar = document.getElementById('history-bulk-bar');
        if (bar) bar.style.display = this._selectMode ? '' : 'none';

        const count = document.getElementById('bulk-count');
        if (count) count.textContent = `${this._selectedDates.size} selected`;

        const delBtn = document.getElementById('bulk-delete-btn');
        if (delBtn) delBtn.disabled = this._selectedDates.size === 0;
    },

    async _bulkDeleteSelected() {
        const dates = Array.from(this._selectedDates);
        if (dates.length === 0) return;

        // Calculate total meals
        let totalMeals = 0;
        dates.forEach(d => {
            const day = this._days.find(x => x.meal_date === d);
            if (day) totalMeals += day.meal_count;
        });

        if (!confirm(
            `Delete ${totalMeals} meal${totalMeals !== 1 ? 's' : ''} across ${dates.length} day${dates.length !== 1 ? 's' : ''}?\n\nThis cannot be undone.`
        )) return;

        try {
            // Delete each selected date
            for (const date of dates) {
                await App.api(`/users/${App.state.currentUser.id}/meals/bulk-delete`, {
                    method: 'POST',
                    body: { mode: 'date', date }
                });
            }
            App.toast(`Deleted ${totalMeals} meals`, 'success');
            this._selectedDates.clear();
            await this.load();
        } catch (err) {
            App.toast('Delete failed', 'error');
        }
    },

    _showRangeModal() {
        const modal = document.getElementById('range-delete-modal');
        if (!modal) return;

        // Pre-fill with sensible defaults
        const today = App.todayISO();
        document.getElementById('range-end').value = today;

        // Default start to 30 days ago
        const start = new Date();
        start.setDate(start.getDate() - 30);
        document.getElementById('range-start').value = start.toISOString().split('T')[0];

        modal.style.display = '';
    },

    _hideRangeModal() {
        const modal = document.getElementById('range-delete-modal');
        if (modal) modal.style.display = 'none';
    },

    async _rangeDelete() {
        const start = document.getElementById('range-start').value;
        const end = document.getElementById('range-end').value;

        if (!start || !end) {
            App.toast('Select both dates', 'error');
            return;
        }
        if (start > end) {
            App.toast('Start date must be before end date', 'error');
            return;
        }

        if (!confirm(
            `Delete ALL meals from ${start} to ${end}?\n\nThis cannot be undone.`
        )) return;

        try {
            const result = await App.api(
                `/users/${App.state.currentUser.id}/meals/bulk-delete`,
                { method: 'POST', body: { mode: 'range', start_date: start, end_date: end } }
            );
            App.toast(`Deleted ${result.deleted} meals`, 'success');
            this._hideRangeModal();
            await this.load();
        } catch (err) {
            App.toast('Delete failed', 'error');
        }
    },

    // ─── Helpers ──────────────────────────────────────────────────────────────

    _formatDayLabel(dateStr) {
        const d = new Date(dateStr + 'T00:00:00');
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const diff = Math.round((today - d) / 86400000);

        if (diff === 0) return 'Today';
        if (diff === 1) return 'Yesterday';
        if (diff < 7) return d.toLocaleDateString('en-US', { weekday: 'long' });
        return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    },
};
