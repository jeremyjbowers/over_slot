"""
Tests for email styling and template consistency.
"""

from django.test import TestCase
from django.template.loader import render_to_string
from django.contrib.auth.models import User
from overslot.models import UserEmail


class EmailStyleTestCase(TestCase):
    """Test email template rendering and style consistency"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            first_name='Test',
            last_name='User'
        )
    
    def test_magic_link_email_renders_for_login(self):
        """Test magic link email renders correctly for login"""
        html_content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic-link/token123',
            'is_signup': False,
            'user': self.user,
            'first_name': self.user.first_name
        })
        
        # Check content structure
        self.assertIn('Over Slot', html_content)
        self.assertIn('Sign In', html_content)
        self.assertIn('Sign in to Over Slot', html_content)
        self.assertIn('Hi Test!', html_content)
        self.assertIn('https://example.com/magic-link/token123', html_content)
        
        # Check consistent button styling
        self.assertIn('background-color: #1d4ed8', html_content)
        self.assertIn('color: #ffffff', html_content)
        self.assertIn('font-weight: 600', html_content)
        
        # Check fallback link
        self.assertIn('Button not working?', html_content)
        self.assertIn('email-fallback-link', html_content)
    
    def test_magic_link_email_renders_for_signup(self):
        """Test magic link email renders correctly for signup"""
        html_content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic-link/token456',
            'is_signup': True,
            'user': self.user,
            'first_name': self.user.first_name
        })
        
        # Check signup-specific content
        self.assertIn('Welcome to Over Slot, Test!', html_content)
        self.assertIn('Create Account', html_content)
        self.assertIn('Thank you for joining', html_content)
        
        # Check info box for new users
        self.assertIn('What\'s next?', html_content)
        self.assertIn('premium baseball scouting', html_content)
        
        # Check consistent styling
        self.assertIn('background-color: #1d4ed8', html_content)
        self.assertIn('email-button', html_content)
    
    def test_secondary_email_verification_renders(self):
        """Test secondary email verification email renders correctly"""
        secondary_email = 'secondary@example.com'
        verification_link = 'https://example.com/verify/token789'
        
        html_content = render_to_string('account/email/verify_secondary_email.html', {
            'verification_link': verification_link,
            'user': self.user,
            'email': secondary_email,
        })
        
        # Check content structure
        self.assertIn('Verify your secondary email', html_content)
        self.assertIn('Hi Test,', html_content)
        self.assertIn(secondary_email, html_content)
        self.assertIn(verification_link, html_content)
        
        # Check button styling consistency
        self.assertIn('Verify Email Address', html_content)
        self.assertIn('background-color: #1d4ed8', html_content)
        self.assertIn('color: #ffffff', html_content)
        
        # Check info box
        self.assertIn('What happens after verification?', html_content)
        self.assertIn('email-info-box', html_content)
        
        # Check fallback link
        self.assertIn('Button not working?', html_content)
        self.assertIn('email-fallback-link', html_content)
    
    def test_consistent_button_styling_across_templates(self):
        """Test that button styling is consistent across all email templates"""
        # Magic link email
        magic_content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic',
            'is_signup': False,
            'user': self.user
        })
        
        # Verification email
        verify_content = render_to_string('account/email/verify_secondary_email.html', {
            'verification_link': 'https://example.com/verify',
            'user': self.user,
            'email': 'test@example.com'
        })
        
        # Check consistent button properties
        button_properties = [
            'background-color: #1d4ed8',
            'color: #ffffff',
            'font-weight: 600',
            'padding: 16px 32px',
            'border-radius: 6px',
            'text-decoration: none'
        ]
        
        for prop in button_properties:
            self.assertIn(prop, magic_content, f"Magic link email missing: {prop}")
            self.assertIn(prop, verify_content, f"Verification email missing: {prop}")
    
    def test_fallback_links_present(self):
        """Test that all emails include fallback text links"""
        # Test magic link email
        magic_content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic-token',
            'is_signup': False,
            'user': self.user
        })
        
        self.assertIn('Button not working?', magic_content)
        self.assertIn('email-fallback-link', magic_content)
        self.assertIn('https://example.com/magic-token', magic_content)
        
        # Test verification email
        verify_content = render_to_string('account/email/verify_secondary_email.html', {
            'verification_link': 'https://example.com/verify-token',
            'user': self.user,
            'email': 'test@example.com'
        })
        
        self.assertIn('Button not working?', verify_content)
        self.assertIn('email-fallback-link', verify_content)
        self.assertIn('https://example.com/verify-token', verify_content)
    
    def test_base_template_structure(self):
        """Test that all emails use the base template structure"""
        templates_to_test = [
            ('auth/email/magic_link.html', {
                'magic_link': 'https://example.com/magic',
                'is_signup': False,
                'user': self.user
            }),
            ('account/email/verify_secondary_email.html', {
                'verification_link': 'https://example.com/verify',
                'user': self.user,
                'email': 'test@example.com'
            })
        ]
        
        for template, context in templates_to_test:
            with self.subTest(template=template):
                content = render_to_string(template, context)
                
                # Check base template elements
                self.assertIn('email-container', content)
                self.assertIn('email-header', content)
                self.assertIn('email-content', content)
                self.assertIn('email-footer', content)
                self.assertIn('Over Slot', content)  # Logo
                self.assertIn('The Over Slot Team', content)  # Footer signature
    
    def test_accessibility_features(self):
        """Test that emails include accessibility features"""
        content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic',
            'is_signup': False,
            'user': self.user
        })
        
        # Check semantic HTML structure
        self.assertIn('<h1 class="email-title">', content)
        self.assertIn('<p class="email-text">', content)
        
        # Check proper link structure
        self.assertIn('href="https://example.com/magic"', content)
        
        # Check fallback content for screen readers
        self.assertIn('Button not working?', content)
    
    def test_mobile_responsive_classes(self):
        """Test that emails include mobile-responsive CSS classes"""
        content = render_to_string('account/email/verify_secondary_email.html', {
            'verification_link': 'https://example.com/verify',
            'user': self.user,
            'email': 'test@example.com'
        })
        
        # Check responsive classes are present
        responsive_classes = [
            'email-container',
            'email-header',
            'email-content', 
            'email-footer',
            'email-button-container',
            'email-button'
        ]
        
        for css_class in responsive_classes:
            self.assertIn(css_class, content)
        
        # Check mobile CSS is present
        self.assertIn('@media only screen and (max-width: 640px)', content)


class EmailContentTestCase(TestCase):
    """Test email content for quality and completeness"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='content@example.com',
            email='content@example.com',
            first_name='Content',
            last_name='Tester'
        )
    
    def test_personalization_works(self):
        """Test that email personalization works correctly"""
        # Test with first name
        content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic',
            'is_signup': False,
            'user': self.user,
            'first_name': 'Content'
        })
        
        self.assertIn('Hi Content!', content)
        
        # Test without first name
        user_no_name = User.objects.create_user(
            username='noname@example.com',
            email='noname@example.com'
        )
        
        content = render_to_string('account/email/verify_secondary_email.html', {
            'verification_link': 'https://example.com/verify',
            'user': user_no_name,
            'email': 'test@example.com'
        })
        
        self.assertIn('Hi noname@example.com,', content)
    
    def test_security_messaging(self):
        """Test that security messaging is consistent and clear"""
        templates_contexts = [
            ('auth/email/magic_link.html', {
                'magic_link': 'https://example.com/magic',
                'is_signup': False,
                'user': self.user
            }),
            ('account/email/verify_secondary_email.html', {
                'verification_link': 'https://example.com/verify',
                'user': self.user,
                'email': 'test@example.com'
            })
        ]
        
        for template, context in templates_contexts:
            with self.subTest(template=template):
                content = render_to_string(template, context)
                
                # Check security notices
                self.assertIn('Security notice:', content)
                self.assertIn('24 hours', content)
                self.assertIn('safely ignore', content)
    
    def test_brand_consistency(self):
        """Test that brand elements are consistent"""
        content = render_to_string('auth/email/magic_link.html', {
            'magic_link': 'https://example.com/magic',
            'is_signup': True,
            'user': self.user
        })
        
        # Check brand elements
        self.assertIn('Over Slot', content)
        self.assertIn('The Over Slot Team', content)
        self.assertIn('premium baseball scouting', content)
        
        # Check tone consistency
        self.assertIn('Thank you for joining', content)
        self.assertIn('Best regards', content)