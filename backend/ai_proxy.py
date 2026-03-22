"""
AI Proxy — Multi-Provider Client
=================================
Handles communication with OpenAI, Anthropic, and Google Gemini APIs.
Supports text chat and vision (food photo analysis).

Each user brings their own API key. Keys are stored locally in SQLite.
The server proxies requests — no data leaves the local network except
the API call itself (photo + prompt → response).
"""

import json
import base64
import re
import httpx
from pathlib import Path

# Timeout for API calls (seconds)
API_TIMEOUT = 60

# ─── Provider Configurations ────────────────────────────────────────────────
# Fallback models used when live API fetch fails (no key yet, network error)

PROVIDERS = {
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'models': {}   # Populated live via fetch_models_live()
    },
    'anthropic': {
        'name': 'Anthropic',
        'base_url': 'https://api.anthropic.com/v1',
        'models': {}   # Populated live via fetch_models_live()
    },
    'google': {
        'name': 'Google Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'models': {}   # Populated live via fetch_models_live()
    }
}

# Cache for live-fetched models (populated on first request per provider)
_model_cache = {}


async def fetch_models_live(provider, api_key):
    """
    Fetch available models directly from the provider's API.
    Returns dict of {model_id: display_name}.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if provider == 'openai':
                resp = await client.get(
                    'https://api.openai.com/v1/models',
                    headers={'Authorization': f'Bearer {api_key}'}
                )
                resp.raise_for_status()
                data = resp.json()
                models = {}
                for m in sorted(data.get('data', []), key=lambda x: x['id']):
                    mid = m['id']
                    # Filter to chat models (gpt, o1, o3, o4)
                    if any(mid.startswith(p) for p in ('gpt-', 'o1', 'o3', 'o4')):
                        # Skip fine-tuned, instruct, audio, realtime variants
                        if any(x in mid for x in ('instruct', 'audio', 'realtime', 'search', ':ft')):
                            continue
                        models[mid] = mid
                return models

            elif provider == 'anthropic':
                resp = await client.get(
                    'https://api.anthropic.com/v1/models',
                    headers={
                        'x-api-key': api_key,
                        'anthropic-version': '2023-06-01'
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                models = {}
                for m in data.get('data', []):
                    mid = m.get('id', '')
                    name = m.get('display_name', mid)
                    if mid:
                        models[mid] = name
                return models

            elif provider == 'google':
                resp = await client.get(
                    f'https://generativelanguage.googleapis.com/v1beta/models?key={api_key}'
                )
                resp.raise_for_status()
                data = resp.json()
                models = {}
                for m in data.get('models', []):
                    mid = m.get('name', '').replace('models/', '')
                    name = m.get('displayName', mid)
                    # Filter to generative models
                    methods = m.get('supportedGenerationMethods', [])
                    if 'generateContent' in methods:
                        models[mid] = name
                return models

    except Exception as e:
        print(f"  [WARN] Failed to fetch models for {provider}: {e}")
        return {}


def get_available_providers():
    """Return provider info for the frontend (static fallback)."""
    result = {}
    for pid, pdata in PROVIDERS.items():
        result[pid] = {
            'name': pdata['name'],
            'models': {
                mid: mdata['name'] if isinstance(mdata, dict) else mdata
                for mid, mdata in pdata['models'].items()
            }
        }
    return result


def has_vision(provider, model):
    """
    Check if a provider/model combo supports vision.
    Most modern models support vision, so default to True for known providers.
    """
    # All current-gen models from major providers support vision
    # except reasoning-only models like o3-mini
    no_vision = {'o3-mini', 'o1-mini', 'o1-preview'}
    if model in no_vision:
        return False
    if provider in PROVIDERS:
        return True
    return False


def _encode_image(image_path):
    """Read and base64-encode an image file."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with open(path, 'rb') as f:
        data = f.read()

    ext = path.suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.webp': 'image/webp', '.heic': 'image/heic',
    }
    mime = mime_types.get(ext, 'image/jpeg')
    b64 = base64.b64encode(data).decode('utf-8')
    return b64, mime


def _extract_json(text):
    """Extract JSON from AI response text, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    # Try parsing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object or array in the text
        for pattern in [r'\{.*\}', r'\[.*\]']:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
    return None


# ─── OpenAI ─────────────────────────────────────────────────────────────────

async def _call_openai(api_key, model, messages, image_path=None):
    """Call OpenAI API (chat or vision)."""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # Convert messages to OpenAI format
    oai_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            oai_messages.append({'role': 'system', 'content': msg['content']})
        elif msg['role'] == 'user':
            if image_path and msg == messages[-1]:
                b64, mime = _encode_image(image_path)
                oai_messages.append({
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': msg['content']},
                        {'type': 'image_url', 'image_url': {
                            'url': f'data:{mime};base64,{b64}'
                        }}
                    ]
                })
            else:
                oai_messages.append({'role': 'user', 'content': msg['content']})
        elif msg['role'] == 'assistant':
            oai_messages.append({'role': 'assistant', 'content': msg['content']})

    payload = {
        'model': model,
        'messages': oai_messages,
        'max_tokens': 2000,
        'temperature': 0.3,
    }

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        resp = await client.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']


# ─── Anthropic ──────────────────────────────────────────────────────────────

async def _call_anthropic(api_key, model, messages, image_path=None):
    """Call Anthropic API (chat or vision)."""
    headers = {
        'x-api-key': api_key,
        'Content-Type': 'application/json',
        'anthropic-version': '2023-06-01'
    }

    # Separate system message
    system_text = ''
    claude_messages = []

    for msg in messages:
        if msg['role'] == 'system':
            system_text += msg['content'] + '\n'
        elif msg['role'] == 'user':
            if image_path and msg == messages[-1]:
                b64, mime = _encode_image(image_path)
                claude_messages.append({
                    'role': 'user',
                    'content': [
                        {'type': 'image', 'source': {
                            'type': 'base64',
                            'media_type': mime,
                            'data': b64
                        }},
                        {'type': 'text', 'text': msg['content']}
                    ]
                })
            else:
                claude_messages.append({'role': 'user', 'content': msg['content']})
        elif msg['role'] == 'assistant':
            claude_messages.append({'role': 'assistant', 'content': msg['content']})

    payload = {
        'model': model,
        'max_tokens': 2000,
        'messages': claude_messages,
        'temperature': 0.3,
    }
    if system_text.strip():
        payload['system'] = system_text.strip()

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        resp = await client.post(
            'https://api.anthropic.com/v1/messages',
            headers=headers,
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data['content'][0]['text']


# ─── Google Gemini ──────────────────────────────────────────────────────────

async def _call_gemini(api_key, model, messages, image_path=None):
    """Call Google Gemini API (chat or vision)."""
    # Build contents array
    contents = []
    system_text = ''

    for msg in messages:
        if msg['role'] == 'system':
            system_text += msg['content'] + '\n'
        elif msg['role'] == 'user':
            parts = [{'text': msg['content']}]
            if image_path and msg == messages[-1]:
                b64, mime = _encode_image(image_path)
                parts.insert(0, {
                    'inline_data': {
                        'mime_type': mime,
                        'data': b64
                    }
                })
            contents.append({'role': 'user', 'parts': parts})
        elif msg['role'] == 'assistant':
            contents.append({'role': 'model', 'parts': [{'text': msg['content']}]})

    payload = {
        'contents': contents,
        'generationConfig': {
            'maxOutputTokens': 2000,
            'temperature': 0.3,
        }
    }

    if system_text.strip():
        payload['system_instruction'] = {'parts': [{'text': system_text.strip()}]}

    url = (f'https://generativelanguage.googleapis.com/v1beta/models/{model}'
           f':generateContent?key={api_key}')

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data['candidates'][0]['content']['parts'][0]['text']


# ─── Unified Interface ─────────────────────────────────────────────────────

async def chat(provider, api_key, model, messages, image_path=None):
    """
    Unified chat interface. Routes to the correct provider.

    Args:
        provider: 'openai', 'anthropic', or 'google'
        api_key: User's API key for the provider
        model: Model identifier string
        messages: List of {'role': str, 'content': str}
        image_path: Optional path to image file for vision

    Returns:
        str: The AI's response text
    """
    callers = {
        'openai': _call_openai,
        'anthropic': _call_anthropic,
        'google': _call_gemini,
    }

    caller = callers.get(provider)
    if not caller:
        raise ValueError(f"Unknown provider: {provider}")

    return await caller(api_key, model, messages, image_path)


async def validate_api_key(provider, api_key, model=None):
    """
    Test if an API key works by sending a minimal request.
    Returns (success: bool, message: str).
    """
    test_messages = [{'role': 'user', 'content': 'Say "OK" and nothing else.'}]

    # Pick a cheap model for testing if none specified
    if not model:
        defaults = {
            'openai': 'gpt-5.4-nano',
            'anthropic': 'claude-haiku-4-5-20250929',
            'google': 'gemini-3.1-flash-lite-preview',
        }
        model = defaults.get(provider, '')

    try:
        response = await chat(provider, api_key, model, test_messages)
        return True, f"Key valid. Model responded: {response[:50]}"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return False, "Invalid API key."
        elif e.response.status_code == 403:
            return False, "API key lacks required permissions."
        elif e.response.status_code == 429:
            return True, "Key valid (rate limited — try again shortly)."
        else:
            return False, f"API error {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"
