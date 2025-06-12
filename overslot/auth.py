from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import get_random_string
import requests
from sesame.utils import get_token
from allauth.account.utils import setup_user_email

class MailgunEmailer:
    @staticmethod
    def send_email(to_email, subject, html_content, text_content=None):
        return requests.post(
            f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages",
            auth=("api", settings.MAILGUN_API_KEY),
            data={
                "from": f"Over Slot <noreply@{settings.MAILGUN_DOMAIN}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content or html_content
            }
        )

def send_magic_link(request, email, is_signup=False, first_name=None, last_name=None):
    try:
        user = User.objects.get(email=email)
        if is_signup:
            messages.error(request, "An account with this email already exists. Please sign in instead.")
            return redirect('account_login')
    except User.DoesNotExist:
        if not is_signup:
            messages.error(request, "No account found with this email address. Please sign up first.")
            return redirect('account_signup')
        
        # Create user using allauth-compatible method
        user = User.objects.create_user(
            username=email,  # Use email as username
            email=email,
            password=get_random_string(32),  # Random password since we're using magic links
            first_name=first_name or '',
            last_name=last_name or ''
        )
        
        # Ensure user is saved to database
        user.save()
        
        # Set up email with allauth (marks email as verified)
        try:
            setup_user_email(request, user, [])
        except Exception as e:
            pass  # Continue even if allauth setup fails

    token = get_token(user)
    magic_link = request.build_absolute_uri(
        reverse('magic_link_verify', kwargs={'token': token})
    )
    # Force HTTPS for magic links
    if magic_link.startswith('http://'):
        magic_link = magic_link.replace('http://', 'https://', 1)

    # Send email with magic link
    subject = "Welcome to Over Slot!" if is_signup else "Sign in to Over Slot"
    html_content = render_to_string('auth/email/magic_link.html', {
        'magic_link': magic_link,
        'is_signup': is_signup,
        'user': user,
        'first_name': user.first_name
    })
    
    try:
        MailgunEmailer.send_email(email, subject, html_content)
        messages.success(
            request,
            "We've sent you a magic link! Check your email to continue."
        )
    except Exception as e:
        messages.error(
            request,
            "Sorry, we couldn't send the magic link. Please try again or use password authentication."
        )

    return redirect('account_login')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "No account found with this email address.")
            return render(request, 'auth/login.html')
        
        user = authenticate(username=user.username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            messages.error(request, "Invalid password.")
            return render(request, 'auth/login.html')
    
    return render(request, 'auth/login.html')

def signup_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, 'auth/signup.html')

        if password1 != password2:
            messages.error(request, "Passwords don't match.")
            return render(request, 'auth/signup.html')

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password1
        )
        login(request, user)
        messages.success(request, "Account created successfully!")
        return redirect('index')

    return render(request, 'auth/signup.html')

def magic_link_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        return send_magic_link(request, email)
    return redirect('account_login')

def magic_link_signup_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        # Validate required fields
        if not email or not first_name or not last_name:
            messages.error(request, "Please fill in all required fields.")
            return render(request, 'account/signup.html')
        
        return send_magic_link(request, email, is_signup=True, first_name=first_name, last_name=last_name)
    return redirect('account_signup')

def magic_link_verify_view(request, token):
    from sesame.utils import get_user
    
    user = get_user(token)
    
    if user is not None:
        login(request, user)
        messages.success(request, "You've been signed in!")
        return redirect('index')
    
    messages.error(request, "This magic link is invalid or has expired.")
    return redirect('account_login') 