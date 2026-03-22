"""
Food Analyzer — Vision-Based Nutritional Analysis
===================================================
Constructs prompts for AI vision models to analyze food photos.
Designed to minimize hallucination through:
  - Requesting confidence ranges, not exact numbers
  - Asking for item-by-item breakdown
  - Flagging ambiguous items for user review
  - Cross-referencing user descriptions
"""

import json
from . import ai_proxy
from . import food_database

# The food analysis prompt is carefully engineered to:
# 1. Return structured JSON (parseable)
# 2. Use ranges instead of false precision
# 3. Flag low-confidence items
# 4. Ask clarifying questions when uncertain

FOOD_ANALYSIS_PROMPT = """You are a nutritional analysis assistant. Analyze the food in this photo and provide a detailed macro breakdown.

CRITICAL RULES:
1. NEVER invent food items that aren't clearly visible
2. If you can't identify something, say so — don't guess
3. Use calorie RANGES (e.g., 300-400) not exact numbers
4. Estimate portion sizes conservatively
5. Flag anything you're uncertain about

{user_context}

Respond ONLY with valid JSON in this exact format:
{{
  "items": [
    {{
      "name": "Grilled chicken breast",
      "estimated_quantity": "~6 oz / 170g",
      "calories_low": 250,
      "calories_high": 300,
      "protein_g": 45,
      "carbs_g": 0,
      "fat_g": 6,
      "fiber_g": 0,
      "confidence": 0.85,
      "notes": "Appears skinless, grilled without oil"
    }}
  ],
  "totals": {{
    "calories_low": 250,
    "calories_high": 300,
    "protein_g": 45,
    "carbs_g": 0,
    "fat_g": 6,
    "fiber_g": 0
  }},
  "overall_confidence": 0.85,
  "questions": ["Is that olive oil or butter on the vegetables?"],
  "meal_description": "Grilled chicken breast with steamed vegetables"
}}

CONFIDENCE SCALE:
- 0.9+ = Very confident (clear, common food, standard portion)
- 0.7-0.9 = Moderately confident (identifiable but portion unclear)
- 0.5-0.7 = Low confidence (partially visible, mixed dish, unclear cooking method)
- Below 0.5 = Guessing (flag for user review)
"""


async def analyze_food_photo(user, image_path, user_description=None,
                             user_preferences=None, nix_id=None, nix_key=None):
    """
    Analyze a food photo using AI vision, then cross-reference with food databases.

    Flow:
    1. AI vision identifies the food items
    2. For each item, search food databases for exact match
    3. If database has exact data (Big Mac → McDonald's), replace AI estimates
    4. If generic food (chicken breast), keep AI data but flag for follow-up
    5. Return combined results with data sources

    Args:
        user: User dict from database (contains AI config)
        image_path: Path to the food photo
        user_description: Optional user text like "chicken salad from Chipotle"
        user_preferences: Optional preferences dict for dietary context
        nix_id: Optional Nutritionix app ID
        nix_key: Optional Nutritionix app key

    Returns:
        dict with 'items', 'totals', 'confidence', 'questions', 'raw_response'
    """
    # Determine which provider/model to use for vision
    vision_provider = user.get('vision_provider') or user.get('ai_provider', 'google')
    vision_model = user.get('vision_model') or user.get('ai_model', '')
    vision_key = user.get('vision_api_key') or user.get('ai_api_key', '')

    # Check if the primary model supports vision
    if not ai_proxy.has_vision(vision_provider, vision_model):
        if user.get('vision_provider') and user.get('vision_api_key'):
            vision_provider = user['vision_provider']
            vision_model = user['vision_model']
            vision_key = user['vision_api_key']
        else:
            return {
                'error': True,
                'message': 'Your selected model does not support vision. '
                          'Please configure a vision-capable model in Settings.'
            }

    # Use enhanced prompt that instructs AI to identify branded foods
    prompt = food_database.build_enhanced_analysis_prompt(user_preferences)

    # Build context from user description
    if user_description:
        prompt += f'\n\nThe user describes this meal as: "{user_description}"\nUse this to help identify items, but rely primarily on what you SEE in the photo.'

    messages = [
        {'role': 'system', 'content': prompt},
        {'role': 'user', 'content': user_description or 'Analyze this food photo.'}
    ]

    try:
        raw_response = await ai_proxy.chat(
            provider=vision_provider,
            api_key=vision_key,
            model=vision_model,
            messages=messages,
            image_path=image_path
        )

        parsed = ai_proxy._extract_json(raw_response)

        if parsed is None:
            return {
                'error': True,
                'message': 'Could not parse AI response. Try again or adjust your photo.',
                'raw_response': raw_response
            }

        # ─── Cross-reference with food databases ─────────────────────────
        items = []
        total_cal = 0
        total_protein = 0
        total_carbs = 0
        total_fat = 0
        total_fiber = 0
        all_questions = list(parsed.get('questions', []))

        for ai_item in parsed.get('items', []):
            item_name = ai_item.get('name', 'Unknown item')
            item_brand = ai_item.get('brand', '')
            quantity = ai_item.get('estimated_quantity', '')
            weight_g = ai_item.get('estimated_weight_g')

            # Try database lookup for this item
            search_query = f"{item_brand} {item_name}".strip() if item_brand else item_name
            db_match = await food_database.lookup_food(
                food_name=search_query,
                portion_desc=quantity,
                nutritionix_id=nix_id,
                nutritionix_key=nix_key,
            )

            if db_match and db_match.get('calories', 0) > 0:
                # Database has real data — use it instead of AI estimate
                item_data = {
                    'name': db_match.get('name', item_name),
                    'brand': db_match.get('brand', item_brand),
                    'quantity': db_match.get('serving_size', quantity),
                    'calories': db_match['calories'],
                    'protein_g': db_match['protein_g'],
                    'carbs_g': db_match['carbs_g'],
                    'fat_g': db_match['fat_g'],
                    'fiber_g': db_match.get('fiber_g', 0),
                    'confidence': 0.95,  # Database data is high confidence
                    'data_source': db_match.get('source', 'database'),
                    'match_type': db_match.get('match_type', 'database'),
                }
            else:
                # No database match — use AI estimates
                item_cal_low = ai_item.get('calories_low', 0)
                item_cal_high = ai_item.get('calories_high', 0)
                item_data = {
                    'name': item_name,
                    'brand': item_brand,
                    'quantity': quantity,
                    'calories': round((item_cal_low + item_cal_high) / 2),
                    'protein_g': round(ai_item.get('protein_g', 0), 1),
                    'carbs_g': round(ai_item.get('carbs_g', 0), 1),
                    'fat_g': round(ai_item.get('fat_g', 0), 1),
                    'fiber_g': round(ai_item.get('fiber_g', 0), 1),
                    'confidence': ai_item.get('confidence', 0.5),
                    'data_source': 'ai_estimate',
                    'match_type': 'ai',
                }

            # Check if this food needs follow-up questions
            food_type = food_database.detect_food_type(item_name)
            if food_type.get('needs_followup') and food_type.get('followup_questions'):
                item_data['needs_followup'] = True
                item_data['followup_questions'] = food_type['followup_questions']
                for q in food_type['followup_questions']:
                    if q not in all_questions:
                        all_questions.append(q)

            items.append(item_data)
            total_cal += item_data['calories']
            total_protein += item_data['protein_g']
            total_carbs += item_data['carbs_g']
            total_fat += item_data['fat_g']
            total_fiber += item_data['fiber_g']

        # Calculate overall confidence (weighted by calorie contribution)
        if items and total_cal > 0:
            weighted_conf = sum(
                i['confidence'] * i['calories'] / total_cal for i in items
            )
        else:
            weighted_conf = parsed.get('overall_confidence', 0.5)

        # Check if any items used database data
        has_db_data = any(i.get('data_source') != 'ai_estimate' for i in items)

        return {
            'error': False,
            'items': items,
            'totals': {
                'calories': round(total_cal),
                'calories_low': round(total_cal * 0.9) if not has_db_data else round(total_cal),
                'calories_high': round(total_cal * 1.1) if not has_db_data else round(total_cal),
                'protein_g': round(total_protein, 1),
                'carbs_g': round(total_carbs, 1),
                'fat_g': round(total_fat, 1),
                'fiber_g': round(total_fiber, 1),
            },
            'confidence': round(weighted_conf, 2),
            'questions': all_questions,
            'description': parsed.get('meal_description', ''),
            'has_database_match': has_db_data,
            'raw_response': raw_response,
        }

    except Exception as e:
        return {
            'error': True,
            'message': f'AI analysis failed: {str(e)}',
        }


def build_user_system_prompt(user, preferences=None):
    """
    Build a personalized system prompt for the AI based on user profile
    and lifestyle preferences. Used for chat and meal suggestions.
    """
    unit = user.get('unit_system', 'metric')

    if unit == 'imperial':
        height_str = f"{user.get('height_cm', 0) / 2.54:.0f} inches" if user.get('height_cm') else 'unknown'
        weight_str = f"{user.get('weight_kg', 0) * 2.205:.0f} lbs" if user.get('weight_kg') else 'unknown'
        goal_weight = f"{user.get('goal_weight_kg', 0) * 2.205:.0f} lbs" if user.get('goal_weight_kg') else 'not set'
    else:
        height_str = f"{user.get('height_cm', 0):.0f} cm" if user.get('height_cm') else 'unknown'
        weight_str = f"{user.get('weight_kg', 0):.1f} kg" if user.get('weight_kg') else 'unknown'
        goal_weight = f"{user.get('goal_weight_kg', 0):.1f} kg" if user.get('goal_weight_kg') else 'not set'

    goal_labels = {
        'lose_fat': 'Lose body fat',
        'gain_muscle': 'Build muscle / lean bulk',
        'maintain': 'Maintain current weight',
        'recomp': 'Body recomposition (lose fat + gain muscle)',
    }

    activity_labels = {
        'sedentary': 'Sedentary (desk job, minimal exercise)',
        'light': 'Lightly active (1-3 days/week exercise)',
        'moderate': 'Moderately active (3-5 days/week exercise)',
        'active': 'Active (6-7 days/week exercise)',
        'very_active': 'Very active (athlete / physical job + training)',
    }

    # Build lifestyle section from preferences
    lifestyle_section = ""
    if preferences:
        freq_labels = {
            'daily': 'Every day',
            'few_times_week': 'A few times a week',
            'weekly': 'About once a week',
            'monthly': 'About once a month',
            'rarely': 'Rarely',
            'never': 'Never',
        }
        budget_labels = {
            'budget': 'Budget-conscious',
            'moderate': 'Moderate spending',
            'no_limit': 'No budget constraints',
        }

        diet_list = preferences.get('dietary_restrictions', [])
        allergy_list = preferences.get('allergies', [])
        cuisine_list = preferences.get('cuisine_preferences', [])
        fav_list = preferences.get('favorite_foods', [])
        dislike_list = preferences.get('disliked_foods', [])

        lifestyle_section = f"""
LIFESTYLE & PREFERENCES:
- Dietary restrictions: {', '.join(diet_list) if diet_list else 'None'}
- Food allergies: {', '.join(allergy_list) if allergy_list else 'None'}
- Preferred cuisines: {', '.join(cuisine_list) if cuisine_list else 'No preference'}
- Favorite foods: {', '.join(fav_list) if fav_list else 'Not specified'}
- Disliked foods: {', '.join(dislike_list) if dislike_list else 'Not specified'}
- Cooking frequency: {freq_labels.get(preferences.get('cooking_frequency', ''), 'Unknown')}
- Dining out: {freq_labels.get(preferences.get('dining_out_frequency', ''), 'Unknown')}
- Fast food: {freq_labels.get(preferences.get('fast_food_frequency', ''), 'Unknown')}
- Travel: {freq_labels.get(preferences.get('travel_frequency', ''), 'Unknown')}
- Budget: {budget_labels.get(preferences.get('budget_preference', ''), 'Moderate')}
{f'- Notes: {preferences["notes"]}' if preferences.get('notes') else ''}

IMPORTANT: NEVER suggest foods that conflict with the user's dietary restrictions or allergies.
When suggesting meals, consider their cooking frequency, dining-out habits, and budget.
If they travel often, include portable/travel-friendly meal ideas.
"""

    coach_name = user.get('coach_name', 'Coach')
    prompt = f"""You are {coach_name}, a personal nutrition and fitness coach. Your name is {coach_name} — the user chose this name for you, so use it naturally.
Be direct, practical, and encouraging without being patronizing. Be warm and personable, like a real trainer who genuinely cares.

USER PROFILE:
- Name: {user.get('name', 'User')}
- Age: {user.get('age', 'unknown')}
- Sex: {user.get('sex', 'unknown')}
- Height: {height_str}
- Current weight: {weight_str}
- Body fat: {user.get('body_fat_pct', 'unknown')}%
- Activity level: {activity_labels.get(user.get('activity_level', ''), 'unknown')}

GOALS:
- Goal: {goal_labels.get(user.get('goal_type', ''), 'unknown')}
- Target weight: {goal_weight}
- Timeline: {user.get('goal_timeline_weeks', '?')} weeks
- Approach: {user.get('goal_aggression', 'moderate')}

DAILY TARGETS:
- Calories: {user.get('calorie_target', 'not calculated')} kcal
- Protein: {user.get('protein_g', '?')}g
- Carbs: {user.get('carbs_g', '?')}g
- Fat: {user.get('fat_g', '?')}g
{lifestyle_section}
RULES:
1. Base advice on the user's actual data, goals, and preferences above
2. Be honest about limitations — you're not a doctor or registered dietitian
3. Flag any health concerns that should involve a medical professional
4. Give practical, actionable advice tailored to their lifestyle
5. When discussing calories/macros, acknowledge estimation uncertainty
6. Celebrate progress but don't sugarcoat setbacks
7. Suggest foods they'll actually enjoy based on their preferences
8. If they eat out often, suggest healthier restaurant options
9. If they cook rarely, suggest simple meal prep ideas
10. For travelers, recommend portable high-protein options

ANTI-SCAM COACHING RULES (NON-NEGOTIABLE):
- NEVER recommend supplements, protein powders, or any products to buy
- NEVER suggest "detox" diets, cleanses, juice fasts, or "reset" programs — they are medically baseless
- NEVER endorse fad diets (carnivore, alkaline, blood type, etc.) unless medically prescribed
- NEVER use fear-mongering about food ("toxic", "inflammatory", "poisonous") — all food is chemistry
- NEVER recommend elimination diets without medical justification
- NEVER push "superfoods" — no single food is magic; overall patterns matter
- NEVER suggest "boosting metabolism" with foods/drinks — that's not how metabolism works
- NEVER recommend waist trainers, body wraps, fat-burning creams, or similar scams
- If the user asks about any of the above, explain why it's not evidence-based and redirect to what actually works: consistent caloric balance, adequate protein, regular movement, sufficient sleep, and stress management
- The ONLY things that reliably help: eating appropriate calories, getting enough protein, moving your body regularly, sleeping well, managing stress, and staying hydrated with water
- Consistency beats perfection. Small sustainable changes beat dramatic short-term ones. Always.
"""
    return prompt


def calculate_targets(user):
    """
    Calculate calorie and macro targets based on user profile.
    Uses Mifflin-St Jeor equation for BMR, then applies activity
    multiplier and goal adjustment.

    Returns dict with calorie_target, protein_g, carbs_g, fat_g.
    """
    weight = user.get('weight_kg', 70)
    height = user.get('height_cm', 170)
    age = user.get('age', 30)
    sex = user.get('sex', 'male')

    # Mifflin-St Jeor BMR
    if sex == 'female':
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5

    # Activity multiplier
    activity_multipliers = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9,
    }
    tdee = bmr * activity_multipliers.get(user.get('activity_level', 'moderate'), 1.55)

    # Goal adjustment
    goal = user.get('goal_type', 'maintain')
    aggression = user.get('goal_aggression', 'moderate')

    deficit_map = {
        'lose_fat': {'conservative': 0.85, 'moderate': 0.80, 'aggressive': 0.75},
        'gain_muscle': {'conservative': 1.05, 'moderate': 1.10, 'aggressive': 1.15},
        'maintain': {'conservative': 1.0, 'moderate': 1.0, 'aggressive': 1.0},
        'recomp': {'conservative': 0.95, 'moderate': 0.90, 'aggressive': 0.85},
    }

    multiplier = deficit_map.get(goal, {}).get(aggression, 1.0)
    calorie_target = round(tdee * multiplier)

    # Macro split based on goal
    if goal in ('lose_fat', 'recomp'):
        # High protein, moderate fat, fill rest with carbs
        protein_g = round(weight * 2.2)  # ~1g per lb bodyweight
        fat_g = round(calorie_target * 0.25 / 9)
        remaining_cal = calorie_target - (protein_g * 4) - (fat_g * 9)
        carbs_g = round(max(remaining_cal, 0) / 4)
    elif goal == 'gain_muscle':
        protein_g = round(weight * 2.0)
        fat_g = round(calorie_target * 0.25 / 9)
        remaining_cal = calorie_target - (protein_g * 4) - (fat_g * 9)
        carbs_g = round(max(remaining_cal, 0) / 4)
    else:  # maintain
        protein_g = round(weight * 1.6)
        fat_g = round(calorie_target * 0.30 / 9)
        remaining_cal = calorie_target - (protein_g * 4) - (fat_g * 9)
        carbs_g = round(max(remaining_cal, 0) / 4)

    return {
        'calorie_target': calorie_target,
        'protein_g': protein_g,
        'carbs_g': carbs_g,
        'fat_g': fat_g,
        'bmr': round(bmr),
        'tdee': round(tdee),
    }


def calculate_navy_body_fat(sex, neck_cm, waist_cm, hip_cm=None, height_cm=170):
    """
    Calculate body fat % using the U.S. Navy method.
    Provides an objective cross-reference for user-reported body fat.

    Male: 86.010 × log10(waist - neck) - 70.041 × log10(height) + 36.76
    Female: 163.205 × log10(waist + hip - neck) - 97.684 × log10(height) - 78.387
    """
    import math

    if sex == 'male':
        if waist_cm <= neck_cm:
            return None
        bf = 86.010 * math.log10(waist_cm - neck_cm) - 70.041 * math.log10(height_cm) + 36.76
    elif sex == 'female':
        if not hip_cm or (waist_cm + hip_cm) <= neck_cm:
            return None
        bf = 163.205 * math.log10(waist_cm + hip_cm - neck_cm) - 97.684 * math.log10(height_cm) - 78.387
    else:
        # Use male formula as default
        if waist_cm <= neck_cm:
            return None
        bf = 86.010 * math.log10(waist_cm - neck_cm) - 70.041 * math.log10(height_cm) + 36.76

    return round(max(bf, 2.0), 1)  # Floor at 2% (essential fat)
