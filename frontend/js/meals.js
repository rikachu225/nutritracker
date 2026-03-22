/* ═══════════════════════════════════════════════════════════════════════════
   NutriTracker — Meal Capture & Analysis
   Camera, file upload, AI analysis, manual entry
   ═══════════════════════════════════════════════════════════════════════════ */

const Meals = {
    selectedType: 'meal',
    capturedFile: null,
    stream: null,

    initAddMeal() {
        this.capturedFile = null;
        this.selectedType = 'meal';
        this.resetUI();
        this.initMealTypeSelector();
        this.initCameraUpload();
        this.initManualEntry();
        this.initAnalyzeButton();
    },

    resetUI() {
        document.getElementById('upload-area').style.display = '';
        document.getElementById('camera-preview-container').style.display = 'none';
        document.getElementById('photo-preview-container').style.display = 'none';
        document.getElementById('analysis-result').style.display = 'none';
        document.getElementById('manual-entry').style.display = 'none';
        document.getElementById('meal-description').value = '';
        document.getElementById('analyze-btn').disabled = true;
        this.stopCamera();
    },

    // ─── Meal Type Selector ────────────────────────────────────────────────

    initMealTypeSelector() {
        document.querySelectorAll('.meal-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.meal-type-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.selectedType = btn.dataset.type;
            });
        });
    },

    // ─── Camera & Upload ───────────────────────────────────────────────────

    initCameraUpload() {
        // Camera button — use native file picker with capture on mobile (works over HTTP)
        // getUserMedia requires HTTPS on mobile, but <input capture> doesn't
        document.getElementById('camera-btn')?.addEventListener('click', () => {
            if (this._canUseGetUserMedia()) {
                this.startCamera();
            } else {
                // Fallback: trigger native camera via file input
                this._triggerNativeCamera();
            }
        });

        // File upload
        document.getElementById('file-upload')?.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) this.handleFile(file);
        });

        // Capture button (take photo from camera)
        document.getElementById('capture-btn')?.addEventListener('click', () => {
            this.captureFromCamera();
        });

        // Close camera
        document.getElementById('camera-close')?.addEventListener('click', () => {
            this.stopCamera();
            document.getElementById('camera-preview-container').style.display = 'none';
            document.getElementById('upload-area').style.display = '';
        });

        // Retake
        document.getElementById('retake-btn')?.addEventListener('click', () => {
            this.capturedFile = null;
            document.getElementById('photo-preview-container').style.display = 'none';
            document.getElementById('upload-area').style.display = '';
            document.getElementById('analyze-btn').disabled = true;
            document.getElementById('analysis-result').style.display = 'none';
        });

        // Drag and drop
        const uploadZone = document.getElementById('upload-area');
        uploadZone?.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone?.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        uploadZone?.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) this.handleFile(file);
        });
    },

    async startCamera() {
        try {
            const constraints = {
                video: {
                    facingMode: App.isMobile() ? { ideal: 'environment' } : 'user',
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                }
            };

            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            const video = document.getElementById('camera-preview');
            video.srcObject = this.stream;

            document.getElementById('upload-area').style.display = 'none';
            document.getElementById('camera-preview-container').style.display = '';
        } catch (err) {
            console.error('Camera error:', err);
            if (err.name === 'NotAllowedError') {
                App.toast('Camera access denied. Check browser permissions.', 'error');
            } else if (err.name === 'NotFoundError') {
                App.toast('No camera found on this device.', 'error');
            } else {
                App.toast('Camera error: ' + err.message, 'error');
            }
        }
    },

    captureFromCamera() {
        const video = document.getElementById('camera-preview');
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);

        canvas.toBlob((blob) => {
            const file = new File([blob], `photo_${Date.now()}.jpg`, { type: 'image/jpeg' });
            this.handleFile(file);
            this.stopCamera();
            document.getElementById('camera-preview-container').style.display = 'none';
        }, 'image/jpeg', 0.85);
    },

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
    },

    _canUseGetUserMedia() {
        // getUserMedia requires a secure context (HTTPS or localhost)
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.isSecureContext);
    },

    _triggerNativeCamera() {
        // Create a temporary file input with capture="environment" to trigger native camera
        // This works over HTTP on iOS/Android — no getUserMedia needed
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.capture = 'environment'; // Rear camera
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) this.handleFile(file);
        });
        input.click();
    },

    handleFile(file) {
        // Validate
        const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic'];
        if (!validTypes.includes(file.type)) {
            App.toast('Please upload a photo (JPG, PNG, WebP)', 'error');
            return;
        }
        if (file.size > 20 * 1024 * 1024) {
            App.toast('Photo too large (max 20MB)', 'error');
            return;
        }

        this.capturedFile = file;

        // Show preview
        const preview = document.getElementById('photo-preview');
        const url = URL.createObjectURL(file);
        preview.src = url;
        preview.onload = () => URL.revokeObjectURL(url);

        document.getElementById('upload-area').style.display = 'none';
        document.getElementById('photo-preview-container').style.display = '';
        document.getElementById('analyze-btn').disabled = false;
    },

    // ─── AI Analysis ───────────────────────────────────────────────────────

    initAnalyzeButton() {
        document.getElementById('analyze-btn')?.addEventListener('click', async () => {
            if (!this.capturedFile) {
                App.toast('Take or upload a photo first', 'error');
                return;
            }

            const btn = document.getElementById('analyze-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Analyzing...';

            try {
                const formData = new FormData();
                formData.append('photo', this.capturedFile);
                formData.append('description', document.getElementById('meal-description').value);
                formData.append('meal_type', this.selectedType);
                formData.append('meal_date', App.todayISO());

                const result = await App.api(`/users/${App.state.currentUser.id}/analyze`, {
                    method: 'POST',
                    body: formData,
                });

                this.renderAnalysisResult(result);

            } catch (err) {
                App.toast('Analysis failed: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<span class="btn-icon">🔍</span> Analyze with AI';
            }
        });
    },

    renderAnalysisResult(result) {
        const container = document.getElementById('analysis-result');

        // Data source badge
        const sourceLabel = result.has_database_match
            ? '<span class="source-badge source-db">📊 Verified from food database</span>'
            : '<span class="source-badge source-ai">🤖 AI estimated</span>';

        // Items breakdown
        let itemsHtml = '';
        if (result.items?.length) {
            itemsHtml = '<div class="analysis-items">';
            result.items.forEach(item => {
                const confClass = item.confidence >= 0.8 ? 'confidence-high'
                    : item.confidence >= 0.6 ? 'confidence-med' : 'confidence-low';

                // Show data source per item
                const itemSource = item.data_source === 'ai_estimate' ? '🤖' : '📊';
                const brandTag = item.brand ? `<span style="color:var(--accent);font-size:0.7rem">${item.brand}</span>` : '';

                itemsHtml += `
                    <div class="analysis-item">
                        <div>
                            <div class="analysis-item-name">${itemSource} ${item.name}</div>
                            ${brandTag}
                            <div style="font-size:0.75rem;color:var(--text-tertiary)">${item.quantity || ''}</div>
                        </div>
                        <div class="analysis-item-macros">
                            ${item.calories} cal<br>
                            P:${Math.round(item.protein_g)}g C:${Math.round(item.carbs_g)}g F:${Math.round(item.fat_g)}g
                            <span class="confidence-badge ${confClass}">${Math.round(item.confidence * 100)}%</span>
                        </div>
                    </div>
                `;
            });
            itemsHtml += '</div>';
        }

        // Totals — show exact values for database-verified items
        const t = result.totals || {};
        const calDisplay = result.has_database_match
            ? `${t.calories || 0} kcal`
            : `${t.calories_low || 0}–${t.calories_high || 0} kcal (est. ${t.calories || 0})`;

        const totalsHtml = `
            <div class="analysis-totals">
                <div class="analysis-total-row">
                    <span class="analysis-total-label">Calories</span>
                    <span class="analysis-total-value">${calDisplay}</span>
                </div>
                <div class="analysis-total-row">
                    <span class="analysis-total-label">Protein</span>
                    <span class="analysis-total-value">${Math.round(t.protein_g || 0)}g</span>
                </div>
                <div class="analysis-total-row">
                    <span class="analysis-total-label">Carbs</span>
                    <span class="analysis-total-value">${Math.round(t.carbs_g || 0)}g</span>
                </div>
                <div class="analysis-total-row">
                    <span class="analysis-total-label">Fat</span>
                    <span class="analysis-total-value">${Math.round(t.fat_g || 0)}g</span>
                </div>
            </div>
        `;

        // Questions from AI + follow-up questions for generic foods
        let questionsHtml = '';
        if (result.questions?.length) {
            questionsHtml = `
                <div class="analysis-questions">
                    <h4>💬 Tell us more for better accuracy:</h4>
                    <ul>${result.questions.map(q => `<li>${q}</li>`).join('')}</ul>
                </div>
            `;
        }

        container.innerHTML = `
            <h3 class="section-title">Analysis Result</h3>
            ${sourceLabel}
            ${itemsHtml}
            ${totalsHtml}
            ${questionsHtml}
            <button class="btn btn-primary btn-lg" onclick="Meals.saveDone()">
                ✓ Looks Good — Save
            </button>
            <button class="btn btn-ghost" style="width:100%;margin-top:8px" onclick="Meals.editAndSave(${result.meal_id})">
                Edit & Adjust
            </button>
        `;
        container.style.display = '';

        // Scroll to result
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    saveDone() {
        App.toast('Meal saved ✓', 'success');
        App.showView('dashboard');
        Dashboard.load();
    },

    editAndSave(mealId) {
        // For now, just go back to dashboard. Full edit UI is a future enhancement.
        App.toast('Meal saved — edit from dashboard coming soon', 'success');
        App.showView('dashboard');
        Dashboard.load();
    },

    // ─── Manual Entry ──────────────────────────────────────────────────────

    initManualEntry() {
        document.getElementById('manual-entry-toggle')?.addEventListener('click', () => {
            const el = document.getElementById('manual-entry');
            el.style.display = el.style.display === 'none' ? '' : 'none';
        });

        document.getElementById('manual-save-btn')?.addEventListener('click', async () => {
            const cal = parseInt(document.getElementById('manual-calories').value) || 0;
            const protein = parseFloat(document.getElementById('manual-protein').value) || 0;
            const carbs = parseFloat(document.getElementById('manual-carbs').value) || 0;
            const fat = parseFloat(document.getElementById('manual-fat').value) || 0;
            const desc = document.getElementById('meal-description').value.trim();

            if (!cal && !protein && !carbs && !fat) {
                App.toast('Enter at least one value', 'error');
                return;
            }

            try {
                await App.api(`/users/${App.state.currentUser.id}/meals`, {
                    method: 'POST',
                    body: {
                        meal_date: App.todayISO(),
                        meal_type: this.selectedType,
                        description: desc || 'Manual entry',
                        calories: cal,
                        protein_g: protein,
                        carbs_g: carbs,
                        fat_g: fat,
                    }
                });
                App.toast('Meal saved ✓', 'success');
                App.showView('dashboard');
                Dashboard.load();
            } catch (err) {
                App.toast('Failed to save', 'error');
            }
        });
    },
};
