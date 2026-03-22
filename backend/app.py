"""
NutriTracker Flask Application
===============================
REST API + static file serving for the NutriTracker PWA.
All endpoints return JSON. Frontend is a vanilla JS SPA.
"""

import os
import asyncio
import uuid
from pathlib import Path
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename

from . import database as db
from . import ai_proxy
from . import food_analyzer
from . import food_database

# ─── App Setup ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')


def run_async(coro):
    """Helper to run async functions from sync Flask routes."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── JSON Error Handlers (never return HTML to SPA) ──────────────────────

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': str(e)}), 400

@app.errorhandler(404)
def not_found(e):
    # Only return JSON for API routes; serve SPA for frontend routes
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': f'Internal server error: {e}'}), 500

@app.errorhandler(Exception)
def unhandled_exception(e):
    import traceback
    traceback.print_exc()
    return jsonify({'error': f'Server error: {type(e).__name__}: {str(e)}'}), 500


# ─── Static Files & SPA ────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(str(FRONTEND_DIR), 'manifest.json')


@app.route('/sw.js')
def serve_sw():
    return send_from_directory(str(FRONTEND_DIR), 'sw.js')


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(str(FRONTEND_DIR / 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(str(FRONTEND_DIR / 'js'), filename)


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(str(FRONTEND_DIR / 'assets'), filename)


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


# ─── App State ──────────────────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    """Check if the app is set up and ready."""
    first_run = db.is_first_run()
    app_name = db.get_setting('app_name', 'NutriTracker')
    users = db.get_all_users()
    return jsonify({
        'first_run': first_run,
        'app_name': app_name,
        'user_count': len(users),
        'users': users,
        'server_time': datetime.now().isoformat(),
    })


@app.route('/api/setup', methods=['POST'])
def api_setup():
    """First-time app setup — name the app."""
    data = request.json or {}
    app_name = data.get('app_name', 'NutriTracker').strip()
    if not app_name:
        return jsonify({'error': 'App name required'}), 400

    db.set_setting('app_name', app_name)
    db.set_setting('setup_date', datetime.now().isoformat())
    return jsonify({'ok': True, 'app_name': app_name})


# ─── User / Profile ────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
def api_get_users():
    return jsonify(db.get_all_users())


@app.route('/api/users', methods=['POST'])
def api_create_user():
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    avatar = data.get('avatar_emoji', '🍎')
    user_id = db.create_user(name, avatar)
    return jsonify({'id': user_id, 'name': name, 'avatar_emoji': avatar})


@app.route('/api/users/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    # Don't send API keys to frontend
    safe_user = {k: v for k, v in user.items()
                 if 'api_key' not in k}
    safe_user['has_ai_key'] = bool(user.get('ai_api_key'))
    safe_user['has_vision_key'] = bool(user.get('vision_api_key'))
    return jsonify(safe_user)


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def api_update_user(user_id):
    data = request.json or {}
    if not db.get_user(user_id):
        return jsonify({'error': 'User not found'}), 404

    # If body measurements provided (with actual values), calculate Navy body fat
    neck = data.get('neck_cm')
    waist = data.get('waist_cm')
    sex = data.get('sex')
    if neck and waist and sex:
        navy_bf = food_analyzer.calculate_navy_body_fat(
            sex=sex,
            neck_cm=float(neck),
            waist_cm=float(waist),
            hip_cm=float(data['hip_cm']) if data.get('hip_cm') else None,
            height_cm=float(data['height_cm']) if data.get('height_cm') else 170
        )
        if navy_bf is not None:
            data['body_fat_navy'] = navy_bf

    db.update_user(user_id, **data)

    # Recalculate targets if relevant fields changed
    target_fields = {'weight_kg', 'height_cm', 'age', 'sex', 'activity_level',
                     'goal_type', 'goal_aggression'}
    if target_fields & set(data.keys()):
        user = db.get_user(user_id)
        targets = food_analyzer.calculate_targets(user)
        db.update_user(user_id, **targets)

    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def api_delete_user(user_id):
    db.delete_user(user_id)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/complete-onboarding', methods=['POST'])
def api_complete_onboarding(user_id):
    """Mark onboarding as complete and calculate initial targets."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    targets = food_analyzer.calculate_targets(user)
    db.update_user(user_id, onboarding_complete=1, **targets)
    return jsonify({'ok': True, 'targets': targets})


# ─── AI Configuration ──────────────────────────────────────────────────────

@app.route('/api/providers')
def api_get_providers():
    """Get available AI providers and models."""
    return jsonify(ai_proxy.get_available_providers())


@app.route('/api/users/<int:user_id>/ai-config', methods=['POST'])
def api_set_ai_config(user_id):
    """Set the user's AI provider, model, and API key."""
    data = request.json or {}
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    updates = {}
    if 'ai_provider' in data:
        updates['ai_provider'] = data['ai_provider']
    if 'ai_model' in data:
        updates['ai_model'] = data['ai_model']
    if 'ai_api_key' in data:
        updates['ai_api_key'] = data['ai_api_key']
    if 'vision_provider' in data:
        updates['vision_provider'] = data['vision_provider']
    if 'vision_model' in data:
        updates['vision_model'] = data['vision_model']
    if 'vision_api_key' in data:
        updates['vision_api_key'] = data['vision_api_key']

    if updates:
        db.update_user(user_id, **updates)

    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/validate-key', methods=['POST'])
def api_validate_key(user_id):
    """Test if an API key works."""
    data = request.json or {}
    provider = data.get('provider', '')
    api_key = data.get('api_key', '')
    model = data.get('model')

    if not provider or not api_key:
        return jsonify({'valid': False, 'message': 'Provider and API key required'}), 400

    valid, message = run_async(ai_proxy.validate_api_key(provider, api_key, model))
    return jsonify({'valid': valid, 'message': message})


@app.route('/api/fetch-models', methods=['POST'])
def api_fetch_models():
    """Fetch available models live from a provider using the user's API key."""
    data = request.json or {}
    provider = data.get('provider', '')
    api_key = data.get('api_key', '')

    if not provider or not api_key:
        return jsonify({'error': 'Provider and API key required'}), 400

    models = run_async(ai_proxy.fetch_models_live(provider, api_key))
    return jsonify({'models': models, 'count': len(models)})


# ─── User Preferences ─────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/preferences', methods=['GET'])
def api_get_preferences(user_id):
    """Get user lifestyle/dietary preferences."""
    prefs = db.get_user_preferences(user_id)
    if not prefs:
        return jsonify({
            'dietary_restrictions': [],
            'allergies': [],
            'cuisine_preferences': [],
            'cooking_frequency': 'few_times_week',
            'dining_out_frequency': 'weekly',
            'fast_food_frequency': 'rarely',
            'travel_frequency': 'rarely',
            'budget_preference': 'moderate',
            'favorite_foods': [],
            'disliked_foods': [],
            'notes': '',
        })
    # Don't expose API keys to frontend
    safe_prefs = {k: v for k, v in prefs.items()
                  if k not in ('nutritionix_app_id', 'nutritionix_app_key', 'usda_api_key')}
    safe_prefs['has_nutritionix'] = bool(prefs.get('nutritionix_app_key'))
    return jsonify(safe_prefs)


@app.route('/api/users/<int:user_id>/preferences', methods=['PUT'])
def api_update_preferences(user_id):
    """Update user lifestyle/dietary preferences."""
    if not db.get_user(user_id):
        return jsonify({'error': 'User not found'}), 404
    data = request.json or {}
    db.upsert_user_preferences(user_id, **data)
    return jsonify({'ok': True})


# ─── Food Database Lookup ──────────────────────────────────────────────────

@app.route('/api/food/search', methods=['POST'])
def api_food_search():
    """Search food databases for nutritional data."""
    data = request.json or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Search query required'}), 400

    # Get user's Nutritionix keys if available
    user_id = data.get('user_id')
    nix_id = None
    nix_key = None
    usda_key = None
    if user_id:
        prefs = db.get_user_preferences(user_id)
        if prefs:
            nix_id = prefs.get('nutritionix_app_id')
            nix_key = prefs.get('nutritionix_app_key')
            usda_key = prefs.get('usda_api_key')

    result = run_async(food_database.lookup_food(
        food_name=query,
        portion_desc=data.get('portion'),
        nutritionix_id=nix_id,
        nutritionix_key=nix_key,
        usda_key=usda_key,
    ))

    if result:
        return jsonify({'found': True, 'food': result})
    return jsonify({'found': False, 'food': None})


@app.route('/api/food/detect', methods=['POST'])
def api_food_detect():
    """Detect if food is branded/generic and get follow-up questions."""
    data = request.json or {}
    description = data.get('description', '').strip()
    if not description:
        return jsonify({'error': 'Food description required'}), 400

    detection = food_database.detect_food_type(description)
    return jsonify(detection)


# ─── Meals ──────────────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/meals', methods=['GET'])
def api_get_meals(user_id):
    """Get meals for a date (query param: ?date=YYYY-MM-DD)."""
    meal_date = request.args.get('date', date.today().isoformat())
    meals = db.get_meals_for_date(user_id, meal_date)
    totals = db.get_daily_totals(user_id, meal_date)
    user = db.get_user(user_id)
    return jsonify({
        'date': meal_date,
        'meals': meals,
        'totals': totals,
        'targets': {
            'calories': user.get('calorie_target', 2000),
            'protein_g': user.get('protein_g', 150),
            'carbs_g': user.get('carbs_g', 200),
            'fat_g': user.get('fat_g', 70),
        }
    })


@app.route('/api/users/<int:user_id>/meals', methods=['POST'])
def api_add_meal(user_id):
    """Add a meal manually (no photo)."""
    data = request.json or {}
    meal_id = db.add_meal(
        user_id=user_id,
        meal_date=data.get('meal_date', date.today().isoformat()),
        meal_type=data.get('meal_type', 'meal'),
        description=data.get('description'),
        calories=data.get('calories', 0),
        protein_g=data.get('protein_g', 0),
        carbs_g=data.get('carbs_g', 0),
        fat_g=data.get('fat_g', 0),
        fiber_g=data.get('fiber_g', 0),
        notes=data.get('notes'),
        items=data.get('items'),
    )
    return jsonify({'id': meal_id, 'ok': True})


@app.route('/api/users/<int:user_id>/meals/<int:meal_id>', methods=['PUT'])
def api_update_meal(user_id, meal_id):
    """Update a meal (e.g., user corrections to AI estimates)."""
    data = request.json or {}
    data['user_adjusted'] = 1
    db.update_meal(meal_id, **data)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/meals/<int:meal_id>', methods=['DELETE'])
def api_delete_meal(user_id, meal_id):
    db.delete_meal(meal_id)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/meals/history', methods=['GET'])
def api_meal_history(user_id):
    """Get paginated meal history grouped by date (newest first)."""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 30, type=int)
    days = db.get_meal_history(user_id, offset, limit)
    total = db.get_meal_date_count(user_id)
    date_range = db.get_meal_date_range(user_id)
    return jsonify({
        'days': days,
        'total_days': total,
        'offset': offset,
        'date_range': date_range,
    })


@app.route('/api/users/<int:user_id>/meals/bulk-delete', methods=['POST'])
def api_bulk_delete_meals(user_id):
    """Bulk delete meals by date, date range, or specific IDs.
    Body: { mode: 'date' | 'range' | 'ids', date?, start_date?, end_date?, meal_ids? }"""
    data = request.json or {}
    mode = data.get('mode', '')

    if mode == 'date':
        meal_date = data.get('date')
        if not meal_date:
            return jsonify({'error': 'Date required'}), 400
        count = db.delete_meals_by_date(user_id, meal_date)
    elif mode == 'range':
        start = data.get('start_date')
        end = data.get('end_date')
        if not start or not end:
            return jsonify({'error': 'start_date and end_date required'}), 400
        count = db.delete_meals_by_range(user_id, start, end)
    elif mode == 'ids':
        ids = data.get('meal_ids', [])
        if not ids:
            return jsonify({'error': 'meal_ids required'}), 400
        count = db.delete_meals_by_ids(user_id, ids)
    else:
        return jsonify({'error': 'Invalid mode. Use: date, range, or ids'}), 400

    return jsonify({'ok': True, 'deleted': count})


# ─── Food Photo Analysis ───────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/analyze', methods=['POST'])
def api_analyze_food(user_id):
    """Upload a food photo for AI analysis."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if not user.get('ai_api_key'):
        return jsonify({'error': 'No API key configured. Go to Settings to add one.'}), 400

    # Handle file upload
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400

    photo = request.files['photo']
    if not photo.filename:
        return jsonify({'error': 'Empty filename'}), 400

    ext = Path(photo.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'File type {ext} not supported'}), 400

    # Save with unique name
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = UPLOAD_DIR / filename
    photo.save(str(filepath))

    # Check file size
    if filepath.stat().st_size > MAX_UPLOAD_SIZE:
        filepath.unlink()
        return jsonify({'error': 'File too large (max 20MB)'}), 400

    # Get optional user description
    description = request.form.get('description', '')

    # Get user preferences for dietary context + API keys
    prefs = db.get_user_preferences(user_id)
    nix_id = prefs.get('nutritionix_app_id') if prefs else None
    nix_key = prefs.get('nutritionix_app_key') if prefs else None

    # Run AI analysis with database cross-reference
    result = run_async(food_analyzer.analyze_food_photo(
        user, str(filepath), description,
        user_preferences=prefs,
        nix_id=nix_id, nix_key=nix_key,
    ))

    if result.get('error'):
        return jsonify(result), 500

    # Auto-save as a meal
    meal_type = request.form.get('meal_type', 'meal')
    meal_date = request.form.get('meal_date', date.today().isoformat())

    meal_id = db.add_meal(
        user_id=user_id,
        meal_date=meal_date,
        meal_type=meal_type,
        description=result.get('description', description),
        photo_path=f"uploads/{filename}",
        ai_analysis=result.get('raw_response', ''),
        ai_confidence=result.get('confidence', 0),
        calories=result['totals']['calories'],
        protein_g=result['totals']['protein_g'],
        carbs_g=result['totals']['carbs_g'],
        fat_g=result['totals']['fat_g'],
        fiber_g=result['totals']['fiber_g'],
        items=result.get('items'),
    )

    result['meal_id'] = meal_id
    result['photo_url'] = f"/uploads/{filename}"
    return jsonify(result)


# ─── Daily Log ──────────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/daily-log', methods=['GET'])
def api_get_daily_log(user_id):
    log_date = request.args.get('date', date.today().isoformat())
    log = db.get_daily_log(user_id, log_date)
    return jsonify(log or {})


@app.route('/api/users/<int:user_id>/daily-log', methods=['POST'])
def api_upsert_daily_log(user_id):
    data = request.json or {}
    log_date = data.pop('log_date', date.today().isoformat())
    log_id = db.upsert_daily_log(user_id, log_date, **data)
    return jsonify({'id': log_id, 'ok': True})


@app.route('/api/users/<int:user_id>/weight-history', methods=['GET'])
def api_weight_history(user_id):
    limit = request.args.get('limit', 90, type=int)
    history = db.get_weight_history(user_id, limit)
    return jsonify(history)


# ─── Trends / Stats ────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/trends', methods=['GET'])
def api_trends(user_id):
    """Get weekly nutrition trends."""
    end = request.args.get('end', date.today().isoformat())
    days = request.args.get('days', 7, type=int)
    end_date = date.fromisoformat(end)
    start_date = end_date - timedelta(days=days - 1)
    totals = db.get_weekly_totals(user_id, start_date.isoformat(), end_date.isoformat())
    weight = db.get_weight_history(user_id, days)
    return jsonify({'daily_totals': totals, 'weight_history': weight})


# ─── AI Trend Analysis ─────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/analyze-trends', methods=['POST'])
def api_analyze_trends(user_id):
    """AI-powered trend analysis and coaching insights."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if not user.get('ai_api_key'):
        return jsonify({'error': 'No API key configured'}), 400

    data = request.json or {}
    days = data.get('days', 7)

    # Gather trend data
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    daily_totals = db.get_weekly_totals(user_id, start_date.isoformat(), end_date.isoformat())
    weight_history = db.get_weight_history(user_id, days)
    prefs = db.get_user_preferences(user_id)

    # Get actual meals with descriptions for richer analysis
    all_meals = db.get_meals_range(user_id, start_date.isoformat(), end_date.isoformat())

    # Get workouts for the period
    all_workouts = db.get_workouts_range(user_id, start_date.isoformat(), end_date.isoformat())

    # Build data summary for AI
    days_logged = len(daily_totals)
    avg_cal = round(sum(d['total_calories'] for d in daily_totals) / max(days_logged, 1))
    avg_protein = round(sum(d['total_protein'] for d in daily_totals) / max(days_logged, 1))
    avg_carbs = round(sum(d['total_carbs'] for d in daily_totals) / max(days_logged, 1))
    avg_fat = round(sum(d['total_fat'] for d in daily_totals) / max(days_logged, 1))

    target_cal = user.get('calorie_target', 2000)
    target_protein = user.get('protein_g', 150)
    target_carbs = user.get('carbs_g', 200)
    target_fat = user.get('fat_g', 70)

    weight_change = ''
    if len(weight_history) >= 2:
        first_w = weight_history[0]['weight_kg']
        last_w = weight_history[-1]['weight_kg']
        diff = round(last_w - first_w, 1)
        weight_change = f"Weight change: {'+' if diff > 0 else ''}{diff} kg over {days} days"

    # Build rich daily breakdown with individual meal descriptions
    daily_breakdown_lines = []
    meals_by_date = {}
    for meal in all_meals:
        d = meal.get('meal_date', '')
        if d not in meals_by_date:
            meals_by_date[d] = []
        meals_by_date[d].append(meal)

    for d in daily_totals:
        day_date = d['meal_date']
        line = (f"  {day_date}: {d['total_calories']} cal, {d['total_protein']}g P, "
                f"{d['total_carbs']}g C, {d['total_fat']}g F, {d['meal_count']} meals")
        day_meals = meals_by_date.get(day_date, [])
        if day_meals:
            for m in day_meals:
                desc = m.get('description') or 'Logged meal (no description)'
                mtype = (m.get('meal_type') or 'meal').title()
                items_text = ''
                if m.get('items'):
                    item_names = [i.get('name', '?') for i in m['items'][:5]]
                    items_text = f" — items: {', '.join(item_names)}"
                line += (f"\n    → {mtype}: {desc} "
                         f"({m.get('calories', 0)} cal, {round(m.get('protein_g', 0))}g P, "
                         f"{round(m.get('carbs_g', 0))}g C, {round(m.get('fat_g', 0))}g F)"
                         f"{items_text}")
        daily_breakdown_lines.append(line)

    daily_breakdown = '\n'.join(daily_breakdown_lines) or "  No meals logged"

    # Build workout summary
    workout_summary = ""
    if all_workouts:
        workout_days = len(set(w['workout_date'] for w in all_workouts))
        workout_lines = []
        for w in all_workouts:
            line = f"  {w['workout_date']}: {w['workout_type']}"
            if w.get('duration_min'):
                line += f" ({w['duration_min']} min)"
            if w.get('intensity'):
                line += f" [{w['intensity']}]"
            workout_lines.append(line)
        workout_summary = f"\nWORKOUTS ({workout_days} days with exercise):\n" + "\n".join(workout_lines)
    else:
        workout_summary = "\nWORKOUTS: No workouts logged this period."

    system_prompt = food_analyzer.build_user_system_prompt(user, preferences=prefs)
    analysis_prompt = f"""Analyze the user's nutrition trends for the past {days} days and provide coaching insights.

TREND DATA ({days} days):
Days with logged meals: {days_logged} / {days}
Average daily: {avg_cal} cal (target: {target_cal}), {avg_protein}g protein (target: {target_protein}g), {avg_carbs}g carbs (target: {target_carbs}g), {avg_fat}g fat (target: {target_fat}g)
{weight_change}

DAILY BREAKDOWN (with individual meals and foods):
{daily_breakdown}
{workout_summary}

IMPORTANT: You can see WHAT the user actually ate each day AND their workout activity (meal descriptions, food items, and per-meal macros).
Use this to give food-specific advice — comment on specific meals, suggest swaps, identify patterns
(e.g., "you're grabbing fast food for lunch 3 out of 5 days" or "great job with the grilled chicken salads").

PROVIDE YOUR ANALYSIS IN THIS STRUCTURE:
1. **Summary** — One-sentence overview of how they're doing
2. **What's Working** — Positive patterns you see (even small wins)
3. **Where to Improve** — Honest but constructive gaps (be specific with numbers)
4. **Action Plan** — 2-3 concrete, easy steps for the next {days} days
5. **Motivation** — One encouraging line that acknowledges their effort

TONE RULES:
- Be a coach, not a judge. Never demean or guilt-trip.
- If they're off track, frame it as "here's how to get back" not "you failed"
- Acknowledge that consistency matters more than perfection
- If they barely logged meals, encourage logging more — you can't coach what you can't see
- Be specific: "Add a protein shake after your workout" not "eat more protein"
- If they're crushing it, say so enthusiastically
"""

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': analysis_prompt},
    ]

    try:
        response = run_async(ai_proxy.chat(
            provider=user['ai_provider'],
            api_key=user['ai_api_key'],
            model=user['ai_model'],
            messages=messages,
        ))
        return jsonify({'analysis': response, 'days': days, 'days_logged': days_logged})

    except Exception as e:
        return jsonify({'error': f'AI analysis failed: {str(e)}'}), 500


# ─── Chat Conversations ────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/conversations', methods=['GET'])
def api_get_conversations(user_id):
    """Get all conversations for a user."""
    convos = db.get_conversations(user_id)
    return jsonify(convos)


@app.route('/api/users/<int:user_id>/conversations', methods=['POST'])
def api_create_conversation(user_id):
    """Create a new conversation."""
    data = request.json or {}
    title = data.get('title', 'New Chat')
    conv_id = db.create_conversation(user_id, title)
    return jsonify({'id': conv_id, 'title': title})


@app.route('/api/users/<int:user_id>/conversations/<int:conv_id>', methods=['DELETE'])
def api_delete_conversation(user_id, conv_id):
    """Delete a conversation and its messages."""
    db.delete_conversation(conv_id)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/conversations/<int:conv_id>', methods=['PUT'])
def api_rename_conversation(user_id, conv_id):
    """Rename a conversation."""
    data = request.json or {}
    title = data.get('title', '').strip()
    if title:
        db.update_conversation(conv_id, title=title)
    return jsonify({'ok': True})


# ─── AI Chat ──────────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/chat', methods=['POST'])
def api_chat(user_id):
    """Send a message to the AI coach."""
    import re as _re
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if not user.get('ai_api_key'):
        return jsonify({'error': 'No API key configured'}), 400

    data = request.json or {}
    user_message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')
    if not user_message:
        return jsonify({'error': 'Message required'}), 400

    # Auto-create conversation if none specified
    is_new_conversation = False
    if not conversation_id:
        title = user_message[:40] + ('...' if len(user_message) > 40 else '')
        conversation_id = db.create_conversation(user_id, title)
        is_new_conversation = True

    # Build context with recent meal data
    today = date.today().isoformat()
    today_totals = db.get_daily_totals(user_id, today)
    today_meals = db.get_meals_for_date(user_id, today)

    # Build messages with system prompt + history + context
    prefs = db.get_user_preferences(user_id)
    system_prompt = food_analyzer.build_user_system_prompt(user, preferences=prefs)

    # Add persistent memory to system prompt
    memories = db.get_chat_memories(user_id, limit=30)
    if memories:
        memory_text = "\n".join(f"- {m['fact']}" for m in memories)
        system_prompt += f"""

THINGS I REMEMBER ABOUT YOU (from our previous conversations):
{memory_text}

Use these memories to personalize your advice. If you learn something new and important about the user
(a food preference, a milestone, a habit, an injury, a life event that affects their diet),
add it to your response prefixed with [MEMORY]: so I can save it.
Example: [MEMORY]: User is training for a marathon in October
Only add truly important, lasting facts — not every detail of every meal.
"""
    else:
        system_prompt += """

If you learn something important about the user during this conversation
(a food preference, a milestone, a habit, an injury, a life event),
add it to your response prefixed with [MEMORY]: so I can save it for future conversations.
Example: [MEMORY]: User is lactose intolerant but can handle hard cheese
Only add truly important, lasting facts — not temporary details.
"""

    # Add today's data as context
    meal_summary = ""
    if today_meals:
        meal_lines = []
        for m in today_meals:
            meal_lines.append(f"- {m.get('meal_type', 'meal').title()}: {m.get('description', 'logged meal')} "
                            f"({m.get('calories', 0)} cal, {m.get('protein_g', 0)}g P, "
                            f"{m.get('carbs_g', 0)}g C, {m.get('fat_g', 0)}g F)")
        meal_summary = "\n".join(meal_lines)

    context = f"""
TODAY'S LOG ({today}):
Meals logged: {today_totals.get('meal_count', 0)}
Calories: {today_totals.get('total_calories', 0)} / {user.get('calorie_target', '?')} kcal
Protein: {today_totals.get('total_protein', 0)} / {user.get('protein_g', '?')}g
Carbs: {today_totals.get('total_carbs', 0)} / {user.get('carbs_g', '?')}g
Fat: {today_totals.get('total_fat', 0)} / {user.get('fat_g', '?')}g
{('Meals:' + chr(10) + meal_summary) if meal_summary else ''}
"""

    messages = [
        {'role': 'system', 'content': system_prompt + "\n" + context},
    ]

    # Add conversation history for continuity (last 20 messages)
    history = db.get_chat_history(user_id, conversation_id=conversation_id)
    for h in history[-20:]:
        messages.append({'role': h['role'], 'content': h['content']})

    messages.append({'role': 'user', 'content': user_message})

    # Store user message
    db.add_chat_message(user_id, 'user', user_message, conversation_id)

    try:
        response = run_async(ai_proxy.chat(
            provider=user['ai_provider'],
            api_key=user['ai_api_key'],
            model=user['ai_model'],
            messages=messages
        ))

        # Extract and save any [MEMORY] tags from AI response
        memory_pattern = _re.compile(r'\[MEMORY\]:\s*(.+?)(?:\n|$)')
        found_memories = memory_pattern.findall(response)
        for fact in found_memories:
            db.add_chat_memory(user_id, fact.strip())

        # Clean [MEMORY] tags from visible response
        clean_response = memory_pattern.sub('', response).strip()

        # Store AI response (clean version)
        db.add_chat_message(user_id, 'assistant', clean_response, conversation_id)

        return jsonify({
            'response': clean_response,
            'conversation_id': conversation_id,
            'memories_saved': len(found_memories),
        })

    except Exception as e:
        return jsonify({'error': f'AI error: {str(e)}'}), 500


@app.route('/api/users/<int:user_id>/chat/intro', methods=['POST'])
def api_chat_intro(user_id):
    """Generate the coach's first introductory message — a personal trainer meet-and-greet."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if not user.get('ai_api_key'):
        return jsonify({'error': 'No API key configured'}), 400

    prefs = db.get_user_preferences(user_id)
    coach_name = user.get('coach_name', 'Coach')

    # Build a rich intro prompt
    goal_labels = {
        'lose_fat': 'lose body fat',
        'gain_muscle': 'build muscle',
        'maintain': 'maintain their current weight',
        'recomp': 'do a body recomposition (lose fat + gain muscle)',
    }
    goal_text = goal_labels.get(user.get('goal_type', ''), 'reach their fitness goals')

    diet_list = prefs.get('dietary_restrictions', []) if prefs else []
    allergy_list = prefs.get('allergies', []) if prefs else []
    cuisine_list = prefs.get('cuisine_preferences', []) if prefs else []

    intro_prompt = f"""You are {coach_name}, a warm, personable personal nutrition coach meeting your new client for the first time.

This is your INTRODUCTION message. You're like a personal trainer at the first session — excited, genuine, professional but casual.

CLIENT PROFILE:
- Name: {user.get('name', 'there')}
- Age: {user.get('age', 'unknown')}
- Sex: {user.get('sex', 'unknown')}
- Current weight: {user.get('weight_kg', '?')} kg
- Height: {user.get('height_cm', '?')} cm
- Activity level: {user.get('activity_level', 'moderate')}
- Goal: {goal_text}
- Target weight: {user.get('goal_weight_kg', 'not set')} kg
- Timeline: {user.get('goal_timeline_weeks', '?')} weeks
- Calorie target: {user.get('calorie_target', '?')} kcal/day
- Protein: {user.get('protein_g', '?')}g / Carbs: {user.get('carbs_g', '?')}g / Fat: {user.get('fat_g', '?')}g
{f'- Dietary restrictions: {", ".join(diet_list)}' if diet_list else ''}
{f'- Allergies: {", ".join(allergy_list)}' if allergy_list else ''}
{f'- Favorite cuisines: {", ".join(cuisine_list)}' if cuisine_list else ''}
{f'- Notes: {prefs.get("notes", "")}' if prefs and prefs.get('notes') else ''}

INSTRUCTIONS FOR YOUR INTRO:
1. Greet them by name warmly — like meeting a friend, not a corporate onboarding
2. Introduce yourself by YOUR name ({coach_name}) and express genuine excitement to work together
3. Briefly reflect back what you know about them (goal, current state) to show you've been "briefed"
4. Acknowledge their specific dietary needs/restrictions if any
5. Share your coaching style: practical, no-BS, encouraging, always honest
6. Ask 3-4 specific personal questions to learn more about them — things like:
   - What's their biggest struggle with food/nutrition?
   - What does a typical day of eating look like?
   - Any foods they absolutely love or can't live without?
   - What motivated them to start tracking?
   - What's their personality type? Are they self-disciplined or do they need a kick?
   - What coaching style do they prefer? (Gentle encouragement? Drill sergeant? Tough love? Bubbly cheerleader? Science nerd? Chill buddy?)
7. End with something motivating but real — not generic "you got this!" but specific to their goal
8. Keep it conversational, warm, and under 300 words
9. Use markdown formatting (## for section headers, **bold** for emphasis, - for lists)
10. Make sure to ask about their preferred coaching personality — this is KEY for how you'll communicate going forward

Remember: You're building rapport. This person hired YOU. Make them feel seen and heard."""

    # Create a conversation for this intro
    conv_id = db.create_conversation(user_id, f"Getting to know {user.get('name', 'you')}")

    messages = [
        {'role': 'system', 'content': intro_prompt},
        {'role': 'user', 'content': f"Hi {coach_name}! I just signed up and I'm ready to start my journey."},
    ]

    try:
        response = run_async(ai_proxy.chat(
            provider=user['ai_provider'],
            api_key=user['ai_api_key'],
            model=user['ai_model'],
            messages=messages
        ))

        # Store the exchange
        import re as _re
        memory_pattern = _re.compile(r'\[MEMORY\]:\s*(.+?)(?:\n|$)')
        found_memories = memory_pattern.findall(response)
        for fact in found_memories:
            db.add_chat_memory(user_id, fact.strip())
        clean_response = memory_pattern.sub('', response).strip()

        db.add_chat_message(user_id, 'user', f"Hi {coach_name}! I just signed up and I'm ready to start my journey.", conv_id)
        db.add_chat_message(user_id, 'assistant', clean_response, conv_id)

        return jsonify({
            'response': clean_response,
            'conversation_id': conv_id,
        })

    except Exception as e:
        return jsonify({'error': f'AI error: {str(e)}'}), 500


@app.route('/api/users/<int:user_id>/chat/history', methods=['GET'])
def api_chat_history(user_id):
    conv_id = request.args.get('conversation_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    history = db.get_chat_history(user_id, limit, conversation_id=conv_id)
    return jsonify(history)


@app.route('/api/users/<int:user_id>/chat/clear', methods=['POST'])
def api_clear_chat(user_id):
    db.clear_chat_history(user_id)
    return jsonify({'ok': True})


# ─── Chat Memory ──────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/memories', methods=['GET'])
def api_get_memories(user_id):
    memories = db.get_chat_memories(user_id)
    return jsonify(memories)


@app.route('/api/users/<int:user_id>/memories/<int:memory_id>', methods=['DELETE'])
def api_delete_memory(user_id, memory_id):
    db.delete_chat_memory(memory_id)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/memories/clear', methods=['POST'])
def api_clear_memories(user_id):
    db.clear_chat_memories(user_id)
    return jsonify({'ok': True})


# ─── Workouts ──────────────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/workouts', methods=['GET'])
def api_get_workouts(user_id):
    """Get workouts for a date or date range."""
    workout_date = request.args.get('date')
    start = request.args.get('start')
    end = request.args.get('end')

    if start and end:
        workouts = db.get_workouts_range(user_id, start, end)
    elif workout_date:
        workouts = db.get_workouts_for_date(user_id, workout_date)
    else:
        workouts = db.get_workouts_for_date(user_id, date.today().isoformat())

    return jsonify(workouts)


@app.route('/api/users/<int:user_id>/workouts', methods=['POST'])
def api_add_workout(user_id):
    """Log a workout."""
    data = request.json or {}
    workout_type = data.get('workout_type', '').strip()
    if not workout_type:
        return jsonify({'error': 'Workout type required'}), 400

    workout_id = db.add_workout(
        user_id=user_id,
        workout_date=data.get('workout_date', date.today().isoformat()),
        workout_type=workout_type,
        duration_min=data.get('duration_min'),
        intensity=data.get('intensity', 'moderate'),
        notes=data.get('notes'),
    )
    return jsonify({'id': workout_id, 'ok': True})


@app.route('/api/users/<int:user_id>/workouts/<int:workout_id>', methods=['DELETE'])
def api_delete_workout(user_id, workout_id):
    db.delete_workout(workout_id)
    return jsonify({'ok': True})


@app.route('/api/users/<int:user_id>/workout-stats', methods=['GET'])
def api_workout_stats(user_id):
    """Get workout summary stats."""
    last = db.get_last_workout(user_id)
    streak_30 = db.get_workout_streak(user_id, 30)
    # Get this week's workouts
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_workouts = db.get_workouts_range(user_id, week_start.isoformat(), today.isoformat())

    return jsonify({
        'last_workout': last,
        'days_this_month': streak_30,
        'workouts_this_week': len(week_workouts),
        'week_workouts': week_workouts,
    })


# ─── Daily Coach Nudge ────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/daily-nudge', methods=['GET'])
def api_daily_nudge(user_id):
    """Get the daily coach nudge — cached per day, generated once via AI."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    prefs = db.get_user_preferences(user_id)
    nudge_freq = prefs.get('nudge_frequency', 'daily') if prefs else 'daily'

    # Check if nudges are disabled
    if nudge_freq == 'off':
        return jsonify({'nudge': None, 'disabled': True})

    # Check frequency
    today = date.today()
    cached = db.get_daily_nudge(user_id, today.isoformat())
    if cached:
        return jsonify({'nudge': cached['message'], 'cached': True})

    # Check if it's a nudge day based on frequency
    if nudge_freq == 'every_other_day':
        day_num = (today - date(2024, 1, 1)).days
        if day_num % 2 != 0:
            return jsonify({'nudge': None, 'not_today': True})
    elif nudge_freq == 'weekly':
        if today.weekday() != 0:  # Only Monday
            return jsonify({'nudge': None, 'not_today': True})

    # No API key = can't generate
    if not user.get('ai_api_key'):
        return jsonify({'nudge': None, 'no_key': True})

    # Gather context for AI
    today_iso = today.isoformat()
    today_totals = db.get_daily_totals(user_id, today_iso)
    today_meals = db.get_meals_for_date(user_id, today_iso)
    last_workout = db.get_last_workout(user_id)
    last_weighin = db.get_last_weighin(user_id)
    workout_streak = db.get_workout_streak(user_id, 30)
    memories = db.get_chat_memories(user_id, limit=15)

    # Recent meal patterns (last 3 days)
    recent_meals = db.get_meals_range(
        user_id,
        (today - timedelta(days=3)).isoformat(),
        today_iso
    )

    # Build context
    meals_logged_today = len(today_meals)
    cal_today = today_totals.get('total_calories', 0)
    target_cal = user.get('calorie_target', 2000)

    workout_context = "No workouts logged yet."
    if last_workout:
        days_since = (today - date.fromisoformat(last_workout['workout_date'])).days
        if days_since == 0:
            workout_context = f"Already worked out today: {last_workout['workout_type']} ({last_workout.get('duration_min', '?')} min)"
        elif days_since == 1:
            workout_context = f"Last workout was yesterday: {last_workout['workout_type']}"
        else:
            workout_context = f"Last workout was {days_since} days ago: {last_workout['workout_type']}"
    workout_context += f"\nWorkout days this month: {workout_streak}/30"

    weighin_context = ""
    if last_weighin:
        days_since_w = (today - date.fromisoformat(last_weighin['log_date'])).days
        weighin_context = f"Last weigh-in: {last_weighin['weight_kg']}kg, {days_since_w} days ago"

    memory_text = ""
    if memories:
        memory_text = "Things I remember about this person:\n" + "\n".join(f"- {m['fact']}" for m in memories)

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_of_week = day_names[today.weekday()]

    coach_name = user.get('coach_name', 'Coach')

    nudge_prompt = f"""You are {coach_name}, a personal nutrition and fitness coach. Generate a brief daily check-in message for your client.

CLIENT: {user.get('name', 'there')}
TODAY: {day_of_week}, {today_iso}
GOAL: {user.get('goal_type', 'maintain')} | Target: {target_cal} kcal/day

TODAY'S STATUS:
- Meals logged so far: {meals_logged_today} ({cal_today} cal of {target_cal} target)
- {workout_context}
{weighin_context}

{memory_text}

YOUR DAILY NUDGE RULES:
1. Keep it SHORT — 2-4 sentences max. This is a dashboard card, not a conversation.
2. Be warm, genuine, and specific to their situation RIGHT NOW
3. Vary your approach by day:
   - Monday: Fresh start energy, set the week's intention
   - Mid-week: Check consistency, encourage momentum
   - Friday: Celebrate the week, plan for weekend temptations
   - Weekend: Acknowledge flexibility while staying mindful
4. If they haven't logged meals today, gently encourage it (without nagging)
5. If they haven't worked out recently, ask what movement sounds good (don't guilt-trip)
6. If they worked out today, celebrate it specifically
7. Ask ONE simple question to drive engagement (yes/no or simple answer)
8. NEVER recommend supplements, detoxes, cleanses, or any products
9. NEVER push fad diets, elimination diets without medical reason, or "superfood" nonsense
10. Be a real coach — practical, warm, evidence-based

Examples of good nudges:
- "Hey [name]! Wednesday already — you're halfway through the week. I see you haven't logged yet today. What's on the menu? Even a quick photo helps us stay on track."
- "Morning! You crushed that workout yesterday. How are your muscles feeling? Remember to get some protein in early today."
- "Happy Friday [name]! You've been consistent all week — that's what counts more than any single meal. Got any fun plans this weekend?"

DO NOT include any greeting like "Good morning" if it's afternoon/evening — just be natural.
DO NOT use emojis excessively — one or two max.
DO NOT include markdown formatting — plain text only.
"""

    try:
        response = run_async(ai_proxy.chat(
            provider=user['ai_provider'],
            api_key=user['ai_api_key'],
            model=user['ai_model'],
            messages=[
                {'role': 'system', 'content': nudge_prompt},
                {'role': 'user', 'content': 'Generate today\'s check-in nudge.'},
            ]
        ))

        # Clean up response
        nudge_text = response.strip()
        # Remove any markdown formatting the AI might add
        nudge_text = nudge_text.replace('**', '').replace('##', '').replace('# ', '')

        # Cache it
        db.save_daily_nudge(user_id, today_iso, nudge_text)

        return jsonify({'nudge': nudge_text, 'cached': False})

    except Exception as e:
        return jsonify({'nudge': None, 'error': str(e)}), 500


# ─── Macro Calculator ──────────────────────────────────────────────────────

@app.route('/api/users/<int:user_id>/weighin-status', methods=['GET'])
def api_weighin_status(user_id):
    """Check if user is due for a weigh-in based on their frequency setting."""
    user = db.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    prefs = db.get_user_preferences(user_id)
    frequency = prefs.get('weighin_frequency', 'weekly') if prefs else 'weekly'
    last = db.get_last_weighin(user_id)

    is_due = False
    days_since = None
    if not last:
        is_due = True
    else:
        from datetime import date as _date
        last_date = _date.fromisoformat(last['log_date'])
        days_since = (date.today() - last_date).days
        if frequency == 'daily' and days_since >= 1:
            is_due = True
        elif frequency == 'weekly' and days_since >= 7:
            is_due = True
        elif frequency == 'biweekly' and days_since >= 14:
            is_due = True
        elif frequency == 'monthly' and days_since >= 30:
            is_due = True

    return jsonify({
        'is_due': is_due,
        'frequency': frequency,
        'last_weighin': last,
        'days_since': days_since,
    })


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """Get all app-level settings."""
    return jsonify({
        'app_name': db.get_setting('app_name', 'NutriTracker'),
    })


@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    """Update app-level settings."""
    data = request.json or {}
    if 'app_name' in data:
        name = data['app_name'].strip()
        if name:
            db.set_setting('app_name', name)
    return jsonify({'ok': True})


@app.route('/api/calculate-targets', methods=['POST'])
def api_calculate_targets():
    """Calculate calorie/macro targets from profile data (no user needed)."""
    data = request.json or {}
    targets = food_analyzer.calculate_targets(data)
    return jsonify(targets)


@app.route('/api/calculate-body-fat', methods=['POST'])
def api_calculate_body_fat():
    """Calculate Navy method body fat from measurements."""
    data = request.json or {}
    bf = food_analyzer.calculate_navy_body_fat(
        sex=data.get('sex', 'male'),
        neck_cm=data.get('neck_cm', 0),
        waist_cm=data.get('waist_cm', 0),
        hip_cm=data.get('hip_cm'),
        height_cm=data.get('height_cm', 170)
    )
    return jsonify({'body_fat_pct': bf})
