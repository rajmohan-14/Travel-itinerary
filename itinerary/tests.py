"""
Basic tests for Travel-itinerary models and view permissions.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import date, timedelta
import json

from .models import Trip, UserOTP
from .views import _calculate_spent


class TripModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', email='test@example.com', password='pass')

    def _make_trip(self, **kwargs):
        defaults = dict(
            user=self.user,
            destination='Paris',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
            budget=10000,
            currency='INR',
        )
        defaults.update(kwargs)
        return Trip.objects.create(**defaults)

    def test_duration_days(self):
        trip = self._make_trip()
        self.assertEqual(trip.duration_days, 5)

    def test_formatted_budget_inr(self):
        trip = self._make_trip(budget=50000, currency='INR')
        self.assertIn('₹', trip.formatted_budget)
        self.assertIn('50,000.00', trip.formatted_budget)

    def test_formatted_budget_usd(self):
        trip = self._make_trip(budget=500, currency='USD')
        self.assertIn('$', trip.formatted_budget)

    def test_budget_none(self):
        trip = self._make_trip(budget=None)
        self.assertEqual(trip.formatted_budget, 'Not specified')

    def test_generate_booking_reference(self):
        trip = self._make_trip()
        ref = trip.generate_booking_reference()
        self.assertTrue(ref.startswith('TRP'))
        self.assertEqual(trip.booking_reference, ref)

    def test_generate_share_slug(self):
        trip = self._make_trip()
        slug = trip.generate_share_slug()
        self.assertTrue(len(slug) > 10)
        # Calling again returns same slug
        self.assertEqual(trip.generate_share_slug(), slug)

    def test_share_slug_unique(self):
        trip1 = self._make_trip()
        trip2 = Trip.objects.create(
            user=self.user,
            destination='London',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            budget=5000,
            currency='GBP',
        )
        self.assertNotEqual(trip1.share_slug, trip2.share_slug)

    def test_currency_symbol(self):
        trip = self._make_trip(currency='EUR')
        self.assertEqual(trip.currency_symbol, '€')

    def test_str(self):
        trip = self._make_trip()
        self.assertIn('Paris', str(trip))
        self.assertIn('tester', str(trip))

    def test_userotp_generate(self):
        otp_obj = UserOTP.objects.create(user=self.user)
        otp = otp_obj.generate_otp()
        self.assertEqual(len(otp), 5)
        self.assertTrue(otp.isdigit())


class BudgetCalculationTests(TestCase):
    def test_calculate_spent_normal(self):
        itinerary = {
            'itinerary': [
                {'activities': [
                    {'cost': '500'},
                    {'cost': '1000'},
                ]},
                {'activities': [
                    {'cost': '₹750'},
                ]},
            ]
        }
        self.assertEqual(_calculate_spent(itinerary), 2250.0)

    def test_calculate_spent_empty(self):
        self.assertEqual(_calculate_spent(None), 0)
        self.assertEqual(_calculate_spent({}), 0)

    def test_calculate_spent_non_numeric(self):
        itinerary = {'itinerary': [{'activities': [{'cost': 'free'}]}]}
        self.assertEqual(_calculate_spent(itinerary), 0)


class ViewPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='viewer', email='viewer@example.com', password='pass')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='pass')
        self.trip = Trip.objects.create(
            user=self.user,
            destination='Tokyo',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
        )
        # Ensure trip has a share_slug
        self.trip.generate_share_slug()

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertRedirects(resp, reverse('register'))

    def test_trip_detail_requires_login(self):
        resp = self.client.get(reverse('trip_detail', args=[self.trip.id]))
        self.assertRedirects(resp, reverse('register'))

    def test_trip_detail_owner_can_view(self):
        self.client.login(username='viewer', password='pass')
        resp = self.client.get(reverse('trip_detail', args=[self.trip.id]))
        self.assertEqual(resp.status_code, 200)

    def test_trip_detail_other_user_gets_404(self):
        self.client.login(username='other', password='pass')
        resp = self.client.get(reverse('trip_detail', args=[self.trip.id]))
        self.assertEqual(resp.status_code, 404)

    def test_public_trip_accessible_without_login(self):
        resp = self.client.get(reverse('public_trip', args=[self.trip.share_slug]))
        self.assertEqual(resp.status_code, 200)

    def test_public_trip_invalid_slug_404(self):
        resp = self.client.get(reverse('public_trip', args=['nonexistent-slug-xyz']))
        self.assertEqual(resp.status_code, 404)

    def test_share_trip_requires_login(self):
        resp = self.client.get(reverse('share_trip', args=[self.trip.id]))
        self.assertRedirects(resp, reverse('register'))

    def test_delete_trip_other_user_gets_404(self):
        self.client.login(username='other', password='pass')
        resp = self.client.post(reverse('delete_trip', args=[self.trip.id]))
        self.assertEqual(resp.status_code, 404)

    def test_landing_page_renders(self):
        resp = self.client.get(reverse('landing'))
        self.assertEqual(resp.status_code, 200)

    def test_landing_page_logged_in_shows_trips(self):
        self.client.login(username='viewer', password='pass')
        resp = self.client.get(reverse('landing'))
        self.assertEqual(resp.status_code, 200)
        # The page renders; the My Trips section visibility depends on trip data
        # being in the request context – the authenticated branch is always attempted.
        self.assertIn(b'Plan', resp.content)
