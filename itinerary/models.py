from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string
import uuid
import secrets


class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=5, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_otp(self):
        self.otp = ''.join(random.choices(string.digits, k=5))
        self.save()
        return self.otp


CURRENCY_CHOICES = [
    ('INR', '₹ INR'),
    ('USD', '$ USD'),
    ('EUR', '€ EUR'),
    ('GBP', '£ GBP'),
    ('JPY', '¥ JPY'),
    ('AUD', 'A$ AUD'),
    ('CAD', 'C$ CAD'),
    ('SGD', 'S$ SGD'),
]

CURRENCY_SYMBOLS = {
    'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£',
    'JPY': '¥', 'AUD': 'A$', 'CAD': 'C$', 'SGD': 'S$',
}


class Trip(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='INR')
    travelers = models.IntegerField(default=1)
    interests = models.CharField(max_length=200, blank=True)
    weather = models.TextField(blank=True)
    weather_forecast = models.TextField(blank=True)  # JSON: 7-day forecast
    hotels = models.TextField(blank=True)
    attractions = models.TextField(blank=True)
    itinerary = models.TextField(blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    # Coordinates for the destination
    dest_lat = models.FloatField(null=True, blank=True)
    dest_lng = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_booked = models.BooleanField(default=False)
    booking_reference = models.CharField(max_length=20, blank=True)
    tickets_sent = models.BooleanField(default=False)
    whatsapp_sent = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True)
    # Public share slug (read-only link token)
    share_slug = models.CharField(max_length=32, unique=True, null=True, blank=True)

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0

    @property
    def currency_symbol(self):
        return CURRENCY_SYMBOLS.get(self.currency, self.currency)

    @property
    def formatted_budget(self):
        if self.budget:
            symbol = self.currency_symbol
            return f"{symbol}{self.budget:,.2f}"
        return "Not specified"

    def generate_booking_reference(self):
        """Generate unique booking reference"""
        if not self.booking_reference:
            self.booking_reference = f"TRP{self.id:06d}{random.randint(1000, 9999)}"
            self.save()
        return self.booking_reference

    def generate_share_slug(self):
        """Generate a unique cryptographically random slug for public sharing."""
        if not self.share_slug:
            self.share_slug = secrets.token_urlsafe(12)
            self.save()
        return self.share_slug

    def __str__(self):
        return f"{self.destination} - {self.user.username}"


class TripInvite(models.Model):
    """Tracks email invites sent for a trip's public share link."""
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite to {self.email} for {self.trip}"
