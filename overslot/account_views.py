from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.template.loader import render_to_string
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.crypto import get_random_string

from overslot.models import UserEmail
from overslot.auth import MailgunEmailer


@login_required
def account_dashboard(request):
    """
    Main account dashboard showing user's primary and secondary emails
    """
    user = request.user
    secondary_emails = UserEmail.objects.filter(user=user)
    
    context = {
        'user': user,
        'secondary_emails': secondary_emails,
    }
    return render(request, 'account/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def add_secondary_email(request):
    """
    Add a new secondary email address to the user's account
    """
    email = request.POST.get('email', '').strip().lower()
    user = request.user
    
    if not email:
        messages.error(request, "Please enter a valid email address.")
        return redirect('account_dashboard')
    
    # Check if email is already the user's primary email
    if email == user.email:
        messages.error(request, "This is already your primary email address.")
        return redirect('account_dashboard')
    
    # Check if email already exists (either as primary or secondary)
    existing_user = UserEmail.find_user_by_email(email)
    if existing_user:
        if existing_user == user:
            messages.error(request, "This email is already associated with your account.")
        else:
            messages.error(request, "This email address is already in use by another account.")
        return redirect('account_dashboard')
    
    # Check if user already has too many secondary emails (limit to 5)
    if UserEmail.objects.filter(user=user).count() >= 5:
        messages.error(request, "You can only have up to 5 secondary email addresses.")
        return redirect('account_dashboard')
    
    # Create the secondary email
    user_email = UserEmail.objects.create(
        user=user,
        email=email,
        is_verified=False
    )
    
    # Generate verification token and send email
    token = user_email.generate_verification_token()
    send_verification_email(request, user_email, token)
    
    messages.success(request, f"We've sent a verification email to {email}. Please check your inbox and click the verification link.")
    return redirect('account_dashboard')


@login_required
@require_http_methods(["POST"])
def remove_secondary_email(request, email_id):
    """
    Remove a secondary email address from the user's account
    """
    user_email = get_object_or_404(UserEmail, id=email_id, user=request.user)
    email_address = user_email.email
    user_email.delete()
    
    messages.success(request, f"Removed {email_address} from your account.")
    return redirect('account_dashboard')


@require_http_methods(["GET"])
def verify_secondary_email(request, token):
    """
    Verify a secondary email address using the verification token
    """
    try:
        user_email = UserEmail.objects.get(verification_token=token, is_verified=False)
    except UserEmail.DoesNotExist:
        messages.error(request, "Invalid or expired verification link.")
        return redirect('account_login')
    
    # Mark as verified and clear the token
    user_email.is_verified = True
    user_email.verification_token = None
    user_email.save()
    
    messages.success(request, f"Successfully verified {user_email.email}! You can now use this email to sign in.")
    
    # If user is logged in, redirect to dashboard, otherwise to login
    if request.user.is_authenticated:
        return redirect('account_dashboard')
    else:
        return redirect('account_login')


@login_required
@require_http_methods(["POST"])
def resend_verification_email(request, email_id):
    """
    Resend verification email for a secondary email address
    """
    user_email = get_object_or_404(UserEmail, id=email_id, user=request.user, is_verified=False)
    
    # Generate new verification token and send email
    token = user_email.generate_verification_token()
    send_verification_email(request, user_email, token)
    
    messages.success(request, f"Verification email resent to {user_email.email}.")
    return redirect('account_dashboard')


def send_verification_email(request, user_email, token):
    """
    Send verification email for a secondary email address
    """
    verification_link = request.build_absolute_uri(
        reverse('verify_secondary_email', kwargs={'token': token})
    )
    
    # Force HTTPS for verification links
    if verification_link.startswith('http://'):
        verification_link = verification_link.replace('http://', 'https://', 1)
    
    subject = "Verify your secondary email address - Over Slot"
    html_content = render_to_string('account/email/verify_secondary_email.html', {
        'verification_link': verification_link,
        'user': user_email.user,
        'email': user_email.email,
    })
    
    try:
        MailgunEmailer.send_email(user_email.email, subject, html_content)
    except Exception as e:
        # Log the error in production
        raise Exception(f"Failed to send verification email: {str(e)}")