# NutriTracker Quick Reference

## 30-Second Overview
- **What:** Private food tracker with AI-powered nutritional analysis
- **Tech:** Python 3 + Flask + waitress + vanilla JS PWA (zero npm/build deps)
- **Port:** 8888
- **Status:** Development — first build

## Key Design Decisions
- All data local (SQLite) — nothing leaves the network except AI API calls
- User brings their own API key (OpenAI, Anthropic, or Google Gemini)
- PWA with home screen install for iOS and Android
- Multi-user household support (profile switcher)
- Mobile-first responsive design, works on desktop with webcam support

## File Structure
```
NutriTracker/
├── install.bat / install.sh    ← one-click setup
├── start.bat / start.sh        ← launch server
├── backend/
│   ├── app.py                  ← Flask routes & API
│   ├── server.py               ← waitress entry point
│   ├── database.py             ← SQLite models
│   ├── ai_proxy.py             ← multi-provider AI client
│   └── food_analyzer.py        ← vision prompt engineering
├── frontend/
│   ├── index.html              ← SPA shell
│   ├── manifest.json           ← PWA manifest
│   ├── sw.js                   ← service worker
│   ├── css/style.css           ← glass panels, magazine typography
│   └── js/
│       ├── app.js              ← router & state
│       ├── onboarding.js       ← profile setup flow
│       ├── dashboard.js        ← daily view & trends
│       ├── meals.js            ← camera, upload, analysis
│       ├── chat.js             ← AI coach conversation
│       └── pwa.js              ← install prompt logic
├── data/
│   ├── config.json             ← server settings (auto-created)
│   └── nutritracker.db         ← SQLite database (auto-created)
└── docs/
    └── QUICK_REFERENCE.md      ← this file
```

## Common Commands
```bash
# Install (one-click)
install.bat          # Windows
./install.sh         # Mac/Linux

# Run
start.bat            # Windows
./start.sh           # Mac/Linux

# Custom port
start.bat 9090
./start.sh 9090
```

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/status | App state & user list |
| POST | /api/setup | First-time app naming |
| GET/POST | /api/users | List / create users |
| GET/PUT/DELETE | /api/users/:id | User CRUD |
| POST | /api/users/:id/analyze | Upload food photo for AI analysis |
| GET/POST | /api/users/:id/meals | List / add meals |
| POST | /api/users/:id/chat | Send message to AI coach |
| GET | /api/users/:id/trends | Weekly nutrition trends |
| GET | /api/providers | Available AI providers & models |

## Data Flow
```
Phone camera → Flask upload endpoint → Save to data/uploads/
  → AI proxy → User's API key → Provider API (OpenAI/Anthropic/Gemini)
  → Structured JSON response → Store in SQLite → Render on dashboard
```

## AI Providers Supported
- **Google Gemini** (recommended — cheapest, good vision)
- **OpenAI** (GPT-4o, GPT-4o-mini)
- **Anthropic** (Claude Sonnet/Opus — excellent analysis quality)

## Privacy Model
- All data stored in local SQLite — never uploaded anywhere
- API keys stored locally — used only for AI calls
- Food photos stored locally in data/uploads/
- No analytics, no tracking, no cloud sync
- Server binds to 0.0.0.0 — accessible only on local network (or via VPN)

## Remote Access
For use outside the home network:
- **Tailscale** (recommended): Install on server + phone, zero config mesh VPN
- **OpenVPN**: More setup but full control

## NEVER DO THESE
| DON'T | DO INSTEAD |
|-------|------------|
| Store API keys in frontend JS | Keys stay in SQLite, never sent to browser |
| Use exact calorie numbers from AI | Always show ranges (300-400 cal) |
| Hardcode file paths | Use Path(__file__).resolve().parent |
| npm install anything | Pure vanilla JS, zero build deps |
