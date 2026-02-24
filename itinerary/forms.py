from django import forms
from django.contrib.auth.models import User
from .models import Trip

class RegisterForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email'
        })
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose a username'
        })
    )
    phone_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone number (for WhatsApp)'
        })
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

class OTPForm(forms.Form):
    otp = forms.CharField(
        max_length=5,
        min_length=5,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 5-digit OTP'
        })
    )

class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ['destination', 'start_date', 'end_date', 'budget', 'travelers', 'interests', 'phone_number']
        widgets = {
            'destination': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Goa, India'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'budget': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Total budget in Indian Rupees (₹)'
            }),
            'travelers': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'interests': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., beaches, temples, food'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'WhatsApp number (with country code)'
            }),
        }
    
    def clean_budget(self):
        budget = self.cleaned_data.get('budget')
        if budget and budget < 0:
            raise forms.ValidationError("Budget cannot be negative.")
        return budget