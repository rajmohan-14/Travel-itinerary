from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import secrets
import string

class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=5, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_otp(self):
        self.otp = ''.join(random.choices(string.digits, k=5))
        self.save()
        return self.otp

class Trip(models.Model):
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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='INR')
    travelers = models.IntegerField(default=1)
    interests = models.CharField(max_length=200, blank=True)
    weather = models.TextField(blank=True)
    hotels = models.TextField(blank=True)
    attractions = models.TextField(blank=True)
    itinerary = models.TextField(blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    # Destination coordinates for map display
    dest_lat = models.FloatField(null=True, blank=True)
    dest_lng = models.FloatField(null=True, blank=True)
    # Public sharing
    share_slug = models.CharField(max_length=40, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_booked = models.BooleanField(default=False)
    booking_reference = models.CharField(max_length=20, blank=True)
    tickets_sent = models.BooleanField(default=False)
    whatsapp_sent = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True)

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0

    @property
    def currency_symbol(self):
        symbols = {'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£',
                   'JPY': '¥', 'AUD': 'A$', 'CAD': 'C$', 'SGD': 'S$'}
        return symbols.get(self.currency, self.currency)

    @property
    def formatted_budget(self):
        if self.budget:
            return f"{self.currency_symbol}{self.budget:,.2f}"
        return "Not specified"

    def generate_booking_reference(self):
        if not self.booking_reference:
            self.booking_reference = f"TRP{self.id:06d}{random.randint(1000, 9999)}"
            self.save()
        return self.booking_reference

    def save(self, *args, **kwargs):
        if not self.share_slug:
            self.share_slug = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def generate_share_slug(self):
        if not self.share_slug:
            self.share_slug = secrets.token_urlsafe(24)
            self.save()
        return self.share_slug

    def __str__(self):
        return f"{self.destination} - {self.user.username}"