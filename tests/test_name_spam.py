from io import StringIO
from unittest.mock import patch, Mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from overslot.models import Author, Subscription
from overslot.name_spam import name_contains_domain, name_looks_like_spam, user_is_protected


class NameContainsDomainTestCase(TestCase):
    def test_screenshot_spam_names(self):
        self.assertTrue(name_contains_domain(
            "Claim Your Authentic Money jolpo.kesug.com 7f GJ",
            "Access Your Certified Reward riooep.wuaze.com XB GJ",
        ))
        self.assertTrue(name_contains_domain("Unlock Your VIP Reward jrert.great-site.net HT GJ", "User"))

    def test_common_tlds_and_url_tokens(self):
        self.assertTrue(name_contains_domain("spam.ru", "User"))
        self.assertTrue(name_contains_domain("John", "mailinator.com"))
        self.assertTrue(name_contains_domain("www.example", "User"))
        self.assertTrue(name_contains_domain("Jane", "foo@bar"))
        self.assertTrue(name_contains_domain("http://bad", "User"))

    def test_real_human_names_are_allowed(self):
        self.assertFalse(name_contains_domain("John", "Smith"))
        self.assertFalse(name_contains_domain("J.R.", "Morgan"))
        self.assertFalse(name_contains_domain("Mary-Anne", "O'Connor"))
        self.assertFalse(name_contains_domain("St. John", "Combs"))
        self.assertFalse(name_contains_domain("Dr.Combs", ""))

    def test_looks_like_spam_covers_length_and_substrings(self):
        self.assertTrue(name_looks_like_spam("A" * 61, "User"))
        self.assertTrue(name_looks_like_spam("blogspot fan", "User"))
        self.assertFalse(name_looks_like_spam("Alex", "Garcia"))


class PurgeSpamNameUsersCommandTestCase(TestCase):
    def test_dry_run_lists_but_does_not_delete(self):
        spam = User.objects.create_user(
            username="spam@example.com",
            email="spam@example.com",
            first_name="Claim Your Bonus jolpo.kesug.com",
            last_name="Access Reward riooep.wuaze.com",
        )
        legit = User.objects.create_user(
            username="ok@example.com",
            email="ok@example.com",
            first_name="Alex",
            last_name="Garcia",
        )
        out = StringIO()
        call_command("purge_spam_name_users", stdout=out)
        self.assertIn(spam.email, out.getvalue())
        self.assertIn("Dry run", out.getvalue())
        self.assertTrue(User.objects.filter(id=spam.id).exists())
        self.assertTrue(User.objects.filter(id=legit.id).exists())

    def test_delete_removes_unprotected_spam_users(self):
        spam = User.objects.create_user(
            username="spam@example.com",
            email="spam@example.com",
            first_name="Claim Your Bonus jolpo.kesug.com",
            last_name="User",
        )
        staff = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            first_name="Staff",
            last_name="Person.com",
            is_staff=True,
        )
        author_user = User.objects.create_user(
            username="author@example.com",
            email="author@example.com",
            first_name="Writer",
            last_name="Blog.com",
        )
        Author.objects.create(user=author_user, name="Writer")
        subscriber = User.objects.create_user(
            username="sub@example.com",
            email="sub@example.com",
            first_name="Paid",
            last_name="Member.com",
        )
        Subscription.objects.create(user=subscriber, status="active")

        self.assertEqual(user_is_protected(staff), "staff")
        self.assertEqual(user_is_protected(author_user), "author")
        self.assertEqual(user_is_protected(subscriber), "active_subscription")
        self.assertIsNone(user_is_protected(spam))

        out = StringIO()
        call_command("purge_spam_name_users", "--delete", stdout=out)
        self.assertFalse(User.objects.filter(id=spam.id).exists())
        self.assertTrue(User.objects.filter(id=staff.id).exists())
        self.assertTrue(User.objects.filter(id=author_user.id).exists())
        self.assertTrue(User.objects.filter(id=subscriber.id).exists())
        self.assertIn("skip=staff", out.getvalue())


class SignupRejectsDomainInNameTestCase(TestCase):
    @patch("overslot.auth.MailgunEmailer.send_email")
    def test_legitimate_period_in_name_still_signs_up(self, mock_send_email):
        mock_send_email.return_value = Mock(status_code=200)
        response = self.client.post(reverse("magic_link_signup"), {
            "csrfmiddlewaretoken": "test",
            "email": "jr@example.com",
            "first_name": "J.R.",
            "last_name": "Morgan",
        })
        self.assertEqual(response.status_code, 302)
        mock_send_email.assert_called_once()
        self.assertTrue(User.objects.filter(email="jr@example.com").exists())
