from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
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
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    destination = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    travelers = models.IntegerField(default=1)
    interests = models.CharField(max_length=200, blank=True)
    weather = models.TextField(blank=True)
    hotels = models.TextField(blank=True)
    attractions = models.TextField(blank=True)
    itinerary = models.TextField(blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_booked = models.BooleanField(default=False)
    booking_reference = models.CharField(max_length=20, blank=True)
    tickets_sent = models.BooleanField(default=False)
    whatsapp_sent = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True)  # Add phone number field

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0

    @property
    def formatted_budget(self):
        if self.budget:
            return f"₹{self.budget:,.2f}"
        return "Not specified"

    def generate_booking_reference(self):
        """Generate unique booking reference"""
        if not self.booking_reference:
            self.booking_reference = f"TRP{self.id:06d}{random.randint(1000, 9999)}"
            self.save()
        return self.booking_reference

    def __str__(self):
        return f"{self.destination} - {self.user.username}"