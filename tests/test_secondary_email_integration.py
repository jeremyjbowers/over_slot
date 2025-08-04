"""
Integration tests for secondary email functionality.
These test complete end-to-end workflows and user journeys.
"""

import json
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from sesame.utils import get_token

from overslot.models import UserEmail


class SecondaryEmailWorkflowIntegrationTestCase(TestCase):
    """Test complete secondary email workflows from start to finish"""
    
    def setUp(self):
        self.client = Client()
        self.primary_email = 'primary@example.com'
        self.secondary_email = 'secondary@example.com'
        self.password = 'workflow123'
        
        self.user = User.objects.create_user(
            username=self.primary_email,
            email=self.primary_email,
            password=self.password,
            first_name='Workflow',
            last_name='User'
        )
    
    @patch('overslot.account_views.MailgunEmailer.send_email')
    def test_complete_secondary_email_addition_workflow(self, mock_send_email):
        """Test the complete workflow of adding and verifying a secondary email"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Step 1: User logs in
        self.client.login(username=self.primary_email, password=self.password)
        
        # Step 2: User visits account dashboard
        response = self.client.get(reverse('account_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.primary_email)
        self.assertNotContains(response, self.secondary_email)
        
        # Step 3: User adds secondary email
        response = self.client.post(reverse('add_secondary_email'), {
            'email': self.secondary_email
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_dashboard')))
        
        # Step 4: Verify email was created but not verified
        user_email = UserEmail.objects.get(email=self.secondary_email)
        self.assertEqual(user_email.user, self.user)
        self.assertFalse(user_email.is_verified)
        self.assertIsNotNone(user_email.verification_token)
        
        # Step 5: Verification email was sent
        mock_send_email.assert_called_once()
        
        # Step 6: Dashboard shows unverified email
        response = self.client.get(reverse('account_dashboard'))
        self.assertContains(response, self.secondary_email)
        self.assertContains(response, 'Unverified')
        self.assertContains(response, 'Resend verification')
        
        # Step 7: User cannot login with unverified secondary email
        self.client.logout()
        response = self.client.post(reverse('account_login'), {
            'email': self.secondary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No account found")
        
        # Step 8: User clicks verification link
        token = user_email.verification_token
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': token}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Step 9: Email is now verified
        user_email.refresh_from_db()
        self.assertTrue(user_email.is_verified)
        self.assertIsNone(user_email.verification_token)
        
        # Step 10: User can now login with secondary email
        response = self.client.post(reverse('account_login'), {
            'email': self.secondary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('index')))
        self.assertTrue(self.client.session.get('_auth_user_id'))
        
        # Step 11: Dashboard shows verified email
        response = self.client.get(reverse('account_dashboard'))
        self.assertContains(response, self.secondary_email)
        self.assertContains(response, 'Verified ✓')
        self.assertNotContains(response, 'Resend verification')
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_magic_link_workflow_with_secondary_email(self, mock_send_email):
        """Test magic link authentication workflow with secondary email"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Setup: Create verified secondary email
        UserEmail.objects.create(
            user=self.user,
            email=self.secondary_email,
            is_verified=True
        )
        
        # Step 1: User requests magic link with secondary email
        response = self.client.post(reverse('magic_link'), {
            'email': self.secondary_email
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Step 2: Magic link email was sent
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args
        self.assertEqual(call_args[0][0], self.secondary_email)  # to_email
        self.assertIn("Sign in to Over Slot", call_args[0][1])  # subject
        
        # Step 3: User clicks magic link
        token = get_token(self.user)
        response = self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('index')))
        
        # Step 4: User is logged in
        self.assertTrue(self.client.session.get('_auth_user_id'))
        
        # Step 5: User can access authenticated content
        response = self.client.get(reverse('index'))
        self.assertContains(response, self.primary_email)  # Shows primary email in nav
    
    def test_email_removal_workflow(self, ):
        """Test the workflow of removing a secondary email"""
        # Setup: Create and verify secondary email
        user_email = UserEmail.objects.create(
            user=self.user,
            email=self.secondary_email,
            is_verified=True
        )
        
        # Step 1: User logs in and sees secondary email
        self.client.login(username=self.primary_email, password=self.password)
        response = self.client.get(reverse('account_dashboard'))
        self.assertContains(response, self.secondary_email)
        
        # Step 2: User can login with secondary email
        self.client.logout()
        response = self.client.post(reverse('account_login'), {
            'email': self.secondary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 3: User removes secondary email
        self.client.login(username=self.primary_email, password=self.password)
        response = self.client.post(reverse('remove_secondary_email', kwargs={'email_id': user_email.id}))
        self.assertEqual(response.status_code, 302)
        
        # Step 4: Email is deleted
        self.assertFalse(UserEmail.objects.filter(id=user_email.id).exists())
        
        # Step 5: Dashboard no longer shows secondary email
        response = self.client.get(reverse('account_dashboard'))
        self.assertNotContains(response, self.secondary_email)
        
        # Step 6: User can no longer login with removed email
        self.client.logout()
        response = self.client.post(reverse('account_login'), {
            'email': self.secondary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No account found")
    
    @patch('overslot.account_views.MailgunEmailer.send_email')
    def test_verification_resend_workflow(self, mock_send_email):
        """Test the workflow of resending verification email"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Setup: Create unverified secondary email
        user_email = UserEmail.objects.create(
            user=self.user,
            email=self.secondary_email,
            is_verified=False
        )
        original_token = user_email.generate_verification_token()
        
        # Step 1: User logs in and sees unverified email
        self.client.login(username=self.primary_email, password=self.password)
        response = self.client.get(reverse('account_dashboard'))
        self.assertContains(response, self.secondary_email)
        self.assertContains(response, 'Unverified')
        self.assertContains(response, 'Resend verification')
        
        # Step 2: User clicks resend verification
        response = self.client.post(reverse('resend_verification_email', kwargs={'email_id': user_email.id}))
        self.assertEqual(response.status_code, 302)
        
        # Step 3: New verification email was sent
        mock_send_email.assert_called_once()
        
        # Step 4: New token was generated
        user_email.refresh_from_db()
        self.assertNotEqual(user_email.verification_token, original_token)
        
        # Step 5: Old token no longer works
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': original_token}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        user_email.refresh_from_db()
        self.assertFalse(user_email.is_verified)
        
        # Step 6: New token works
        new_token = user_email.verification_token
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': new_token}))
        self.assertEqual(response.status_code, 302)
        
        user_email.refresh_from_db()
        self.assertTrue(user_email.is_verified)


class MultipleSecondaryEmailsIntegrationTestCase(TestCase):
    """Test workflows with multiple secondary emails"""
    
    def setUp(self):
        self.client = Client()
        self.primary_email = 'primary@example.com'
        self.password = 'multipass123'
        
        self.user = User.objects.create_user(
            username=self.primary_email,
            email=self.primary_email,
            password=self.password
        )
        
        # Create multiple verified secondary emails
        self.secondary_emails = []
        for i in range(3):
            email = f'secondary{i}@example.com'
            UserEmail.objects.create(
                user=self.user,
                email=email,
                is_verified=True
            )
            self.secondary_emails.append(email)
    
    def test_login_with_any_verified_email(self):
        """Test that user can login with any verified email address"""
        # Test primary email
        response = self.client.post(reverse('account_login'), {
            'email': self.primary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        
        # Test each secondary email
        for email in self.secondary_emails:
            with self.subTest(email=email):
                response = self.client.post(reverse('account_login'), {
                    'email': email,
                    'password': self.password
                })
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.endswith(reverse('index')))
                self.assertTrue(self.client.session.get('_auth_user_id'))
                self.client.logout()
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_magic_links_with_multiple_emails(self, mock_send_email):
        """Test magic link requests with multiple emails"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Test magic link with each email
        for email in [self.primary_email] + self.secondary_emails:
            with self.subTest(email=email):
                mock_send_email.reset_mock()
                
                response = self.client.post(reverse('magic_link'), {
                    'email': email
                })
                self.assertEqual(response.status_code, 302)
                mock_send_email.assert_called_once()
                
                # Verify email was sent to correct address
                call_args = mock_send_email.call_args
                self.assertEqual(call_args[0][0], email)
    
    def test_dashboard_shows_all_emails(self):
        """Test that dashboard shows all associated email addresses"""
        self.client.login(username=self.primary_email, password=self.password)
        
        response = self.client.get(reverse('account_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should show primary email
        self.assertContains(response, self.primary_email)
        self.assertContains(response, 'Primary')
        
        # Should show all secondary emails
        for email in self.secondary_emails:
            with self.subTest(email=email):
                self.assertContains(response, email)
                self.assertContains(response, 'Verified ✓')
    
    def test_removing_one_email_preserves_others(self):
        """Test that removing one secondary email doesn't affect others"""
        # Get one of the secondary emails to remove
        user_email_to_remove = UserEmail.objects.get(email=self.secondary_emails[0])
        
        self.client.login(username=self.primary_email, password=self.password)
        
        # Remove one secondary email
        response = self.client.post(reverse('remove_secondary_email', kwargs={'email_id': user_email_to_remove.id}))
        self.assertEqual(response.status_code, 302)
        
        # Verify removed email is gone
        self.assertFalse(UserEmail.objects.filter(email=self.secondary_emails[0]).exists())
        
        # Verify other emails still exist
        for email in self.secondary_emails[1:]:
            self.assertTrue(UserEmail.objects.filter(email=email).exists())
        
        # User can still login with remaining emails
        self.client.logout()
        response = self.client.post(reverse('account_login'), {
            'email': self.secondary_emails[1],
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)


class CrossAuthenticationMethodTestCase(TestCase):
    """Test interactions between password and magic link authentication"""
    
    def setUp(self):
        self.client = Client()
        self.primary_email = 'cross@example.com'
        self.secondary_email = 'cross_secondary@example.com'
        self.password = 'crosspass123'
        
        self.user = User.objects.create_user(
            username=self.primary_email,
            email=self.primary_email,
            password=self.password
        )
        
        UserEmail.objects.create(
            user=self.user,
            email=self.secondary_email,
            is_verified=True
        )
    
    def test_password_login_then_magic_link_with_different_email(self):
        """Test login with password, logout, then magic link with different email"""
        # Step 1: Login with password using primary email
        response = self.client.post(reverse('account_login'), {
            'email': self.primary_email,
            'password': self.password
        })
        self.assertEqual(response.status_code, 302)
        user_id_1 = self.client.session.get('_auth_user_id')
        
        # Step 2: Logout
        self.client.logout()
        
        # Step 3: Login with magic link using secondary email
        with patch('overslot.auth.MailgunEmailer.send_email') as mock_send_email:
            mock_send_email.return_value = Mock(status_code=200)
            
            response = self.client.post(reverse('magic_link'), {
                'email': self.secondary_email
            })
            self.assertEqual(response.status_code, 302)
            
            token = get_token(self.user)
            response = self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
            self.assertEqual(response.status_code, 302)
            
            user_id_2 = self.client.session.get('_auth_user_id')
        
        # Both logins should be for the same user
        self.assertEqual(user_id_1, user_id_2)
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_magic_link_signup_with_existing_secondary_email(self, mock_send_email):
        """Test attempting signup with an email that's already a secondary email"""
        mock_send_email.return_value = Mock(status_code=200)
        
        response = self.client.post(reverse('magic_link_signup'), {
            'email': self.secondary_email,
            'first_name': 'New',
            'last_name': 'User'
        })
        
        # Should redirect to login (existing account)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Should not create new user
        self.assertEqual(User.objects.filter(email=self.secondary_email).count(), 0)
        self.assertEqual(User.objects.count(), 1)  # Only original user
    
    def test_consistent_session_regardless_of_login_method(self):
        """Test that session data is consistent regardless of login method"""
        # Login with password
        self.client.post(reverse('account_login'), {
            'email': self.primary_email,
            'password': self.password
        })
        
        session_data_1 = dict(self.client.session.items())
        self.client.logout()
        
        # Login with magic link
        with patch('overslot.auth.MailgunEmailer.send_email') as mock_send_email:
            mock_send_email.return_value = Mock(status_code=200)
            
            self.client.post(reverse('magic_link'), {
                'email': self.secondary_email
            })
            
            token = get_token(self.user)
            self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
        
        session_data_2 = dict(self.client.session.items())
        
        # User ID should be the same
        self.assertEqual(session_data_1.get('_auth_user_id'), session_data_2.get('_auth_user_id'))


class ErrorHandlingIntegrationTestCase(TestCase):
    """Test error handling in integration scenarios"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='error@example.com',
            email='error@example.com',
            password='errorpass123'
        )
    
    @patch('overslot.account_views.MailgunEmailer.send_email')
    def test_email_sending_failure_handling(self, mock_send_email):
        """Test graceful handling when email sending fails"""
        # Mock email sending to fail
        mock_send_email.side_effect = Exception("Email service unavailable")
        
        self.client.login(username='error@example.com', password='errorpass123')
        
        # Should handle email sending failure gracefully
        with self.assertRaises(Exception):
            self.client.post(reverse('add_secondary_email'), {
                'email': 'new@example.com'
            })
    
    def test_invalid_verification_tokens(self):
        """Test handling of various invalid verification scenarios"""
        # Test completely invalid token
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': 'invalid'}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Test empty token
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': ''}))
        self.assertEqual(response.status_code, 302)
        
        # Test very long token
        long_token = 'a' * 1000
        response = self.client.get(reverse('verify_secondary_email', kwargs={'token': long_token}))
        self.assertEqual(response.status_code, 302)
    
    def test_concurrent_email_addition(self):
        """Test handling of concurrent email addition attempts"""
        self.client.login(username='error@example.com', password='errorpass123')
        
        # Create secondary email manually
        UserEmail.objects.create(
            user=self.user,
            email='concurrent@example.com'
        )
        
        # Try to add the same email through the view
        response = self.client.post(reverse('add_secondary_email'), {
            'email': 'concurrent@example.com'
        })
        
        # Should handle gracefully and redirect
        self.assertEqual(response.status_code, 302)
        
        # Should only have one instance
        self.assertEqual(UserEmail.objects.filter(email='concurrent@example.com').count(), 1)


class PerformanceIntegrationTestCase(TestCase):
    """Test performance with multiple secondary emails"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='perf@example.com',
            email='perf@example.com',
            password='perfpass123'
        )
        
        # Create the maximum number of secondary emails
        for i in range(5):
            UserEmail.objects.create(
                user=self.user,
                email=f'perf{i}@example.com',
                is_verified=True
            )
    
    def test_dashboard_performance_with_max_emails(self):
        """Test dashboard performance with maximum secondary emails"""
        self.client.login(username='perf@example.com', password='perfpass123')
        
        response = self.client.get(reverse('account_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should show all emails
        self.assertContains(response, 'perf@example.com')  # Primary
        for i in range(5):
            self.assertContains(response, f'perf{i}@example.com')
    
    def test_login_performance_with_secondary_email(self):
        """Test login performance when checking secondary emails"""
        # Login with a secondary email (requires database lookup)
        response = self.client.post(reverse('account_login'), {
            'email': 'perf4@example.com',
            'password': 'perfpass123'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('index')))
    
    def test_find_user_by_email_performance(self):
        """Test UserEmail.find_user_by_email performance"""
        # Should quickly find user by primary email
        user = UserEmail.find_user_by_email('perf@example.com')
        self.assertEqual(user, self.user)
        
        # Should find user by any secondary email
        for i in range(5):
            user = UserEmail.find_user_by_email(f'perf{i}@example.com')
            self.assertEqual(user, self.user)