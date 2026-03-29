from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import date, timedelta

from .models import Trip, TripInvite, UserOTP


class TripModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tester', email='tester@example.com', password='pw'
        )

    def _make_trip(self, **kwargs):
        defaults = dict(
            user=self.user,
            destination='Paris',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
            budget=1000,
            currency='USD',
        )
        defaults.update(kwargs)
        return Trip.objects.create(**defaults)

    def test_duration_days(self):
        trip = self._make_trip()
        self.assertEqual(trip.duration_days, 5)

    def test_formatted_budget_with_currency(self):
        trip = self._make_trip(budget=1500, currency='USD')
        self.assertIn('$', trip.formatted_budget)
        self.assertIn('1,500', trip.formatted_budget)

    def test_formatted_budget_inr(self):
        trip = self._make_trip(budget=50000, currency='INR')
        self.assertIn('₹', trip.formatted_budget)

    def test_generate_share_slug_is_unique(self):
        trip1 = self._make_trip(destination='Rome')
        trip2 = self._make_trip(destination='Tokyo')
        slug1 = trip1.generate_share_slug()
        slug2 = trip2.generate_share_slug()
        self.assertNotEqual(slug1, slug2)
        self.assertEqual(len(slug1), 16)

    def test_generate_share_slug_idempotent(self):
        trip = self._make_trip()
        slug1 = trip.generate_share_slug()
        slug2 = trip.generate_share_slug()
        self.assertEqual(slug1, slug2)

    def test_currency_symbol_property(self):
        trip = self._make_trip(currency='EUR')
        self.assertEqual(trip.currency_symbol, '€')

    def test_booking_reference_generation(self):
        trip = self._make_trip()
        trip.save()
        ref = trip.generate_booking_reference()
        self.assertTrue(ref.startswith('TRP'))
        self.assertEqual(trip.booking_reference, ref)

    def test_trip_invite_model(self):
        trip = self._make_trip()
        invite = TripInvite.objects.create(trip=trip, email='friend@example.com')
        self.assertEqual(invite.email, 'friend@example.com')
        self.assertEqual(invite.trip, trip)


class TripViewPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pw'
        )
        self.other = User.objects.create_user(
            username='other', email='other@example.com', password='pw'
        )
        self.trip = Trip.objects.create(
            user=self.owner,
            destination='Berlin',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
        )
        self.trip.generate_share_slug()

    def test_unauthenticated_cannot_view_trip_detail(self):
        url = reverse('trip_detail', args=[self.trip.id])
        response = self.client.get(url)
        self.assertRedirects(response, reverse('register'))

    def test_authenticated_owner_can_view_trip_detail(self):
        self.client.force_login(self.owner)
        url = reverse('trip_detail', args=[self.trip.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_owner'])

    def test_other_user_gets_404_on_trip_detail(self):
        self.client.force_login(self.other)
        url = reverse('trip_detail', args=[self.trip.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_public_trip_view_no_auth_required(self):
        url = reverse('public_trip', args=[self.trip.share_slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_owner'])

    def test_public_trip_view_invalid_slug(self):
        url = reverse('public_trip', args=['nonexistent-slug'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_cannot_delete_trip(self):
        url = reverse('delete_trip', args=[self.trip.id])
        response = self.client.post(url)
        self.assertRedirects(response, reverse('register'))

    def test_other_user_cannot_delete_trip(self):
        self.client.force_login(self.other)
        url = reverse('delete_trip', args=[self.trip.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_dashboard_redirects_unauthenticated(self):
        url = reverse('dashboard')
        response = self.client.get(url)
        self.assertRedirects(response, reverse('register'))

    def test_landing_page_accessible(self):
        url = reverse('landing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
