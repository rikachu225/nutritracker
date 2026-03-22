/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — Onboarding Flow
   Multi-step profile setup with glass panel transitions
   ═══════════════════════════════════════════════════════════════════════════ */

const Onboarding = {
    step: 1,
    totalSteps: 7,
    userId: null,
    data: {
        name: '',
        avatar_emoji: '🍎',
        age: null,
        sex: 'male',
        height_cm: null,
        weight_kg: null,
        activity_level: 'moderate',
        body_fat_pct: null,
        body_fat_method: 'visual',
        neck_cm: null,
        waist_cm: null,
        hip_cm: null,
        goal_type: 'maintain',
        goal_weight_kg: null,
        goal_timeline_weeks: 12,
        goal_aggression: 'moderate',
        unit_system: 'metric',
        ai_provider: 'google',
        ai_model: '',
        ai_api_key: '',
    },
    // Lifestyle preferences (separate from profile data)
    preferences: {
        dietary_restrictions: [],
        allergies: [],
        cuisine_preferences: [],
        cooking_frequency: 'few_times_week',
        dining_out_frequency: 'weekly',
        fast_food_frequency: 'rarely',
        travel_frequency: 'rarely',
        budget_preference: 'moderate',
        notes: '',
    },

    avatarOptions: ['🍎', '🥑', '🍊', '🥦', '🍇', '🍋', '🥕', '🍓', '💪', '🏋️', '🧘', '🏃', '⚡', '🔥', '🌟', '🎯'],

    // Body fat reference ranges for visual estimation
    bfRanges: {
        male: [
            { pct: 10, label: 'Very lean', desc: 'Visible abs, veins' },
            { pct: 15, label: 'Lean', desc: 'Some ab definition' },
            { pct: 20, label: 'Average', desc: 'Soft midsection' },
            { pct: 25, label: 'Above avg', desc: 'Noticeable belly' },
            { pct: 30, label: 'Overweight', desc: 'Round midsection' },
            { pct: 35, label: 'Obese', desc: 'Large midsection' },
        ],
        female: [
            { pct: 18, label: 'Very lean', desc: 'Defined muscles' },
            { pct: 22, label: 'Lean', desc: 'Some definition' },
            { pct: 27, label: 'Average', desc: 'Soft figure' },
            { pct: 32, label: 'Above avg', desc: 'Fuller figure' },
            { pct: 37, label: 'Overweight', desc: 'Round midsection' },
            { pct: 42, label: 'Obese', desc: 'Large midsection' },
        ],
    },

    async start(existingUser = null) {
        this.step = 1;

        if (existingUser && existingUser.id) {
            this.userId = existingUser.id;
            this.data.name = existingUser.name || '';
            this.data.avatar_emoji = existingUser.avatar_emoji || '🍎';
        } else {
            this.userId = null;
        }

        App.showView('onboarding');
        this.renderStepIndicators();
        this.showStep(1);
        this.initEmojis();
        this.initUnitToggle();
        this.initBFTabs();
        this.initGoalCards();
        this.initLifestyleChips();
        this.initProviderSelect();
        this.initNavButtons();
    },

    // ─── Step Navigation ───────────────────────────────────────────────────

    renderStepIndicators() {
        const container = document.getElementById('step-indicators');
        container.innerHTML = '';
        for (let i = 1; i <= this.totalSteps; i++) {
            const dot = document.createElement('div');
            dot.className = 'step-dot';
            if (i === this.step) dot.classList.add('active');
            if (i < this.step) dot.classList.add('done');
            container.appendChild(dot);
        }
    },

    showStep(n) {
        document.querySelectorAll('.onboarding-step').forEach(el => {
            el.style.display = el.dataset.step == n ? '' : 'none';
        });
        this.step = n;
        this.renderStepIndicators();

        const backBtn = document.getElementById('ob-back');
        const nextBtn = document.getElementById('ob-next');
        backBtn.style.visibility = n === 1 ? 'hidden' : 'visible';
        nextBtn.textContent = n === this.totalSteps ? 'Finish ✓' : 'Next →';

        // Pre-fill step 3 visual grid based on sex
        if (n === 3) this.renderBFVisual();
        // Pre-fill step 6 model select (was step 5)
        if (n === 6) this.updateModelSelect();
        // Calculate and show targets on step 7 (was step 6)
        if (n === 7) this.showTargets();
    },

    initNavButtons() {
        document.getElementById('ob-back').addEventListener('click', () => {
            if (this.step > 1) this.showStep(this.step - 1);
        });

        document.getElementById('ob-next').addEventListener('click', async () => {
            if (this.step < this.totalSteps) {
                if (await this.validateStep(this.step)) {
                    this.collectStepData(this.step);
                    this.showStep(this.step + 1);
                }
            } else {
                await this.finish();
            }
        });
    },

    // ─── Validation ────────────────────────────────────────────────────────

    async validateStep(n) {
        if (n === 1) {
            const name = document.getElementById('ob-name').value.trim();
            if (!name) { App.toast('Please enter your name', 'error'); return false; }
        }
        if (n === 2) {
            const h = parseFloat(document.getElementById('ob-height').value);
            const w = parseFloat(document.getElementById('ob-weight').value);
            if (!h || h < 50) { App.toast('Please enter your height', 'error'); return false; }
            if (!w || w < 20) { App.toast('Please enter your weight', 'error'); return false; }
        }
        if (n === 6) {
            const key = document.getElementById('ob-api-key').value.trim();
            if (!key) { App.toast('Please enter an API key', 'error'); return false; }
        }
        return true;
    },

    // ─── Collect Data ──────────────────────────────────────────────────────

    collectStepData(n) {
        if (n === 1) {
            this.data.name = document.getElementById('ob-name').value.trim();
            this.data.age = parseInt(document.getElementById('ob-age').value) || 30;
            this.data.sex = document.getElementById('ob-sex').value;
        }
        if (n === 2) {
            const unit = this.data.unit_system;
            let h = parseFloat(document.getElementById('ob-height').value);
            let w = parseFloat(document.getElementById('ob-weight').value);
            if (unit === 'imperial') {
                h = h * 2.54;   // inches → cm
                w = w / 2.205;  // lbs → kg
            }
            this.data.height_cm = h;
            this.data.weight_kg = w;
            this.data.activity_level = document.getElementById('ob-activity').value;
        }
        if (n === 3) {
            // Body fat already set via visual/measure/skip handlers
            this.data.neck_cm = parseFloat(document.getElementById('ob-neck').value) || null;
            this.data.waist_cm = parseFloat(document.getElementById('ob-waist').value) || null;
            this.data.hip_cm = parseFloat(document.getElementById('ob-hip').value) || null;
        }
        if (n === 4) {
            const gw = parseFloat(document.getElementById('ob-goal-weight').value);
            if (gw) {
                this.data.goal_weight_kg = this.data.unit_system === 'imperial' ? gw / 2.205 : gw;
            }
            this.data.goal_timeline_weeks = parseInt(document.getElementById('ob-timeline').value) || 12;
        }
        if (n === 5) {
            // Lifestyle preferences — chips already tracked via click handlers
            this.preferences.cooking_frequency = document.getElementById('ob-cooking-freq').value;
            this.preferences.dining_out_frequency = document.getElementById('ob-dining-freq').value;
            this.preferences.fast_food_frequency = document.getElementById('ob-fastfood-freq').value;
            this.preferences.travel_frequency = document.getElementById('ob-travel-freq').value;
            this.preferences.notes = document.getElementById('ob-lifestyle-notes')?.value.trim() || '';
        }
        if (n === 6) {
            this.data.coach_name = document.getElementById('ob-coach-name').value.trim() || 'Coach';
            this.data.ai_provider = document.getElementById('ob-provider').value;
            this.data.ai_model = document.getElementById('ob-model').value;
            this.data.ai_api_key = document.getElementById('ob-api-key').value.trim();
        }
    },

    // ─── Emoji Picker ──────────────────────────────────────────────────────

    initEmojis() {
        const grid = document.getElementById('emoji-grid');
        grid.innerHTML = '';
        this.avatarOptions.forEach(emoji => {
            const btn = document.createElement('button');
            btn.className = 'emoji-option' + (emoji === this.data.avatar_emoji ? ' selected' : '');
            btn.textContent = emoji;
            btn.type = 'button';
            btn.addEventListener('click', () => {
                grid.querySelectorAll('.emoji-option').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                this.data.avatar_emoji = emoji;
            });
            grid.appendChild(btn);
        });
    },

    // ─── Unit Toggle ───────────────────────────────────────────────────────

    initUnitToggle() {
        document.querySelectorAll('.unit-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.unit-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.data.unit_system = btn.dataset.unit;

                const isImp = btn.dataset.unit === 'imperial';
                document.getElementById('height-label').textContent = isImp ? 'Height (inches)' : 'Height (cm)';
                document.getElementById('weight-label').textContent = isImp ? 'Weight (lbs)' : 'Weight (kg)';

                const heightInput = document.getElementById('ob-height');
                const weightInput = document.getElementById('ob-weight');
                heightInput.placeholder = isImp ? '67' : '170';
                weightInput.placeholder = isImp ? '154' : '70';
            });
        });
    },

    // ─── Body Fat Tabs ─────────────────────────────────────────────────────

    initBFTabs() {
        document.querySelectorAll('.bf-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.bf-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const method = tab.dataset.method;
                this.data.body_fat_method = method;

                document.getElementById('bf-visual').style.display = method === 'visual' ? '' : 'none';
                document.getElementById('bf-measure').style.display = method === 'measure' ? '' : 'none';
                document.getElementById('bf-skip').style.display = method === 'skip' ? '' : 'none';

                if (method === 'skip') this.data.body_fat_pct = null;
            });
        });

        // Navy calculator button
        document.getElementById('calc-navy-bf')?.addEventListener('click', async () => {
            const neck = parseFloat(document.getElementById('ob-neck').value);
            const waist = parseFloat(document.getElementById('ob-waist').value);
            const hip = parseFloat(document.getElementById('ob-hip').value) || null;
            const sex = this.data.sex || document.getElementById('ob-sex').value;

            if (!neck || !waist) {
                App.toast('Enter neck and waist measurements', 'error');
                return;
            }

            try {
                const result = await App.api('/calculate-body-fat', {
                    method: 'POST',
                    body: {
                        sex,
                        neck_cm: neck,
                        waist_cm: waist,
                        hip_cm: hip,
                        height_cm: this.data.height_cm || 170
                    }
                });
                const bf = result.body_fat_pct;
                if (bf !== null) {
                    this.data.body_fat_pct = bf;
                    document.getElementById('bf-navy-result').textContent = `Estimated body fat: ${bf}%`;
                    document.getElementById('bf-navy-result').style.display = '';
                } else {
                    App.toast('Could not calculate — check measurements', 'error');
                }
            } catch (err) {
                App.toast('Calculation failed', 'error');
            }
        });
    },

    renderBFVisual() {
        const sex = this.data.sex || 'male';
        const ranges = this.bfRanges[sex] || this.bfRanges.male;
        const grid = document.getElementById('bf-visual-grid');
        grid.innerHTML = '';

        ranges.forEach(r => {
            const btn = document.createElement('button');
            btn.className = 'bf-visual-option';
            btn.innerHTML = `
                <span class="bf-visual-pct">${r.pct}%</span>
                <span class="bf-visual-label">${r.label}</span>
                <span class="bf-visual-label">${r.desc}</span>
            `;
            btn.addEventListener('click', () => {
                grid.querySelectorAll('.bf-visual-option').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                this.data.body_fat_pct = r.pct;
                document.getElementById('bf-visual-result').textContent = `Selected: ~${r.pct}% body fat`;
                document.getElementById('bf-visual-result').style.display = '';
            });
            grid.appendChild(btn);
        });
    },

    // ─── Goal Cards ────────────────────────────────────────────────────────

    initGoalCards() {
        document.querySelectorAll('.goal-card').forEach(card => {
            card.addEventListener('click', () => {
                document.querySelectorAll('.goal-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                this.data.goal_type = card.dataset.goal;

                const showDetails = card.dataset.goal !== 'maintain';
                document.getElementById('goal-details').style.display = showDetails ? '' : 'none';
                document.getElementById('aggression-group').style.display = showDetails ? '' : 'none';

                // Update weight label based on unit
                const isImp = this.data.unit_system === 'imperial';
                document.getElementById('goal-weight-label').textContent =
                    `Target Weight (${isImp ? 'lbs' : 'kg'})`;
            });
        });

        // Aggression buttons
        document.querySelectorAll('.aggression-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.aggression-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.data.goal_aggression = btn.dataset.val;
            });
        });
    },

    // ─── Lifestyle Chips ────────────────────────────────────────────────────

    initLifestyleChips() {
        // Multi-select chip grids (toggle on/off)
        const chipMappings = {
            'diet-chips': 'dietary_restrictions',
            'allergy-chips': 'allergies',
            'cuisine-chips': 'cuisine_preferences',
        };

        for (const [gridId, prefKey] of Object.entries(chipMappings)) {
            const grid = document.getElementById(gridId);
            if (!grid) continue;
            grid.querySelectorAll('.chip-option').forEach(chip => {
                chip.addEventListener('click', () => {
                    chip.classList.toggle('selected');
                    // Rebuild the array from selected chips
                    this.preferences[prefKey] = Array.from(
                        grid.querySelectorAll('.chip-option.selected')
                    ).map(c => c.dataset.val);
                });
            });
        }

        // Budget buttons (single select, same pattern as aggression)
        document.querySelectorAll('.budget-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.budget-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.preferences.budget_preference = btn.dataset.val;
            });
        });
    },

    // ─── AI Provider Select ────────────────────────────────────────────────

    _fetchModelsTimer: null,
    _lastFetchKey: '',

    initProviderSelect() {
        const providerSelect = document.getElementById('ob-provider');
        const apiKeyInput = document.getElementById('ob-api-key');

        providerSelect.addEventListener('change', () => {
            this.data.ai_provider = providerSelect.value;
            this._tryFetchModels();
        });

        // Debounced live model fetch when user types/pastes API key
        apiKeyInput?.addEventListener('input', () => {
            clearTimeout(this._fetchModelsTimer);
            this._fetchModelsTimer = setTimeout(() => this._tryFetchModels(), 500);
        });

        // Also catch paste events immediately
        apiKeyInput?.addEventListener('paste', () => {
            setTimeout(() => this._tryFetchModels(), 50);
        });

        // Key validation
        document.getElementById('ob-validate-key')?.addEventListener('click', async () => {
            const provider = document.getElementById('ob-provider').value;
            const key = document.getElementById('ob-api-key').value.trim();
            const model = document.getElementById('ob-model').value;
            const resultEl = document.getElementById('key-validation-result');

            if (!key) {
                App.toast('Enter an API key first', 'error');
                return;
            }

            resultEl.className = 'validation-result';
            resultEl.textContent = 'Testing...';
            resultEl.style.display = 'block';

            try {
                const result = await App.api('/users/0/validate-key', {
                    method: 'POST',
                    body: { provider, api_key: key, model }
                });
                resultEl.className = `validation-result ${result.valid ? 'success' : 'error'}`;
                resultEl.textContent = result.message;
            } catch (err) {
                resultEl.className = 'validation-result error';
                resultEl.textContent = err.message || 'Validation failed';
            }
        });
    },

    async _tryFetchModels() {
        const provider = document.getElementById('ob-provider').value;
        const apiKey = document.getElementById('ob-api-key').value.trim();
        const modelSelect = document.getElementById('ob-model');

        // Need both provider and key to fetch
        if (!provider || !apiKey || apiKey.length < 10) {
            modelSelect.innerHTML = '<option value="">Enter API key to load models</option>';
            this.data.ai_model = '';
            return;
        }

        // Skip if we already fetched for this exact combo
        const cacheKey = `${provider}:${apiKey}`;
        if (cacheKey === this._lastFetchKey) return;

        // Show loading state
        modelSelect.innerHTML = '<option value="">Fetching models...</option>';
        modelSelect.disabled = true;

        try {
            const result = await App.api('/fetch-models', {
                method: 'POST',
                body: { provider, api_key: apiKey }
            });

            const models = result.models || {};
            this._lastFetchKey = cacheKey;

            modelSelect.innerHTML = '';

            if (Object.keys(models).length === 0) {
                modelSelect.innerHTML = '<option value="">No models found</option>';
                this.data.ai_model = '';
            } else {
                Object.entries(models).forEach(([id, name]) => {
                    const opt = document.createElement('option');
                    opt.value = id;
                    opt.textContent = name !== id ? `${name} (${id})` : id;
                    modelSelect.appendChild(opt);
                });

                // Default to first model
                this.data.ai_model = modelSelect.options[0].value;
            }
        } catch (err) {
            modelSelect.innerHTML = '<option value="">Failed to fetch models</option>';
            this.data.ai_model = '';
            console.warn('Model fetch failed:', err);
        } finally {
            modelSelect.disabled = false;
        }
    },

    updateModelSelect() {
        // Legacy fallback — now handled by _tryFetchModels()
        this._tryFetchModels();
    },

    // ─── Show Calculated Targets ───────────────────────────────────────────

    async showTargets() {
        this.collectStepData(this.step - 1); // Collect previous step data

        try {
            const targets = await App.api('/calculate-targets', {
                method: 'POST',
                body: this.data
            });

            const container = document.getElementById('targets-preview');
            container.innerHTML = `
                <div class="target-card calories">
                    <div class="target-value">${targets.calorie_target}</div>
                    <div class="target-label">Daily Calories</div>
                </div>
                <div class="target-card">
                    <div class="target-value" style="color: var(--protein)">${targets.protein_g}g</div>
                    <div class="target-label">Protein</div>
                </div>
                <div class="target-card">
                    <div class="target-value" style="color: var(--carbs)">${targets.carbs_g}g</div>
                    <div class="target-label">Carbs</div>
                </div>
                <div class="target-card">
                    <div class="target-value" style="color: var(--fat)">${targets.fat_g}g</div>
                    <div class="target-label">Fat</div>
                </div>
            `;
        } catch (err) {
            console.error('Target calculation failed:', err);
        }
    },

    // ─── Finish Onboarding ─────────────────────────────────────────────────

    async finish() {
        this.collectStepData(this.step);

        try {
            // Create user if new
            if (!this.userId) {
                const created = await App.api('/users', {
                    method: 'POST',
                    body: { name: this.data.name, avatar_emoji: this.data.avatar_emoji }
                });
                this.userId = created.id;
            }

            // Update profile data
            const profileData = { ...this.data };
            delete profileData.ai_api_key; // Send separately

            await App.api(`/users/${this.userId}`, {
                method: 'PUT',
                body: profileData
            });

            // Set AI config (includes API key)
            await App.api(`/users/${this.userId}/ai-config`, {
                method: 'POST',
                body: {
                    ai_provider: this.data.ai_provider,
                    ai_model: this.data.ai_model,
                    ai_api_key: this.data.ai_api_key,
                }
            });

            // Save lifestyle preferences
            await App.api(`/users/${this.userId}/preferences`, {
                method: 'PUT',
                body: this.preferences,
            });

            // Complete onboarding (calculates targets)
            await App.api(`/users/${this.userId}/complete-onboarding`, {
                method: 'POST'
            });

            // Load user and go to dashboard
            await App.selectUser(this.userId);
            App.toast('Profile created! Welcome 🎉', 'success');

        } catch (err) {
            App.toast('Failed to save profile: ' + err.message, 'error');
        }
    },
};
