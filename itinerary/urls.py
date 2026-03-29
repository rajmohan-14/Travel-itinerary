# itinerary/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ---------------------- AUTHENTICATION URLs ----------------------
    path('', views.landing_page, name='landing'),
    path('register/', views.register_view, name='register'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    path('logout/', views.logout_view, name='logout'),

    # ---------------------- DASHBOARD & TRIP MANAGEMENT URLs ----------------------
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('trip/<int:trip_id>/', views.trip_detail_view, name='trip_detail'),
    path('trip/<int:trip_id>/book/', views.book_trip_view, name='book_trip'),
    path('trip/<int:trip_id>/delete/', views.delete_trip_view, name='delete_trip'),
    path('trip/<int:trip_id>/share/', views.share_trip_view, name='share_trip'),

    # ---------------------- NOTIFICATION & TICKET URLs ----------------------
    path('trip/<int:trip_id>/resend-email/', views.resend_ticket_email_view, name='resend_ticket_email'),
    path('trip/<int:trip_id>/whatsapp-reminder/', views.send_whatsapp_reminder_view, name='whatsapp_reminder'),

    # ---------------------- PUBLIC SHARE URL ----------------------
    path('trip/share/<str:share_slug>/', views.public_trip_view, name='public_trip'),
]