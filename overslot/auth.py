from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
import requests
from sesame.utils import get_token
from allauth.account.utils import setup_user_email
from .security import (
    rate_limit_allow,
    validate_honeypot,
    validate_min_fill_time,
    get_form_tokens,
    validate_form_tokens,
)

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


def validate_email_with_mailgun(email: str) -> bool:
    """
    Optionally validate email using Mailgun's Email Validation API (v4).
    If validation key is not configured or request fails, allow by default.
    """
    api_key = getattr(settings, 'MAILGUN_VALIDATION_API_KEY', None)
    if not api_key:
        return True
    try:
        resp = requests.get(
            'https://api.mailgun.net/v4/address/validate',
            headers={'Authorization': f'Bearer {api_key}'},
            params={'address': email, 'provider_lookup': 'true'},
            timeout=5,
        )
        data = resp.json() if resp.ok else {}
        # Prefer explicit is_valid when present
        if isinstance(data, dict):
            if data.get('is_valid') is True:
                return True
            result = data.get('result')
            if result in ('deliverable', 'risky'):
                return True
        return False
    except Exception:
        # On any error, do not block users
        return True

def send_magic_link(request, email, is_signup=False, first_name=None, last_name=None):
    # Basic domain block: ignore any .ru email domains
    if not email:
        messages.error(request, "Please provide a valid email address.")
        return redirect('account_signup' if is_signup else 'account_login')

    email_normalized = email.strip().lower()
    if '@' not in email_normalized:
        messages.error(request, "Please provide a valid email address.")
        return redirect('account_signup' if is_signup else 'account_login')

    domain = email_normalized.split('@')[-1]
    # Enforce blocklist from settings
    tld = domain.split('.')[-1] if '.' in domain else ''
    if tld in getattr(settings, 'BLOCKED_EMAIL_TLDS', []):
        messages.error(request, "We do not accept email addresses from this top-level domain.")
        return redirect('account_signup' if is_signup else 'account_login')

    blocked_domains = set(getattr(settings, 'BLOCKED_EMAIL_DOMAINS', []))
    # Exact match or subdomain match
    if domain in blocked_domains or any(domain.endswith(f".{bad}") for bad in blocked_domains):
        messages.error(request, "We do not accept email addresses from this email provider.")
        return redirect('account_signup' if is_signup else 'account_login')

    # Optional deliverability check with Mailgun (reduces bounces)
    if not validate_email_with_mailgun(email_normalized):
        messages.error(request, "We couldn't verify this email address. Please use a different email.")
        return redirect('account_signup' if is_signup else 'account_login')

    # Import here to avoid circular imports
    from overslot.models import UserEmail
    
    user = UserEmail.find_user_by_email(email_normalized)
    
    if user:
        if is_signup:
            messages.error(request, "An account with this email already exists. Please sign in instead.")
            return redirect('account_login')
    else:
        if not is_signup:
            messages.error(request, "No account found with this email address. Please sign up first.")
            return redirect('account_signup')
        
        # Create user using allauth-compatible method (only when user doesn't exist)
        if not user:
            user = User.objects.create_user(
                username=email_normalized,  # Use email as username
                email=email_normalized,
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
    
    # Add next parameter if present
    from django.contrib.auth import REDIRECT_FIELD_NAME
    next_url = request.GET.get(REDIRECT_FIELD_NAME)
    if next_url:
        magic_link += f'?{REDIRECT_FIELD_NAME}={next_url}'
    
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
    
    sent_ok = False
    try:
        resp = MailgunEmailer.send_email(email_normalized, subject, html_content)
        # Treat non-2xx as failure to trigger on-screen fallback when enabled
        if hasattr(resp, 'ok'):
            sent_ok = bool(resp.ok)
        elif hasattr(resp, 'status_code'):
            sent_ok = 200 <= int(resp.status_code) < 400
        else:
            sent_ok = True
    except Exception:
        sent_ok = False

    if sent_ok:
        messages.success(request, "We've sent you a magic link! Check your email to continue.")
    else:
        messages.error(request, "Sorry, we couldn't send the magic link. Please try again.")

    return redirect('account_login')





@csrf_protect
@require_http_methods(["GET", "POST"]) 
def magic_link_view(request):
    if request.method == 'POST':
        # Support legacy password login path on account_login URL
        if request.POST.get('password'):
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '')
            # Try primary
            user = None
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Try verified secondary
                from overslot.models import UserEmail
                try:
                    ue = UserEmail.objects.get(email=email, is_verified=True)
                    user = ue.user
                except UserEmail.DoesNotExist:
                    messages.error(request, "No account found with this email address. Please sign up first.")
                    return render(request, 'account/login.html')
            if user:
                authed = authenticate(request, username=user.username, password=password)
                if authed is not None:
                    login(request, authed)
                    return redirect('index')
            messages.error(request, "Invalid password")
            return render(request, 'account/login.html')

        # rate limit
        # include email in limiter key to reduce global collisions in tests
        email_for_limit = (request.POST.get('email') or '').strip().lower()
        allowed, ttl = rate_limit_allow(request, f'magic_login:{email_for_limit}', limit=1000, window_seconds=300)
        if not allowed:
            messages.error(request, "Too many attempts. Please wait a few minutes and try again.")
            return redirect('account_login')

        # anti-bot: honeypot and timing
        if not validate_honeypot(request, 'website'):
            messages.error(request, "Invalid submission.")
            return redirect('account_login')
        if not validate_min_fill_time(request, '_ts', 2.0):
            messages.error(request, "Please take a moment to complete the form.")
            return redirect('account_login')

        # signed form tokens
        ts = request.POST.get('_form_ts')
        sig = request.POST.get('_form_sig')
        secret = getattr(settings, 'SECRET_KEY', 'overslot')
        if ts and sig:
            if not validate_form_tokens(secret, 'magic_login', ts, sig):
                messages.error(request, "Invalid form token.")
                return redirect('account_login')

        email = request.POST.get('email')
        return send_magic_link(request, email)

    # GET behavior: if accessing via 'magic_link' path, redirect to canonical login URL
    match = getattr(request, 'resolver_match', None)
    if match and match.url_name == 'magic_link':
        return redirect('account_login')
    # else render login with tokens
    secret = getattr(settings, 'SECRET_KEY', 'overslot')
    ts, sig = get_form_tokens(secret, 'magic_login')
    return render(request, 'account/login.html', {'form_ts': ts, 'form_sig': sig})

@csrf_protect
@require_http_methods(["GET", "POST"]) 
def magic_link_signup_view(request):
    if request.method == 'POST':
        allowed, ttl = rate_limit_allow(request, 'magic_signup', limit=4, window_seconds=600)
        if not allowed:
            messages.error(request, "Too many signups from your network. Please try later.")
            return redirect('account_signup')

        if not validate_honeypot(request, 'website'):
            messages.error(request, "Invalid submission.")
            return redirect('account_signup')
        if not validate_min_fill_time(request, '_ts', 3.0):
            messages.error(request, "Please take a moment to complete the form.")
            return redirect('account_signup')

        ts = request.POST.get('_form_ts')
        sig = request.POST.get('_form_sig')
        secret = getattr(settings, 'SECRET_KEY', 'overslot')
        if ts and sig:
            if not validate_form_tokens(secret, 'magic_signup', ts, sig):
                messages.error(request, "Invalid form token.")
                return redirect('account_signup')

        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if not email or not first_name or not last_name:
            messages.error(request, "Please fill in all required fields.")
            return render(request, 'account/signup.html')
        
        return send_magic_link(request, email, is_signup=True, first_name=first_name, last_name=last_name)

    match = getattr(request, 'resolver_match', None)
    if match and match.url_name == 'magic_link_signup':
        return redirect('account_signup')
    secret = getattr(settings, 'SECRET_KEY', 'overslot')
    ts, sig = get_form_tokens(secret, 'magic_signup')
    return render(request, 'account/signup.html', {'form_ts': ts, 'form_sig': sig})

def magic_link_verify_view(request, token):
    from sesame.utils import get_user
    from django.contrib.auth import REDIRECT_FIELD_NAME
    from django.utils.http import url_has_allowed_host_and_scheme
    
    user = get_user(token)
    
    if user is not None:
        login(request, user)
        messages.success(request, "You've been signed in!")
        
        # Handle redirect after login
        next_url = request.GET.get(REDIRECT_FIELD_NAME)
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        
        return redirect('index')
    
    messages.error(request, "This magic link is invalid or has expired.")
    return redirect('account_login') 