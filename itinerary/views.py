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
import urllib.parse
import secrets

from .forms import RegisterForm, OTPForm, TripForm
from .models import UserOTP, Trip

import os
from dotenv import load_dotenv
from django.conf import settings

load_dotenv(settings.BASE_DIR / ".env")

OPENWEATHER_API = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHER_API")
GEOAPIFY_API = os.getenv("GEOAPIFY_API_KEY") or os.getenv("GEOAPIFY_API")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------

def fetch_weather_forecast(lat, lon):
    """Fetch 7-day daily forecast from OpenWeatherMap One Call API.
    Returns a list of day dicts with keys: date, temp_max, temp_min,
    description, icon, has_rain.
    Falls back to an empty list on error.
    """
    if not OPENWEATHER_API or not lat or not lon:
        return []
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API}&units=metric&cnt=56"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # Aggregate 3-hourly entries into daily summaries
        days = {}
        for entry in data.get("list", []):
            date_str = entry["dt_txt"][:10]
            if date_str not in days:
                days[date_str] = {
                    "date": date_str,
                    "temps": [],
                    "descriptions": [],
                    "icons": [],
                    "has_rain": False,
                }
            days[date_str]["temps"].append(entry["main"]["temp"])
            weather = entry["weather"][0]
            days[date_str]["descriptions"].append(weather["description"])
            days[date_str]["icons"].append(weather["icon"])
            if "rain" in weather["description"].lower() or weather["main"].lower() in ("rain", "drizzle", "thunderstorm"):
                days[date_str]["has_rain"] = True

        result = []
        for day_data in list(days.values())[:7]:
            temps = day_data["temps"]
            result.append({
                "date": day_data["date"],
                "temp_max": round(max(temps), 1),
                "temp_min": round(min(temps), 1),
                "description": day_data["descriptions"][len(day_data["descriptions"]) // 2],
                "icon": day_data["icons"][len(day_data["icons"]) // 2],
                "has_rain": day_data["has_rain"],
            })
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def landing_page(request):
    trips = []
    if request.user.is_authenticated:
        trips = list(Trip.objects.filter(user=request.user).order_by('-created_at')[:6])
    return render(request, 'landing.html', {'trips': trips})

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
# AI & ticket helpers (unchanged from original)
# ---------------------------------------------------------------------------

def generate_itinerary_with_ai(destination, days, budget, travelers, interests):
    """Generate travel itinerary using OpenRouter AI"""
    
    prompt = f"""
    Create a detailed {days}-day travel itinerary for {destination} for {travelers} traveler(s) with a budget of {budget}.
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
                        "cost": "500",
                        "duration": "2 hours",
                        "type": "sightseeing/food/adventure/etc"
                    }}
                ],
                "total_cost": "2500"
            }}
        ],
        "summary": {{
            "total_estimated_cost": "{budget}",
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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
    """Send WhatsApp notification using FREE WhatsApp API"""
    try:
        if not trip.phone_number:
            return False

        phone_number = ''.join(filter(str.isdigit, trip.phone_number))

        if not phone_number.startswith('91') and len(phone_number) == 10:
            phone_number = '91' + phone_number
        
        ticket_data = generate_ticket_data(trip, itinerary)

        message = f"""🎫 *Travel Booking Confirmed!*

*Booking Reference:* {ticket_data['booking_reference']}
*Destination:* {trip.destination}
*Travel Dates:* {trip.start_date} to {trip.end_date}
*Duration:* {trip.duration_days} days
*Travelers:* {trip.travelers}
*Total Budget:* {trip.formatted_budget}

Your detailed itinerary has been sent to your email: {trip.user.email}

Thank you for choosing TravelPlanner! 🌍

_This is an automated message. Please do not reply._"""

        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{phone_number}?text={encoded_message}"
        
        return whatsapp_url
        
    except Exception as e:
        print(f"WhatsApp notification error: {e}")
        return False

def send_sms_notification(trip, itinerary):
    """Send SMS notification - Always return True for demo"""
    try:
        print(f"SMS would be sent to: {trip.phone_number}")
        return True
        
    except Exception as e:
        print(f"SMS sending error: {e}")
        return False


# ---------------------------------------------------------------------------
# Trip management views
# ---------------------------------------------------------------------------

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
            sms_sent = send_sms_notification(trip, itinerary)
            
            if email_sent:
                messages.success(request, "🎫 Booking confirmed! Tickets sent to your email.")
                
                if whatsapp_url:
                    messages.info(request, 
                        f"📱 WhatsApp notification ready! <a href='{whatsapp_url}' target='_blank' class='alert-link'>Click here to send WhatsApp message</a>", 
                        extra_tags='safe'
                    )
                
                if sms_sent:
                    messages.info(request, "📲 SMS notification sent to your phone.")
                    
            else:
                messages.error(request, "Failed to send tickets. Please try again.")
                
        except Exception as e:
            messages.error(request, f"Booking failed: {str(e)}")
        
        return redirect('trip_detail', trip_id=trip.id)
    
    return render(request, 'book_trip.html', {
        'trip': trip,
        'itinerary': itinerary
    })


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
                if 'phone_number' in request.session:
                    del request.session['phone_number']

            try:
                duration = (trip.end_date - trip.start_date).days
                if duration <= 0:
                    messages.error(request, "End date must be after start date.")
                    return redirect('dashboard')

                # Fetch current weather to get coordinates
                weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={trip.destination}&appid={OPENWEATHER_API}&units=metric"
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
                    # Store coordinates
                    if lat and lon:
                        trip.dest_lat = lat
                        trip.dest_lng = lon
                else:
                    trip.weather = "Weather data not available"

                # Fetch 7-day forecast and store as JSON
                if lat and lon:
                    forecast = fetch_weather_forecast(lat, lon)
                    if forecast:
                        trip.weather = json.dumps(forecast)

                    # Fetch attractions & hotels via Geoapify
                    attractions_url = (
                        f"https://api.geoapify.com/v2/places"
                        f"?categories=tourism.sights,tourism.attraction"
                        f"&filter=circle:{lon},{lat},5000&limit=10&apiKey={GEOAPIFY_API}"
                    )
                    attractions_resp = requests.get(attractions_url, timeout=10)
                    if attractions_resp.status_code == 200:
                        features = attractions_resp.json().get('features', [])
                        attractions = [f['properties'].get('name') for f in features[:5] if f['properties'].get('name')]
                        trip.attractions = ", ".join(attractions) if attractions else "No attractions found"

                    hotels_url = (
                        f"https://api.geoapify.com/v2/places"
                        f"?categories=accommodation.hotel"
                        f"&filter=circle:{lon},{lat},5000&limit=5&apiKey={GEOAPIFY_API}"
                    )
                    hotels_resp = requests.get(hotels_url, timeout=10)
                    if hotels_resp.status_code == 200:
                        features = hotels_resp.json().get('features', [])
                        hotels = [f['properties'].get('name') for f in features[:3] if f['properties'].get('name')]
                        trip.hotels = ", ".join(hotels) if hotels else "No hotels found"

                    # Distance
                    distance_url = f"https://router.project-osrm.org/route/v1/driving/77.5946,12.9716;{lon},{lat}?overview=false"
                    dist_resp = requests.get(distance_url, timeout=10)
                    if dist_resp.status_code == 200:
                        dist_data = dist_resp.json()
                        if dist_data.get('routes'):
                            trip.distance_km = round(dist_data['routes'][0]['distance'] / 1000, 2)
                else:
                    trip.attractions = "Location not found"
                    trip.hotels = "Location not found"

                # Generate AI itinerary
                itinerary_data = generate_itinerary_with_ai(
                    destination=trip.destination,
                    days=duration,
                    budget=trip.budget,
                    travelers=trip.travelers,
                    interests=trip.interests
                )
                
                if 'error' not in itinerary_data:
                    trip.itinerary = json.dumps(itinerary_data)
                else:
                    trip.itinerary = "Itinerary generation failed"

                # Auto-generate share slug
                trip.share_slug = secrets.token_urlsafe(24)
                trip.save()
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
        'geoapify_api_key': GEOAPIFY_API or '',
    })


def trip_detail_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')
    
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    
    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    # Parse forecast
    forecast = []
    if trip.weather:
        try:
            forecast = json.loads(trip.weather)
            if not isinstance(forecast, list):
                forecast = []
        except (json.JSONDecodeError, TypeError):
            forecast = []

    # Budget spent calculation from itinerary activities
    spent = _calculate_spent(itinerary)

    return render(request, 'trip_detail.html', {
        'trip': trip,
        'itinerary': itinerary,
        'forecast': forecast,
        'spent': spent,
        'geoapify_api_key': GEOAPIFY_API or '',
    })


def _calculate_spent(itinerary):
    """Sum up activity costs from itinerary JSON."""
    if not itinerary or not isinstance(itinerary, dict):
        return 0
    total = 0
    for day in itinerary.get('itinerary', []):
        for act in day.get('activities', []):
            cost_raw = act.get('cost', '0')
            try:
                cost_clean = str(cost_raw).replace(',', '').replace('₹', '').replace('$', '').replace('€', '').replace('£', '').strip()
                total += float(cost_clean or 0)
            except (ValueError, TypeError):
                pass
    return round(total, 2)


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


def send_whatsapp_reminder_view(request, trip_id):
    """Resend WhatsApp notification"""
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
    """Resend ticket email"""
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


# ---------------------------------------------------------------------------
# Public sharing
# ---------------------------------------------------------------------------

def share_trip_view(request, trip_id):
    """Generate (or return existing) share slug; optionally send email invite."""
    if not request.user.is_authenticated:
        return redirect('register')

    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    trip.generate_share_slug()

    if request.method == 'POST':
        invite_email = request.POST.get('invite_email', '').strip()
        if invite_email:
            public_url = request.build_absolute_uri(f'/p/{trip.share_slug}/')
            try:
                send_mail(
                    subject=f"You've been invited to view a travel itinerary: {trip.destination}",
                    message=(
                        f"Hi there!\n\n"
                        f"{request.user.username} has shared their travel itinerary to {trip.destination} with you.\n\n"
                        f"View the itinerary here (no login required):\n{public_url}\n\n"
                        f"Travel dates: {trip.start_date} → {trip.end_date}\n\n"
                        f"Enjoy planning! 🌍"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[invite_email],
                    fail_silently=True,
                )
                messages.success(request, f"Invite sent to {invite_email}!")
            except Exception as e:
                messages.error(request, f"Could not send invite: {e}")

    public_url = request.build_absolute_uri(f'/p/{trip.share_slug}/')
    return render(request, 'share_trip.html', {'trip': trip, 'public_url': public_url})


def public_trip_view(request, slug):
    """Read-only public view of a trip (no login required)."""
    trip = get_object_or_404(Trip, share_slug=slug)

    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}

    forecast = []
    if trip.weather:
        try:
            forecast = json.loads(trip.weather)
            if not isinstance(forecast, list):
                forecast = []
        except (json.JSONDecodeError, TypeError):
            forecast = []

    spent = _calculate_spent(itinerary)

    return render(request, 'public_trip.html', {
        'trip': trip,
        'itinerary': itinerary,
        'forecast': forecast,
        'spent': spent,
        'geoapify_api_key': GEOAPIFY_API or '',
    })


# ---------------------------------------------------------------------------
# Auth – logout
# ---------------------------------------------------------------------------

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('register')


def landing_page(request):
    return render(request, 'landing.html')

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


def generate_itinerary_with_ai(destination, days, budget, travelers, interests):
    """Generate travel itinerary using OpenRouter AI"""
    
    prompt = f"""
    Create a detailed {days}-day travel itinerary for {destination} for {travelers} traveler(s) with a budget of ₹{budget:,.2f} Indian Rupees.
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
                        "cost": "₹500",
                        "duration": "2 hours",
                        "type": "sightseeing/food/adventure/etc"
                    }}
                ],
                "total_cost": "₹2,500"
            }}
        ],
        "summary": {{
            "total_estimated_cost": "₹{budget:,.2f}",
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
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
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
        'itinerary_summary': itinerary.get('summary', {}),
        'daily_plans': itinerary.get('itinerary', []),
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
    """Send WhatsApp notification using FREE WhatsApp API"""
    try:
        if not trip.phone_number:
            return False
            

        phone_number = ''.join(filter(str.isdigit, trip.phone_number))
        

        if not phone_number.startswith('91') and len(phone_number) == 10:
            phone_number = '91' + phone_number
        
        ticket_data = generate_ticket_data(trip, itinerary)
        

        message = f"""🎫 *Travel Booking Confirmed!*

*Booking Reference:* {ticket_data['booking_reference']}
*Destination:* {trip.destination}
*Travel Dates:* {trip.start_date} to {trip.end_date}
*Duration:* {trip.duration_days} days
*Travelers:* {trip.travelers}
*Total Budget:* {trip.formatted_budget}

Your detailed itinerary has been sent to your email: {trip.user.email}

Thank you for choosing TravelPlanner! 🌍

_This is an automated message. Please do not reply._"""
        

        encoded_message = urllib.parse.quote(message)
        

        whatsapp_url = f"https://wa.me/{phone_number}?text={encoded_message}"
        
        return whatsapp_url
        
    except Exception as e:
        print(f"WhatsApp notification error: {e}")
        return False

def send_sms_notification(trip, itinerary):
    """Send SMS notification - Always return True for demo"""
    try:

        print(f"SMS would be sent to: {trip.phone_number}")
        return True
        
    except Exception as e:
        print(f"SMS sending error: {e}")
        return False



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
            

            sms_sent = send_sms_notification(trip, itinerary)
            
            if email_sent:
                messages.success(request, "🎫 Booking confirmed! Tickets sent to your email.")
                
                if whatsapp_url:
                    messages.info(request, 
                        f"📱 WhatsApp notification ready! <a href='{whatsapp_url}' target='_blank' class='alert-link'>Click here to send WhatsApp message</a>", 
                        extra_tags='safe'
                    )
                
                if sms_sent:
                    messages.info(request, "📲 SMS notification sent to your phone.")
                    
            else:
                messages.error(request, "Failed to send tickets. Please try again.")
                
        except Exception as e:
            messages.error(request, f"Booking failed: {str(e)}")
        
        return redirect('trip_detail', trip_id=trip.id)
    
    return render(request, 'book_trip.html', {
        'trip': trip,
        'itinerary': itinerary
    })



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

                if 'phone_number' in request.session:
                    del request.session['phone_number']

            try:

                duration = (trip.end_date - trip.start_date).days
                if duration <= 0:
                    messages.error(request, "End date must be after start date.")
                    return redirect('dashboard')


                weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={trip.destination}&appid={OPENWEATHER_API}&units=metric"
                weather_resp = requests.get(weather_url)
                if weather_resp.status_code == 200:
                    weather_data = weather_resp.json()
                    temp = weather_data['main']['temp']
                    desc = weather_data['weather'][0]['description']
                    trip.weather = f"{temp}°C, {desc}"
                else:
                    trip.weather = "Weather data not available"


                if weather_resp.status_code == 200:
                    weather_data = weather_resp.json()
                    coord = weather_data.get('coord', {})
                    lat, lon = coord.get('lat'), coord.get('lon')

                    if lat and lon:

                        attractions_url = f"https://api.geoapify.com/v2/places?categories=tourism.sights,tourism.attraction&filter=circle:{lon},{lat},5000&limit=10&apiKey={GEOAPIFY_API}"
                        attractions_resp = requests.get(attractions_url)
                        
                        if attractions_resp.status_code == 200:
                            attractions_data = attractions_resp.json()
                            features = attractions_data.get('features', [])
                            attractions = []
                            for feature in features[:5]:
                                name = feature['properties'].get('name')
                                if name:
                                    attractions.append(name)
                            trip.attractions = ", ".join(attractions) if attractions else "No attractions found"


                        hotels_url = f"https://api.geoapify.com/v2/places?categories=accommodation.hotel&filter=circle:{lon},{lat},5000&limit=5&apiKey={GEOAPIFY_API}"
                        hotels_resp = requests.get(hotels_url)
                        
                        if hotels_resp.status_code == 200:
                            hotels_data = hotels_resp.json()
                            features = hotels_data.get('features', [])
                            hotels = []
                            for feature in features[:3]:
                                name = feature['properties'].get('name')
                                if name:
                                    hotels.append(name)
                            trip.hotels = ", ".join(hotels) if hotels else "No hotels found"
                    else:
                        trip.attractions = "Location not found"
                        trip.hotels = "Location not found"


                    if lat and lon:
                        distance_url = f"https://router.project-osrm.org/route/v1/driving/77.5946,12.9716;{lon},{lat}?overview=false"
                        dist_resp = requests.get(distance_url)
                        if dist_resp.status_code == 200:
                            dist_data = dist_resp.json()
                            if dist_data.get('routes'):
                                trip.distance_km = round(dist_data['routes'][0]['distance'] / 1000, 2)


                itinerary_data = generate_itinerary_with_ai(
                    destination=trip.destination,
                    days=duration,
                    budget=trip.budget,
                    travelers=trip.travelers,
                    interests=trip.interests
                )
                
                if 'error' not in itinerary_data:
                    trip.itinerary = json.dumps(itinerary_data)
                else:
                    trip.itinerary = "Itinerary generation failed"

                trip.save()
                messages.success(request, "Trip planned successfully! You can now book and get tickets.")
                

                return redirect('trip_detail', trip_id=trip.id)

            except requests.exceptions.RequestException as e:
                messages.error(request, f"API error: {e}")
            except Exception as e:
                messages.error(request, f"Something went wrong: {e}")

    return render(request, 'dashboard.html', {
        'form': form, 
        'trips': trips, 
        'user': request.user
    })



def trip_detail_view(request, trip_id):
    if not request.user.is_authenticated:
        return redirect('register')
    
    trip = get_object_or_404(Trip, id=trip_id, user=request.user)
    
    itinerary = None
    if trip.itinerary:
        try:
            itinerary = json.loads(trip.itinerary)
        except json.JSONDecodeError:
            itinerary = {"raw_itinerary": trip.itinerary}
    
    return render(request, 'trip_detail.html', {
        'trip': trip,
        'itinerary': itinerary
    })



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



def send_whatsapp_reminder_view(request, trip_id):
    """Resend WhatsApp notification"""
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
    """Resend ticket email"""
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