# NutriTracker

**Private, self-hosted food tracking with AI-powered nutritional analysis.**

Snap a photo of your meal, and AI identifies the food and estimates macros instantly. Track calories, protein, carbs, and fat against personalized daily targets. Get coaching from an AI that actually knows your history. All data stays on your machine.

---

## Features

### Dashboard
- **Calorie ring** — visual daily progress at a glance
- **Macro bars** — protein, carbs, fat with personalized targets
- **Today's Meals** — photo cards with per-meal breakdown
- **Weigh-in reminders** — configurable frequency (daily/weekly/monthly) with inline quick-weigh

### Snap & Track
- **Photo-based logging** — take a photo or upload from gallery
- **AI food recognition** — identifies food items with confidence scores
- **Automatic macro estimation** — calories, protein, carbs, fat per meal
- **Multi-provider AI** — bring your own API key (OpenAI, Anthropic, or Google Gemini)

### AI Coach
- **Personalized onboarding** — AI introduces itself, reflects your stats, asks about coaching style
- **Multi-conversation chat** — separate threads, conversation drawer, easy switching
- **Persistent memory** — coach remembers details across conversations
- **Customizable personality** — name your coach, pick the vibe (motivational, drill sergeant, etc.)

### Trends & Analytics
- **7/14/30-day views** — calorie and weight charts
- **AI trend analysis** — weekly insights that reference your actual meals, not just numbers
- **Weight tracking** — log weigh-ins, see progress over time

### Meal History
- **Date-grouped timeline** — browse past meals by month
- **Expandable days** — tap to see individual meals with photos
- **Bulk delete** — select days, date ranges, or individual meals

### Settings & Customization
- **Rename the app** — make it yours
- **Name your AI coach** — appears in chat and system prompts
- **Edit profile** — update stats, goals, dietary preferences anytime
- **Weigh-in schedule** — daily, weekly, biweekly, or monthly reminders

### Privacy & Portability
- **100% self-hosted** — runs on your local network
- **No cloud dependency** — SQLite database, no external services except the AI API call
- **Your API keys** — stored locally, never transmitted anywhere except the provider
- **PWA support** — install on your phone's home screen, works offline for cached views

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3 + Flask + Waitress (production WSGI) |
| Frontend | Vanilla JS SPA (zero npm, zero build step) |
| Database | SQLite with WAL mode |
| AI | OpenAI / Anthropic / Google Gemini (BYOK) |
| PWA | Service Worker + Web App Manifest |

**Total dependencies: 3** (`flask`, `waitress`, `httpx`)

---

## Quick Start

### Windows

```batch
install.bat
start.bat
```

### macOS / Linux

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

The server starts on **http://localhost:8888**. Open this URL on your phone (same Wi-Fi network) to use it as a mobile app.

### Add to Home Screen (PWA)

1. Open the URL in your phone's browser
2. Tap **Share** → **Add to Home Screen**
3. It now launches like a native app

---

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/yourusername/nutritracker.git
   cd nutritracker
   ```

2. **Install** (auto-creates venv, installs 3 dependencies, initializes DB)
   ```bash
   # Windows
   install.bat

   # macOS/Linux
   ./install.sh
   ```

3. **Start the server**
   ```bash
   # Windows
   start.bat

   # macOS/Linux
   ./start.sh
   ```

4. **Complete onboarding** — enter your stats, goals, and AI provider API key

5. **Start tracking** — snap photos of meals, chat with your coach

---

## Project Structure

```
nutritracker/
├── backend/
│   ├── server.py          # Entry point (Waitress WSGI)
│   ├── app.py             # Flask routes & API endpoints
│   ├── database.py        # SQLite with auto-migrations
│   ├── food_analyzer.py   # AI prompt engineering & analysis
│   ├── food_database.py   # USDA food reference data
│   └── ai_proxy.py        # Multi-provider AI client
├── frontend/
│   ├── index.html          # Single-page app shell
│   ├── sw.js               # Service worker (offline caching)
│   ├── manifest.json       # PWA manifest
│   ├── css/style.css       # All styles
│   ├── js/
│   │   ├── app.js          # Router & navigation
│   │   ├── dashboard.js    # Dashboard, weigh-ins, settings
│   │   ├── meals.js        # Photo capture & meal logging
│   │   ├── chat.js         # AI coach conversations
│   │   ├── history.js      # Meal history & bulk delete
│   │   ├── onboarding.js   # First-run setup wizard
│   │   └── pwa.js          # Service worker registration
│   └── assets/
│       ├── favicon.svg     # App icon
│       └── icons/          # PWA icons (auto-generated)
├── data/                   # Local data (gitignored)
│   ├── nutritracker.db     # SQLite database
│   ├── config.json         # User config
│   └── uploads/            # Meal photos
├── install.bat / install.sh
├── start.bat / start.sh
└── requirements.txt        # flask, waitress, httpx
```

---

## API Key Setup

NutriTracker uses a **Bring Your Own Key** model. Your key is stored locally in the SQLite database and only used for direct API calls to your chosen provider.

| Provider | Get a key |
|----------|-----------|
| **OpenAI** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/) |
| **Google Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/app/apikey) |

Enter your key during onboarding (Step 6) or update it anytime in Settings.

---

## Privacy

- **No accounts.** No sign-up. No cloud.
- **No telemetry.** Zero analytics, zero tracking.
- **Your photos stay local.** Stored in `data/uploads/` on your machine.
- **AI calls are direct.** Photo + prompt → provider API → response. Nothing else leaves your network.
- **Database is local SQLite.** Back it up, delete it, move it — it's just a file.

---

## License

MIT — free to use, modify, and share. No strings attached.

---

Built with care for people who want to track their nutrition without giving their data to a corporation.
