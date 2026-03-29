# 🌍 Travel Itinerary Planner

A Django-powered travel planning app with AI-generated itineraries, real-time weather forecasts,
interactive maps, budget tracking, and shareable trip links.

## Features

- **OTP-based authentication** – email-verified login, no passwords
- **AI itinerary generation** – powered by OpenRouter (GPT-3.5-turbo)
- **7-day weather forecast** – OpenWeatherMap integration with rain-day suggestions
- **Interactive maps** – Leaflet.js + Geoapify tiles with per-day activity markers
- **Place autocomplete** – Geoapify autocomplete for destination and activity inputs
- **Budget tracker** – per-trip budget with currency selector and remaining-budget meter
- **Shareable links** – read-only public trip view via a random slug token
- **Email invites** – invite anyone to view a trip (no account required)
- **Booking & tickets** – confirm trip and receive a beautifully formatted email ticket

## Tech Stack

- **Backend** – Django 5+, SQLite (dev)
- **Frontend** – Bootstrap 5, Leaflet.js, Font Awesome
- **APIs** – OpenWeatherMap (free), Geoapify (free), OSRM (free), OpenRouter (free tier)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/rajmohan-14/Travel-itinerary.git
cd Travel-itinerary
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys and email settings
```

### 4. Apply migrations and run the dev server

```bash
python manage.py migrate
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (**required**) |
| `DEBUG` | `True` for development, `False` for production (default: `True`) |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated list of trusted origins for CSRF |
| `OPENWEATHER_API_KEY` | [OpenWeatherMap](https://openweathermap.org/api) free API key |
| `GEOAPIFY_API_KEY` | [Geoapify](https://www.geoapify.com/) free API key |
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/) key for AI itineraries |
| `EMAIL_BACKEND` | e.g. `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | e.g. `smtp.gmail.com` |
| `EMAIL_PORT` | e.g. `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_HOST_USER` | Your email address |
| `EMAIL_HOST_PASSWORD` | Gmail App Password |
| `DEFAULT_FROM_EMAIL` | Sender address shown to recipients |

## Running Tests

```bash
python manage.py test itinerary
```

## API Keys (all free tiers)

- **OpenWeatherMap** – 1,000 calls/day on the free plan
- **Geoapify** – 3,000 calls/day on the free plan  
  ⚠️ The Geoapify key is embedded in the client-side JS for autocomplete. To prevent unauthorized use,
  [enable allowed-origins restrictions](https://www.geoapify.com/how-to-get-geoapify-api-key) in your Geoapify dashboard.
- **OSRM** – completely free, no key required
- **OpenRouter** – free tier with rate limits

## License

MIT
