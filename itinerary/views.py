# itinerary/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from django.core.mail import send_mail, EmailMultiAlternatives
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from datetime import datetime, timedelta
import requests
import json
import random
import string
import logging
import urllib.parse

logger = logging.getLogger(__name__)

from .forms import RegisterForm, OTPForm, TripForm, TripInviteForm
from .models import UserOTP, Trip, TripInvite

import os
from dotenv import load_dotenv

load_dotenv(settings.BASE_DIR / ".env")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY") or os.getenv("GEOAPIFY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# Authentication views
# ---------------------------------------------------------------------------

def landing_page(request):
    recent_trips = []
    if request.user.is_authenticated:
        recent_trips = Trip.objects.filter(user=request.user).order_by('-created_at')[:5]
    return render(request, 'landing.html', {'recent_trips': recent_trips})


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            username = form.cleaned_data['username']
            phone_number = form.cleaned_data.get('phone_number', '')

            user, created = User.objects.get_or_create(
                username=username,
                email=email,
                defaults={'is_active': True}
            )

            if phone_number:
                request.session['phone_number'] = phone_number

            otp_obj, _ = UserOTP.objects.get_or_create(user=user)
            otp = otp_obj.generate_otp()

            try:
                send_mail(
                    subject="Your OTP for Travel Planner Login",
                    message=f"Your 5-digit OTP is: {otp}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.info(request, f"OTP sent to {email}. Please check your inbox.")
            except Exception as e:
                messages.error(request, f"Error sending email: {e}")
                return redirect('register')

            request.session['email'] = email
            return redirect('verify_otp')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})


def verify_otp_view(request):
    email = request.session.get('email')
    if not email:
        return redirect('register')

    try:
        user = User.objects.get(email=email)
        otp_obj = UserOTP.objects.get(user=user)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('register')

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            if otp == otp_obj.otp:
                login(request, user)
                otp_obj.otp = None
                otp_obj.save()
                messages.success(request, "Login successful!")
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid OTP. Please try again.")
    else:
        form = OTPForm()

    return render(request, 'verify_otp.html', {'form': form, 'email': email})


def resend_otp_view(request):
    email = request.session.get('email')
    if not email:
        messages.error(request, "Session expired. Please register again.")
        return redirect('register')

    try:
        user = User.objects.get(email=email)
        otp_obj, _ = UserOTP.objects.get_or_create(user=user)
        otp = otp_obj.generate_otp()

        send_mail(
            subject="Resent OTP for Travel Planner Login",
            message=f"Your 5-digit OTP is: {otp}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        messages.success(request, f"A new OTP has been sent to {email}.")
        return redirect('verify_otp')

    except Exception as e:
        messages.error(request, f"Error resending OTP: {e}")
        return redirect('register')


# ---------------------------------------------------------------------------
# AI itinerary generation
# ---------------------------------------------------------------------------

def generate_itinerary_with_ai(destination, days, budget, travelers, interests, currency='INR'):
    """Generate travel itinerary using OpenRouter AI"""

    budget_str = f"{budget} {currency}" if budget else "unspecified"
    prompt = f"""
    Create a detailed {days}-day travel itinerary for {destination} for {travelers} traveler(s) with a budget of {budget_str}.
    Interests: {interests}

    Please provide the itinerary in this exact JSON format:
    {{
        "itinerary": [
            {{
                "day": 1,
                "date": "YYYY-MM-DD",
                "activities": [
                    {{
                        "time": "09:00 AM",
                        "activity": "Activity description",
                        "location": "Location name",
                        "cost": 500,
                        "duration": "2 hours",
                        "type": "sightseeing"
                    }}
                ],
                "total_cost": 2500
            }}
        ],
        "summary": {{
            "total_estimated_cost": {budget},
            "best_transportation": "Recommended transport",
            "tips": ["Tip 1", "Tip 2"],
            "must_see": ["Place 1", "Place 2"]
        }}
    }}
    """

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            itinerary_text = data['choices'][0]['message']['content']

            try:
                start_idx = itinerary_text.find('{')
                end_idx = itinerary_text.rfind('}') + 1
                json_str = itinerary_text[start_idx:end_idx]
                itinerary_data = json.loads(json_str)
                return itinerary_data
            except json.JSONDecodeError:
                return {"raw_itinerary": itinerary_text}

        return {"error": "Failed to generate itinerary"}

    except Exception as e:
        return {"error": f"AI service error: {str(e)}"}


# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------

def fetch_weather_forecast(lat, lon):
    """Fetch 7-day daily forecast from OpenWeatherMap (free One Call API)."""
    if not OPENWEATHER_API_KEY:
        return []
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&cnt=40"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # Aggregate by day (take noon reading or first of the day)
        days_seen = {}
        forecast = []
        for item in data.get('list', []):
            dt_txt = item.get('dt_txt', '')
            day = dt_txt[:10]
            if day not in days_seen:
                days_seen[day] = True
                forecast.append({
                    'date': day,
                    'temp_min': item['main']['temp_min'],
                    'temp_max': item['main']['temp_max'],
                    'description': item['weather'][0]['description'],
                    'icon': item['weather'][0]['icon'],
                    'rain': item.get('rain', {}).get('3h', 0) or 0,
                    'wind': item.get('wind', {}).get('speed', 0),
                })
        return forecast[:7]
    except Exception:
        return []


def weather_icon_url(icon_code):
    return f"https://openweathermap.org/img/wn/{icon_code}@2x.png"


# ---------------------------------------------------------------------------
# Trip ticket helpers
# ---------------------------------------------------------------------------

def generate_ticket_data(trip, itinerary):
    """Generate ticket data for email and WhatsApp"""
    booking_ref = trip.generate_booking_reference()

    ticket_data = {
        'booking_reference': booking_ref,
        'destination': trip.destination,
        'traveler_name': trip.user.username,
        'traveler_email': trip.user.email,
        'start_date': trip.start_date,
        'end_date': trip.end_date,
        'duration': trip.duration_days,
        'travelers': trip.travelers,
        'total_cost': trip.formatted_budget,
        'itinerary_summary': itinerary.get('summary', {}) if itinerary else {},
        'daily_plans': itinerary.get('itinerary', []) if itinerary else [],
        'booking_date': timezone.now().strftime("%Y-%m-%d %H:%M"),
        'ticket_id': f"TKT{random.randint(100000, 999999)}",
    }
    return ticket_data


def send_ticket_email(trip, itinerary):
    """Send beautifully formatted ticket email"""
    try:
        ticket_data = generate_ticket_data(trip, itinerary)

        html_content = render_to_string('ticket_email.html', {
            'trip': trip,
            'ticket': ticket_data,
            'itinerary': itinerary
        })

        text_content = strip_tags(html_content)
        subject = f"🎫 Your Travel Ticket to {trip.destination} - {ticket_data['booking_reference']}"

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[trip.user.email],
            reply_to=[settings.DEFAULT_FROM_EMAIL]
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        trip.is_booked = True
        trip.tickets_sent = True
        trip.save()
        return True

    except Exception as e:
        print(f"Email sending error: {e}")
        return False


def send_whatsapp_notification(trip, itinerary):
    """Build a WhatsApp pre-fill URL (no cost, no API key)."""
    try:
        if not trip.phone_number:
            return False

        phone_number = ''.join(filter(str.isdigit, trip.phone_number))
        if not phone_number.startswith('91') and len(phone_number) == 10:
            phone_number = '91' + phone_number

        ticket_data = generate_ticket_data(trip, itinerary)

        message = (
            f"🎫 *Travel Booking Confirmed!*\n\n"
            f"*Booking Reference:* {ticket_data['booking_reference']}\n"
            f"*Destination:* {trip.destination}\n"
            f"*Travel Dates:* {trip.start_date} to {trip.end_date}\n"
            f"*Duration:* {trip.duration_days} days\n"
            f"*Travelers:* {trip.travelers}\n"
            f"*Total Budget:* {trip.formatted_budget}\n\n"
            f"Your detailed itinerary has been sent to: {trip.user.email}\n\n"
            f"Thank you for choosing TravelPlanner! 🌍"
        )

        encoded_message = urllib.parse.quote(message)
        return f"https://wa.me/{phone_number}?text={encoded_message}"

    except Exception as e:
        print(f"WhatsApp notification error: {e}")
        return False


def send_sms_notification(trip, itinerary):
    print(f"SMS would be sent to: {trip.phone_number}")
    return True


# ---------------------------------------------------------------------------
# Dashboard & trip management views
# ---------------------------------------------------------------------------

def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('register')

    trips = Trip.objects.filter(user=request.user).order_by('-created_at')
    form = TripForm()

    if request.method == "POST":
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.user = request.user

            phone_number = request.session.get('phone_number')
            if phone_number:
                trip.phone_number = phone_number
                request.session.pop('phone_number', None)

            try:
                duration = (trip.end_date - trip.start_date).days
                if duration <= 0:
                    messages.error(request, "End date must be after start date.")
                    return redirect('dashboard')

                # ------ Weather (current) ------
                weather_url = (
                    f"https://api.openweathermap.org/data/2.5/weather"
                    f"?q={urllib.parse.quote(trip.destination)}&appid={OPENWEATHER_API_KEY}&units=metric"
                )
                weather_resp = requests.get(weather_url, timeout=10)
                lat, lon = None, None

                if weather_resp.status_code == 200:
                    weather_data = weather_resp.json()
                    temp = weather_data['main']['temp']
                    desc = weather_data['weather'][0]['description']
                    trip.weather = f"{temp}°C, {desc}"
                    coord = weather_data.get('coord', {})
                    lat = coord.get('lat')
                    lon = coord.get('lon')
                    if lat and lon:
                        trip.dest_lat = lat
                        trip.dest_lng = lon
                else:
                    trip.weather = "Weather data not available"

                # ------ 7-day forecast ------
                if lat and lon:
                    forecast = fetch_weather_forecast(lat, lon)
                    trip.weather_forecast = json.dumps(forecast)

                # ------ Attractions & Hotels via Geoapify ------
                if lat and lon:
                    attractions_url = (
                        f"https://api.geoapify.com/v2/places"
                        f"?categories=tourism.sights,tourism.attraction"
                        f"&filter=circle:{lon},{lat},5000&limit=10&apiKey={GEOAPIFY_API_KEY}"
                    )
                    attractions_resp = requests.get(attractions_url, timeout=10)
                    if attractions_resp.status_code == 200:
                        features = attractions_resp.json().get('features', [])
                        names = [f['properties'].get('name') for f in features[:5] if f['properties'].get('name')]
                        trip.attractions = ", ".join(names) if names else "No attractions found"

                    hotels_url = (
                        f"https://api.geoapify.com/v2/places"
                        f"?categories=accommodation.hotel"
                        f"&filter=circle:{lon},{lat},5000&limit=5&apiKey={GEOAPIFY_API_KEY}"
                    )
                    hotels_resp = requests.get(hotels_url, timeout=10)
                    if hotels_resp.status_code == 200:
                        features = hotels_resp.json().get('features', [])
                        names = [f['properties'].get('name') for f in features[:3] if f['properties'].get('name')]
                        trip.hotels = ", ".join(names) if names else "No hotels found"

                    # ------ Distance via OSRM ------
                    distance_url = (
                        f"https://router.project-osrm.org/route/v1/driving/"
                        f"77.5946,12.9716;{lon},{lat}?overview=false"
                    )
                    dist_resp = requests.get(distance_url, timeout=10)
                    if dist_resp.status_code == 200:
                        dist_data = dist_resp.json()
                        if dist_data.get('routes'):
                            trip.distance_km = round(dist_data['routes'][0]['distance'] / 1000, 2)
                else:
                    trip.attractions = "Location not found"
                    trip.hotels = "Location not found"

                # ------ AI Itinerary ------
                itinerary_data = generate_itinerary_with_ai(
                    destination=trip.destination,
                    days=duration,
                    budget=trip.budget,
                    travelers=trip.travelers,
                    interests=trip.interests,
                    currency=trip.currency,
                )
                if 'error' not in itinerary_data:
                    trip.itinerary = json.dumps(itinerary_data)
                else:
                    trip.itinerary = ""

                # Ensure share slug is generated on first save
                trip.save()
                trip.generate_share_slug()

                messages.success(request, "Trip planned successfully! You can now book and get tickets.")
                return redirect('trip_detail', trip_id=trip.id)

            except requests.exceptions.RequestException as e:
                messages.error(request, f"API error: {e}")
            except Exception as e:
                messages.error(request, f"Something went wrong: {e}")

    return render(request, 'dashboard.html', {
        'form': form,
        'trips': trips,
        'user': request.user,
        'geoapify_api_key': settings.GEOAPIFY_API_KEY,
    })


def trip_detail_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    return _render_trip_detail(request, trip, is_owner=True)


def public_trip_view(request, share_slug):
    """Read-only public trip view – no authentication required."""
    trip = get_object_or_404(Trip, share_slug=share_slug)
    invite_form = TripInviteForm()

    if request.method == 'POST':
        invite_form = TripInviteForm(request.POST)
        if invite_form.is_valid():
            email = invite_form.cleaned_data['email']
            _send_invite_email(trip, email, request)
            messages.success(request, f"Invite sent to {email}!")
            return redirect('public_trip', share_slug=share_slug)

    return _render_trip_detail(request, trip, is_owner=False, invite_form=invite_form)


def _render_trip_detail(request, trip, is_owner, invite_form=None):
    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    forecast = []
    if trip.weather_forecast:
        try:
            forecast = json.loads(trip.weather_forecast)
        except json.JSONDecodeError:
            pass

    # Map forecast dates to day numbers for easy template access
    forecast_by_date = {f['date']: f for f in forecast}

    # Annotate itinerary days with forecast data + rain warnings
    daily_plans = []
    if itinerary and 'itinerary' in itinerary:
        for day in itinerary['itinerary']:
            date_str = day.get('date', '')
            day_forecast = forecast_by_date.get(date_str)
            rain_warning = False
            if day_forecast and day_forecast.get('rain', 0) > 1:
                rain_warning = True
            # Compute day spend from activities
            day_spend = 0
            for act in day.get('activities', []):
                cost = act.get('cost', 0)
                try:
                    day_spend += float(cost)
                except (TypeError, ValueError):
                    logger.debug("Could not parse activity cost %r for day %s", cost, date_str)
            daily_plans.append({
                'day': day,
                'forecast': day_forecast,
                'rain_warning': rain_warning,
                'day_spend': day_spend,
            })

    # Budget spent calculation
    total_spent = sum(dp['day_spend'] for dp in daily_plans)
    budget_remaining = None
    budget_pct = None
    if trip.budget:
        budget_remaining = float(trip.budget) - total_spent
        budget_pct = min(100, round(total_spent / float(trip.budget) * 100))

    # Ensure share slug exists
    if not trip.share_slug:
        trip.generate_share_slug()

    return render(request, 'trip_detail.html', {
        'trip': trip,
        'itinerary': itinerary,
        'daily_plans': daily_plans,
        'forecast': forecast,
        'total_spent': total_spent,
        'budget_remaining': budget_remaining,
        'budget_pct': budget_pct,
        'is_owner': is_owner,
        'invite_form': invite_form or TripInviteForm(),
        'geoapify_api_key': settings.GEOAPIFY_API_KEY,
    })


def _send_invite_email(trip, email, request):
    """Send an email invite with the public share link."""
    try:
        public_url = request.build_absolute_uri(f"/trip/share/{trip.share_slug}/")
        subject = f"You're invited to view {trip.user.username}'s trip to {trip.destination}!"
        message = (
            f"Hi,\n\n"
            f"{trip.user.username} has shared their travel itinerary with you.\n\n"
            f"Destination: {trip.destination}\n"
            f"Dates: {trip.start_date} – {trip.end_date}\n\n"
            f"View the full itinerary here:\n{public_url}\n\n"
            f"Happy travels! 🌍\n— TravelPlanner"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
        TripInvite.objects.create(trip=trip, email=email)
    except Exception as e:
        print(f"Invite email error: {e}")


def share_trip_view(request, trip_id):
    """Generate/retrieve share link for a trip (owner only)."""
    if not request.user.is_authenticated:
        return redirect('register')
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    trip.generate_share_slug()
    messages.success(request, "Share link generated!")
    return redirect('trip_detail', trip_id=trip.id)


def delete_trip_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)

    if request.method == "POST":
        destination = trip.destination
        trip.delete()
        messages.success(request, f"Trip to {destination} deleted successfully!")
        return redirect('dashboard')

    return render(request, 'delete_trip.html', {'trip': trip})


def book_trip_view(request, trip_id):
    """Book trip and send notifications"""
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)

    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    if request.method == "POST":
        try:
            email_sent = send_ticket_email(trip, itinerary)
            whatsapp_url = send_whatsapp_notification(trip, itinerary)
            send_sms_notification(trip, itinerary)

            if email_sent:
                messages.success(request, "🎫 Booking confirmed! Tickets sent to your email.")
                if whatsapp_url:
                    messages.info(
                        request,
                        f"📱 <a href='{whatsapp_url}' target='_blank' class='alert-link'>Click here to send WhatsApp message</a>",
                        extra_tags='safe'
                    )
            else:
                messages.error(request, "Failed to send tickets. Please try again.")

        except Exception as e:
            messages.error(request, f"Booking failed: {str(e)}")

        return redirect('trip_detail', trip_id=trip.id)

    return render(request, 'book_trip.html', {
        'trip': trip,
        'itinerary': itinerary
    })


def send_whatsapp_reminder_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    whatsapp_url = send_whatsapp_notification(trip, itinerary)
    if whatsapp_url:
        messages.success(request, "WhatsApp message ready! Click the button below to send.")
        request.session['whatsapp_url'] = whatsapp_url
    else:
        messages.error(request, "Failed to generate WhatsApp message. Please check your phone number.")

    return redirect('trip_detail', trip_id=trip.id)


def resend_ticket_email_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    email_sent = send_ticket_email(trip, itinerary)
    if email_sent:
        messages.success(request, "Ticket email resent successfully!")
    else:
        messages.error(request, "Failed to resend email. Please try again.")

    return redirect('trip_detail', trip_id=trip.id)


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('register')
