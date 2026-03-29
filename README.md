# ✈️ Travel Itinerary Planner

A Django web application that helps you plan, organise, and share travel itineraries with AI-generated day-by-day plans, live weather forecasts, interactive maps, and budget tracking.

## Features

- **OTP-based authentication** – register and log in with a one-time password sent to your email.
- **AI itinerary generation** – day-by-day plans generated via OpenRouter.
- **Live 7-day weather forecast** – powered by OpenWeatherMap; rain warnings are surfaced on outdoor days.
- **Interactive map** – Leaflet.js + Geoapify tiles with a pin for each destination.
- **Geoapify place autocomplete** – smart autocomplete for destination and activity fields.
- **Budget tracker** – set a budget and currency; see a remaining-budget progress bar.
- **Shareable public link** – generate a read-only tokenised URL for any itinerary; optionally invite someone by email.
- **Booking & tickets** – confirm a booking and receive a formatted HTML ticket by email.
- **WhatsApp reminder** – one-click WhatsApp message with your booking details.

## Tech stack

- **Backend**: Django 5.2, SQLite (dev)
- **Frontend**: Bootstrap 5, Leaflet.js, Font Awesome
- **APIs**: OpenWeatherMap (free tier), Geoapify (free tier), OpenRouter (AI)
- **Email**: Django SMTP (Gmail)

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/rajmohan-14/Travel-itinerary.git
cd Travel-itinerary
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key – **required** |
| `DEBUG` | `True` for development, `False` for production |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts (e.g. `localhost,127.0.0.1`) |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins for CSRF (e.g. `https://myapp.example.com`) |
| `OPENWEATHER_API_KEY` | [OpenWeatherMap](https://home.openweathermap.org/api_keys) free API key |
| `GEOAPIFY_API_KEY` | [Geoapify](https://www.geoapify.com/get-started-with-maps-api) free API key |
| `OPENROUTER_API_KEY` | [OpenRouter](https://openrouter.ai/) API key for AI itinerary generation |
| `EMAIL_BACKEND` | e.g. `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | SMTP host, e.g. `smtp.gmail.com` |
| `EMAIL_PORT` | SMTP port, e.g. `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_HOST_USER` | Your Gmail address |
| `EMAIL_HOST_PASSWORD` | Gmail App Password (not your normal password) |
| `DEFAULT_FROM_EMAIL` | Sender address shown in emails |

### 3. Apply migrations and run

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

### 4. Running tests

```bash
python manage.py test itinerary
```

## Project structure

```
Travel-itinerary/
├── travelplanner/       # Django project settings & root URLs
├── itinerary/           # Main app (models, views, forms, templates)
│   ├── migrations/
│   ├── templates/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   └── tests.py
├── requirements.txt
├── manage.py
└── .env.example
```

## API keys (free tiers used)

| Service | Free quota | Used for |
|---|---|---|
| OpenWeatherMap | 1 000 calls/day | 7-day forecast |
| Geoapify | 3 000 calls/day | Place autocomplete, hotels & attractions |
| OpenRouter | Pay-as-you-go / free models | AI itinerary generation |

## License

MIT
