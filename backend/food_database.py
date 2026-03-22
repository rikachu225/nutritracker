"""
Food Database — Real-World Nutritional Data Lookup
====================================================
Searches USDA FoodData Central and Nutritionix for exact macro data.
Falls back gracefully: Nutritionix (branded/restaurant) → USDA (raw ingredients) → None.

When AI vision detects "Big Mac", we pull McDonald's exact macros.
When it detects "chicken breast", we pull USDA data + ask for portion/cooking method.
"""

import httpx
import re
from pathlib import Path

API_TIMEOUT = 10  # Fast timeout — these are supplementary lookups

# ─── USDA FoodData Central (free, no key needed for basic) ───────────────────

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
USDA_API_KEY = "DEMO_KEY"  # Free tier, 30 req/hr. User can upgrade in settings.


async def search_usda(query, max_results=5):
    """
    Search USDA FoodData Central for nutritional data.
    Returns list of food matches with macros per 100g.
    """
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{USDA_BASE}/foods/search",
                params={
                    'query': query,
                    'pageSize': max_results,
                    'api_key': USDA_API_KEY,
                }
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for food in data.get('foods', []):
                nutrients = {n['nutrientName']: n.get('value', 0)
                             for n in food.get('foodNutrients', [])}

                results.append({
                    'source': 'usda',
                    'fdc_id': food.get('fdcId'),
                    'name': food.get('description', ''),
                    'brand': food.get('brandName', ''),
                    'category': food.get('foodCategory', ''),
                    'serving_size': '100g',  # USDA always per 100g
                    'per_100g': True,
                    'calories': round(nutrients.get('Energy', 0)),
                    'protein_g': round(nutrients.get('Protein', 0), 1),
                    'carbs_g': round(nutrients.get('Carbohydrate, by difference', 0), 1),
                    'fat_g': round(nutrients.get('Total lipid (fat)', 0), 1),
                    'fiber_g': round(nutrients.get('Fiber, total dietary', 0), 1),
                    'sugar_g': round(nutrients.get('Sugars, total including NLEA', 0), 1),
                    'sodium_mg': round(nutrients.get('Sodium, Na', 0)),
                })
            return results

    except Exception as e:
        print(f"  [WARN] USDA search failed: {e}")
        return []


# ─── Nutritionix (branded/restaurant foods) ─────────────────────────────────

NUTRITIONIX_BASE = "https://trackapi.nutritionix.com/v2"


async def search_nutritionix(query, app_id=None, app_key=None):
    """
    Search Nutritionix for branded/restaurant food data.
    Requires app_id and app_key (free tier: 50 req/day).
    Uses the natural language endpoint which is incredibly powerful —
    "Big Mac with large fries and a Coke" returns exact McDonald's data.
    """
    if not app_id or not app_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            # Natural language endpoint — best for conversational food descriptions
            resp = await client.post(
                f"{NUTRITIONIX_BASE}/natural/nutrients",
                headers={
                    'x-app-id': app_id,
                    'x-app-key': app_key,
                    'Content-Type': 'application/json',
                },
                json={'query': query}
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for food in data.get('foods', []):
                results.append({
                    'source': 'nutritionix',
                    'name': food.get('food_name', ''),
                    'brand': food.get('brand_name', ''),
                    'serving_size': f"{food.get('serving_qty', 1)} {food.get('serving_unit', 'serving')}",
                    'serving_weight_g': food.get('serving_weight_grams', 0),
                    'per_100g': False,
                    'calories': round(food.get('nf_calories', 0)),
                    'protein_g': round(food.get('nf_protein', 0), 1),
                    'carbs_g': round(food.get('nf_total_carbohydrate', 0), 1),
                    'fat_g': round(food.get('nf_total_fat', 0), 1),
                    'fiber_g': round(food.get('nf_dietary_fiber', 0), 1),
                    'sugar_g': round(food.get('nf_sugars', 0), 1),
                    'sodium_mg': round(food.get('nf_sodium', 0)),
                    'photo_url': food.get('photo', {}).get('thumb'),
                })
            return results

    except Exception as e:
        print(f"  [WARN] Nutritionix search failed: {e}")
        return []


# ─── Branded Food Detection ─────────────────────────────────────────────────

# Common fast food / restaurant patterns for detection
BRANDED_PATTERNS = {
    'mcdonalds': ["big mac", "mcnugget", "mcflurry", "mcdouble", "egg mcmuffin",
                  "quarter pounder", "filet-o-fish", "mchicken", "happy meal"],
    'burger_king': ["whopper", "impossible whopper", "chicken fries"],
    'wendys': ["baconator", "frosty", "dave's single", "dave's double"],
    'subway': ["footlong", "6 inch", "sub", "meatball marinara"],
    'chipotle': ["burrito bowl", "carnitas", "barbacoa", "sofritas"],
    'starbucks': ["frappuccino", "latte", "caramel macchiato", "cold brew",
                  "pumpkin spice", "americano", "mocha"],
    'chick_fil_a': ["chick-fil-a", "spicy deluxe", "waffle fries"],
    'taco_bell': ["crunchwrap", "chalupa", "gordita", "quesarito"],
    'popeyes': ["popeyes", "chicken sandwich"],
    'dominos': ["domino", "hand tossed", "thin crust"],
    'pizza_hut': ["pizza hut", "stuffed crust"],
    'kfc': ["original recipe", "extra crispy", "famous bowl"],
    'panda_express': ["panda express", "orange chicken", "beijing beef"],
    'in_n_out': ["animal style", "double double", "in-n-out"],
    'five_guys': ["five guys", "cajun fries"],
    'dunkin': ["dunkin", "munchkin", "coolatta"],
}

# Generic foods that need follow-up questions about portion/cooking
GENERIC_FOODS = [
    "chicken breast", "chicken thigh", "chicken wing", "chicken leg",
    "steak", "beef", "ground beef", "pork chop", "pork loin",
    "salmon", "tuna", "shrimp", "tilapia", "cod",
    "rice", "brown rice", "quinoa", "pasta", "bread",
    "broccoli", "spinach", "sweet potato", "potato", "avocado",
    "egg", "eggs", "oatmeal", "greek yogurt", "cottage cheese",
    "almonds", "peanut butter", "olive oil", "butter",
    "banana", "apple", "orange", "berries", "strawberries",
    "milk", "cheese", "protein shake", "protein bar",
]


def detect_food_type(food_description):
    """
    Analyze food description to determine if it's branded/restaurant
    or a generic ingredient that needs follow-up questions.

    Returns:
        dict with:
            'type': 'branded' | 'generic' | 'unknown'
            'brand': str or None
            'needs_followup': bool
            'followup_questions': list of str
    """
    desc_lower = food_description.lower().strip()

    # Check for branded/restaurant foods
    for brand, patterns in BRANDED_PATTERNS.items():
        if any(p in desc_lower for p in patterns):
            return {
                'type': 'branded',
                'brand': brand.replace('_', ' ').title(),
                'needs_followup': False,
                'followup_questions': [],
            }

    # Check for known restaurant names in the description
    restaurant_names = [
        "mcdonald", "burger king", "wendy", "subway", "chipotle",
        "starbucks", "chick-fil-a", "taco bell", "popeye", "domino",
        "pizza hut", "kfc", "panda express", "in-n-out", "five guys",
        "dunkin", "panera", "olive garden", "applebee", "denny",
        "ihop", "waffle house", "arby", "jack in the box", "sonic",
        "whataburger", "carl's jr", "hardee", "el pollo loco",
        "noodles", "pei wei", "sweetgreen", "cava", "wingstop",
    ]
    for name in restaurant_names:
        if name in desc_lower:
            return {
                'type': 'branded',
                'brand': name.title(),
                'needs_followup': False,
                'followup_questions': [],
            }

    # Check for generic foods that need portion/cooking questions
    for food in GENERIC_FOODS:
        if food in desc_lower:
            questions = _get_followup_questions(food, desc_lower)
            return {
                'type': 'generic',
                'brand': None,
                'needs_followup': True,
                'followup_questions': questions,
            }

    return {
        'type': 'unknown',
        'brand': None,
        'needs_followup': True,
        'followup_questions': [
            "What is this food?",
            "Roughly how much (oz, grams, cups, or pieces)?",
        ],
    }


def _get_followup_questions(food, description):
    """Generate relevant follow-up questions based on the food type."""
    questions = []

    # Portion size — always ask unless already specified
    has_quantity = any(unit in description for unit in
                       ['oz', 'ounce', 'gram', 'g ', 'cup', 'piece', 'slice',
                        'tbsp', 'tablespoon', 'tsp', 'teaspoon', 'serving'])
    if not has_quantity:
        questions.append("How much? (oz, grams, cups, or a visual like palm-sized)")

    # Cooking method for proteins
    proteins = ['chicken', 'steak', 'beef', 'pork', 'salmon', 'tuna',
                'shrimp', 'tilapia', 'cod', 'turkey', 'fish']
    if any(p in food for p in proteins):
        has_method = any(m in description for m in
                        ['grilled', 'fried', 'baked', 'roasted', 'sauteed',
                         'steamed', 'air fried', 'boiled', 'raw', 'smoked'])
        if not has_method:
            questions.append("How was it cooked? (grilled, fried, baked, air-fried, etc.)")

    # Additions/toppings
    if any(f in food for f in ['chicken breast', 'steak', 'salmon', 'salad']):
        questions.append("Any oil, butter, sauce, or seasoning added?")

    # Side context
    if any(f in food for f in ['rice', 'pasta', 'potato', 'bread']):
        questions.append("Any butter, oil, or sauce on it?")

    return questions if questions else ["Roughly how much?"]


# ─── Smart Food Lookup ────────────────────────────────────────────────────

async def lookup_food(food_name, portion_desc=None, nutritionix_id=None,
                      nutritionix_key=None, usda_key=None):
    """
    Smart food lookup: tries Nutritionix first (branded), then USDA (raw).

    Args:
        food_name: What the AI identified (e.g., "Big Mac", "chicken breast")
        portion_desc: Optional portion context (e.g., "6 oz grilled")
        nutritionix_id: Optional Nutritionix app ID
        nutritionix_key: Optional Nutritionix app key
        usda_key: Optional USDA API key (uses DEMO_KEY if not set)

    Returns:
        dict with matched food data or None
    """
    global USDA_API_KEY
    if usda_key:
        USDA_API_KEY = usda_key

    food_type = detect_food_type(food_name)

    # For Nutritionix, include portion in query (natural language handles it)
    nix_query = f"{portion_desc} {food_name}".strip() if portion_desc else food_name

    # Try Nutritionix first for branded/restaurant foods
    if nutritionix_id and nutritionix_key:
        results = await search_nutritionix(nix_query, nutritionix_id, nutritionix_key)
        if results:
            best = results[0]
            best['match_type'] = 'exact'
            best['food_type'] = food_type
            return best

    # Fall back to USDA for raw ingredients (use just the food name, not portion)
    results = await search_usda(food_name)
    if results:
        best = results[0]
        best['match_type'] = 'database'
        best['food_type'] = food_type

        # If USDA (per 100g), try to scale to portion
        if best.get('per_100g') and portion_desc:
            grams = _parse_portion_grams(portion_desc, food_name)
            if grams:
                scale = grams / 100
                best['scaled'] = True
                best['serving_size'] = f"{grams}g (estimated)"
                best['calories'] = round(best['calories'] * scale)
                best['protein_g'] = round(best['protein_g'] * scale, 1)
                best['carbs_g'] = round(best['carbs_g'] * scale, 1)
                best['fat_g'] = round(best['fat_g'] * scale, 1)
                best['fiber_g'] = round(best['fiber_g'] * scale, 1)

        return best

    return None


def _parse_portion_grams(portion_desc, food_name=''):
    """
    Try to convert a portion description to grams.
    e.g., "6 oz" → 170, "1 cup" → varies by food, "palm-sized" → ~85g protein
    """
    desc = portion_desc.lower().strip()

    # Direct gram match
    m = re.search(r'(\d+\.?\d*)\s*(?:g|gram)', desc)
    if m:
        return float(m.group(1))

    # Ounce match
    m = re.search(r'(\d+\.?\d*)\s*(?:oz|ounce)', desc)
    if m:
        return float(m.group(1)) * 28.35

    # Cup match (approximate)
    m = re.search(r'(\d+\.?\d*)\s*cup', desc)
    if m:
        cups = float(m.group(1))
        # Rough estimates by food type
        if any(g in food_name.lower() for g in ['rice', 'quinoa', 'oatmeal']):
            return cups * 185  # Cooked rice ~185g/cup
        elif any(g in food_name.lower() for g in ['pasta', 'noodle']):
            return cups * 140  # Cooked pasta ~140g/cup
        elif any(g in food_name.lower() for g in ['vegetable', 'broccoli', 'spinach']):
            return cups * 90  # Chopped veg ~90g/cup
        else:
            return cups * 150  # Generic estimate

    # Visual estimates for proteins
    if 'palm' in desc:
        return 85  # ~3 oz
    if 'fist' in desc:
        return 150  # ~1 cup
    if 'deck of cards' in desc:
        return 85  # ~3 oz

    return None


# ─── Enhanced Analysis Prompt ─────────────────────────────────────────────

def build_enhanced_analysis_prompt(user_preferences=None):
    """
    Build an enhanced food analysis prompt that instructs the AI to:
    1. Identify if food is from a restaurant/brand
    2. Name specific foods clearly for database lookup
    3. Ask follow-up questions for generic foods
    """
    prefs = ""
    if user_preferences:
        diet_str = ', '.join(user_preferences.get('dietary_restrictions', [])) or 'None'
        allergy_str = ', '.join(user_preferences.get('allergies', [])) or 'None'
        prefs = f"""
USER DIETARY CONTEXT:
- Dietary restrictions: {diet_str}
- Allergies: {allergy_str}
- Flag any items that may conflict with these restrictions.
"""

    return f"""You are a nutritional analysis assistant with access to real food databases.

CRITICAL INSTRUCTIONS:
1. IDENTIFY BRANDED FOODS — If you recognize a restaurant item (Big Mac, Chipotle burrito bowl, Starbucks latte), name it exactly as it appears on the menu. Include the restaurant name.
2. NAME GENERIC FOODS PRECISELY — "chicken breast" not just "chicken". "brown rice" not "grain". "whole wheat bread" not "bread".
3. ESTIMATE PORTIONS CAREFULLY — Use visual cues. A plate of pasta is usually 2-3 cups cooked. A chicken breast is typically 4-8 oz.
4. If something is unclear, add it to the "questions" array.
5. Use calorie RANGES only for items you're uncertain about. For branded items, use exact values if you know them.

{prefs}

Respond ONLY with valid JSON:
{{{{
  "items": [
    {{{{
      "name": "Big Mac",
      "brand": "McDonald's",
      "is_branded": true,
      "estimated_quantity": "1 sandwich",
      "estimated_weight_g": 200,
      "calories_low": 550,
      "calories_high": 550,
      "protein_g": 25,
      "carbs_g": 45,
      "fat_g": 30,
      "fiber_g": 3,
      "confidence": 0.95,
      "notes": "Standard Big Mac from McDonald's"
    }}}}
  ],
  "totals": {{{{
    "calories_low": 550,
    "calories_high": 550,
    "protein_g": 25,
    "carbs_g": 45,
    "fat_g": 30,
    "fiber_g": 3
  }}}},
  "overall_confidence": 0.95,
  "questions": [],
  "meal_description": "McDonald's Big Mac"
}}}}

CONFIDENCE SCALE:
- 0.95+ = Branded/restaurant item you're certain about
- 0.85-0.95 = Clear food, good portion estimate
- 0.7-0.85 = Identifiable but portion unclear
- 0.5-0.7 = Partially visible or mixed dish
- Below 0.5 = Guessing (flag for user review)
"""
