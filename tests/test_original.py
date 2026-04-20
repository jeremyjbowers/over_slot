import json
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from django.conf import settings
from sesame.utils import get_token
from overslot import models, auth
from overslot.models import Player, Ranking, PlayerRanking, Article, Author


class AuthenticationTestCase(TestCase):
    """Test the magic link authentication system"""
    
    def setUp(self):
        self.client = Client()
        self.user_email = "test@example.com"
        self.user = User.objects.create_user(
            username=self.user_email,
            email=self.user_email,
            first_name="Test",
            last_name="User"
        )
    
    def test_magic_link_login_view_get_redirects(self):
        """GET request to magic link view should redirect to login"""
        response = self.client.get(reverse('magic_link'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_magic_link_login_existing_user(self, mock_send_email):
        """Magic link login should work for existing users"""
        mock_send_email.return_value = Mock(status_code=200)
        
        response = self.client.post(reverse('magic_link'), {
            'email': self.user_email
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        mock_send_email.assert_called_once()
        
        # Check that email was called with correct parameters
        call_args = mock_send_email.call_args
        self.assertEqual(call_args[0][0], self.user_email)  # to_email
        self.assertIn("Sign in to Over Slot", call_args[0][1])  # subject
    
    def test_magic_link_login_nonexistent_user(self):
        """Magic link login should fail for non-existent users"""
        response = self.client.post(reverse('magic_link'), {
            'email': 'nonexistent@example.com'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_signup')))
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_magic_link_signup_new_user(self, mock_send_email):
        """Magic link signup should create new user account"""
        mock_send_email.return_value = Mock(status_code=200)
        new_email = 'newuser@example.com'
        
        response = self.client.post(reverse('magic_link_signup'), {
            'email': new_email,
            'first_name': 'New',
            'last_name': 'User'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Check that user was created
        self.assertTrue(User.objects.filter(email=new_email).exists())
        new_user = User.objects.get(email=new_email)
        self.assertEqual(new_user.first_name, 'New')
        self.assertEqual(new_user.last_name, 'User')
        
        mock_send_email.assert_called_once()
    
    def test_magic_link_signup_existing_user(self):
        """Magic link signup should fail for existing users"""
        response = self.client.post(reverse('magic_link_signup'), {
            'email': self.user_email,
            'first_name': 'Test',
            'last_name': 'User'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
    
    def test_magic_link_verify_valid_token(self):
        """Valid magic link token should log user in"""
        token = get_token(self.user)
        
        response = self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('index')))
        
        # Check user is logged in
        self.assertTrue(self.client.session.get('_auth_user_id'))
    
    def test_magic_link_verify_invalid_token(self):
        """Invalid magic link token should redirect to login with error"""
        invalid_token = "invalid_token_string"
        
        response = self.client.get(reverse('magic_link_verify', kwargs={'token': invalid_token}))
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('account_login')))
        
        # Check user is not logged in
        self.assertFalse(self.client.session.get('_auth_user_id'))


class ViewsTestCase(TestCase):
    """Test the main views and URL patterns"""
    
    def setUp(self):
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123'
        )
        
        # Create staff user for subscription testing
        self.staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True
        )
        
        # Create test data
        self.author = Author.objects.create(
            name="Test Author",
            email="author@example.com"
        )
        
        self.player = Player.objects.create(
            name="Test Player",
            position="SS",
            school="Test University",
            slug="test-player"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            ranking_length="100",
            headline="Test Ranking",
            slug="test-ranking-2024",
            publish=True
        )
        
        self.player_ranking = PlayerRanking.objects.create(
            player=self.player,
            ranking=self.ranking,
            rank=1,
            position="SS",
            school="Test University"
        )
        
        self.article = Article.objects.create(
            headline="Test Article",
            subhead="Test Subhead",
            blurb="Test blurb content",
            body="<p>Test article body content</p>",
            publish=True,
            slug="test-article"
        )
        self.article.authors.add(self.author)
        self.article.players.add(self.player)
    
    def test_index_view_renders(self):
        """Index page should render successfully"""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Over Slot")
        self.assertContains(response, self.article.headline)
        self.assertContains(response, str(self.ranking))
    
    def test_articles_list_view_renders(self):
        """Articles list page should render successfully"""
        response = self.client.get(reverse('articles_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.headline)
        self.assertContains(response, self.article.subhead)
    
    def test_articles_detail_view_requires_subscription(self):
        """Article detail should require subscription for non-staff users"""
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article.slug}))
        self.assertEqual(response.status_code, 200)
        # Should render preview template
        self.assertContains(response, "preview")
    
    def test_articles_detail_view_staff_access(self):
        """Staff users should have full access to article details"""
        self.client.login(username='staff@example.com', password='staffpass123')
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.headline)
    
    def test_articles_detail_view_404(self):
        """Article detail should return 404 for non-existent articles"""
        response = self.client.get(reverse('articles_detail', kwargs={'slug': 'nonexistent-article'}))
        self.assertEqual(response.status_code, 404)
    
    def test_rankings_list_view_renders(self):
        """Rankings list page should render successfully"""
        response = self.client.get(reverse('rankings_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.ranking))
    
    def test_rankings_detail_view_requires_subscription(self):
        """Ranking detail should require subscription for non-staff users"""
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        # Should render preview template
        self.assertContains(response, "preview")
    
    def test_rankings_detail_view_staff_access(self):
        """Staff users should have full access to ranking details"""
        self.client.login(username='staff@example.com', password='staffpass123')
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ranking.headline)

    def test_rankings_detail_view_free_skips_preview(self):
        """Free rankings show full content to anonymous users (no subscription preview)."""
        self.ranking.is_free = True
        self.ranking.save()
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Preview: Top")

    def test_mock_drafts_detail_view_free_skips_preview(self):
        """Free mock drafts show full content without subscription."""
        mock = Ranking.objects.create(
            year="2026",
            is_mock_draft=True,
            mock_draft_version="1.0",
            is_draft=True,
            publish=True,
            is_free=True,
            slug="test-mock-2026-1",
        )
        PlayerRanking.objects.create(
            player=self.player,
            ranking=mock,
            rank=1,
            position="SS",
            school="Test University",
        )
        response = self.client.get(reverse('mock_drafts_detail', kwargs={'slug': mock.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Preview: Top")
    
    def test_rankings_detail_view_404(self):
        """Ranking detail should return 404 for non-existent rankings"""
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': 'nonexistent-ranking'}))
        self.assertEqual(response.status_code, 404)
    
    def test_players_detail_view_requires_subscription(self):
        """Player detail should require subscription for non-staff users"""
        response = self.client.get(reverse('players_detail', kwargs={'slug': self.player.slug}))
        self.assertEqual(response.status_code, 200)
        # Should render preview template
        self.assertContains(response, "preview")
    
    def test_players_detail_view_staff_access(self):
        """Staff users should have full access to player details"""
        self.client.login(username='staff@example.com', password='staffpass123')
        response = self.client.get(reverse('players_detail', kwargs={'slug': self.player.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.player.name)
    
    def test_players_detail_view_404(self):
        """Player detail should return 404 for non-existent players"""
        response = self.client.get(reverse('players_detail', kwargs={'slug': 'nonexistent-player'}))
        self.assertEqual(response.status_code, 404)


class SearchTestCase(TestCase):
    """Test the search functionality"""
    
    def setUp(self):
        self.client = Client()
        
        # Create test data
        self.author = Author.objects.create(
            name="Test Author",
            email="author@example.com"
        )
        
        self.player = Player.objects.create(
            name="Mike Trout",
            position="CF",
            school="East Carolina",
            slug="mike-trout"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            ranking_length="100",
            headline="Top Prospects",
            slug="top-prospects-2024",
            publish=True
        )
        
        PlayerRanking.objects.create(
            player=self.player,
            ranking=self.ranking,
            rank=1,
            position="CF",
            school="East Carolina"
        )
        
        self.article = Article.objects.create(
            headline="Trout Analysis",
            subhead="Breaking down the superstar",
            blurb="Analysis of Mike Trout",
            body="<p>Mike Trout is amazing</p>",
            publish=True,
            slug="trout-analysis"
        )
        self.article.authors.add(self.author)
        self.article.players.add(self.player)
    
    def test_search_returns_json(self):
        """Search endpoint should return JSON response"""
        response = self.client.get(reverse('search'), {'q': 'Trout'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
    
    def test_search_finds_articles(self):
        """Search should find articles by headline, subhead, blurb, and body"""
        response = self.client.get(reverse('search'), {'q': 'Trout'})
        data = json.loads(response.content)
        
        self.assertEqual(len(data['articles']), 1)
        self.assertEqual(data['articles'][0]['headline'], 'Trout Analysis')
        self.assertEqual(data['articles'][0]['slug'], 'trout-analysis')
    
    def test_search_finds_players(self):
        """Search should find players by name, position, and school"""
        response = self.client.get(reverse('search'), {'q': 'Trout'})
        data = json.loads(response.content)
        
        self.assertEqual(len(data['players']), 1)
        self.assertEqual(data['players'][0]['name'], 'Mike Trout')
        self.assertEqual(data['players'][0]['slug'], 'mike-trout')
        self.assertEqual(data['players'][0]['position'], 'CF')
        self.assertEqual(data['players'][0]['school'], 'East Carolina')
    
    def test_search_finds_rankings_by_players(self):
        """Search should find rankings that contain matching players"""
        response = self.client.get(reverse('search'), {'q': 'Trout'})
        data = json.loads(response.content)
        
        self.assertEqual(len(data['rankings']), 1)
        self.assertEqual(data['rankings'][0]['slug'], 'top-prospects-2024')
        self.assertEqual(data['rankings'][0]['preview'], 'Mike Trout')
    
    def test_search_short_query(self):
        """Search with query less than 2 characters should return empty results"""
        response = self.client.get(reverse('search'), {'q': 'T'})
        data = json.loads(response.content)
        
        self.assertEqual(len(data['articles']), 0)
        self.assertEqual(len(data['players']), 0)
        self.assertEqual(len(data['rankings']), 0)
    
    def test_search_no_query(self):
        """Search without query should return empty results"""
        response = self.client.get(reverse('search'))
        data = json.loads(response.content)
        
        self.assertEqual(len(data['articles']), 0)
        self.assertEqual(len(data['players']), 0)
        self.assertEqual(len(data['rankings']), 0)
    
    def test_search_unpublished_articles(self):
        """Search should not return unpublished articles"""
        unpublished_article = Article.objects.create(
            headline="Unpublished Trout Article",
            body="<p>This should not appear</p>",
            publish=False,
            slug="unpublished-trout"
        )
        
        response = self.client.get(reverse('search'), {'q': 'Unpublished'})
        data = json.loads(response.content)
        
        self.assertEqual(len(data['articles']), 0)


class TemplateRenderingTestCase(TestCase):
    """Test that templates render without errors"""
    
    def setUp(self):
        self.client = Client()
        
        # Create minimal test data
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            is_staff=True
        )
        
        self.author = Author.objects.create(
            name="Test Author",
            email="author@example.com"
        )
        
        self.player = Player.objects.create(
            name="Test Player",
            position="SS",
            school="Test University",
            slug="test-player"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            headline="Test Ranking",
            slug="test-ranking",
            publish=True
        )
        
        self.article = Article.objects.create(
            headline="Test Article",
            body="<p>Test content</p>",
            publish=True,
            slug="test-article"
        )
    
    def test_all_main_templates_render(self):
        """Test that all main templates render without errors"""
        self.client.login(username='testuser@example.com', password='testpass123')
        
        urls_to_test = [
            ('index', {}),
            ('articles_list', {}),
            ('articles_detail', {'slug': self.article.slug}),
            ('rankings_list', {}),
            ('rankings_detail', {'slug': self.ranking.slug}),
            ('players_detail', {'slug': self.player.slug}),
        ]
        
        for url_name, kwargs in urls_to_test:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                self.assertIn(response.status_code, [200, 302])  # 302 for redirects is OK
                if response.status_code == 200:
                    # Check that the response contains HTML
                    self.assertContains(response, '<html', msg_prefix=f"Template {url_name} doesn't contain HTML")
    
    def test_error_pages_render(self):
        """Test that error pages render correctly"""
        # Test 404 pages
        response = self.client.get('/nonexistent-page/')
        self.assertEqual(response.status_code, 404)
        
        response = self.client.get(reverse('articles_detail', kwargs={'slug': 'nonexistent'}))
        self.assertEqual(response.status_code, 404)
    
    def test_navigation_elements_present(self):
        """Test that navigation elements are present on pages"""
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        
        # Check for navigation elements
        self.assertContains(response, 'navbar')
        self.assertContains(response, 'Sign in')
        self.assertContains(response, 'Get started')
    
    def test_authenticated_navigation(self):
        """Test navigation for authenticated users"""
        self.client.login(username='testuser@example.com', password='testpass123')
        response = self.client.get(reverse('index'))
        
        self.assertContains(response, 'testuser@example.com')
        self.assertContains(response, 'Sign out')


class ModelTestCase(TestCase):
    """Test model functionality that affects the UI"""
    
    def setUp(self):
        self.author = Author.objects.create(
            name="Test Author",
            email="author@example.com"
        )
        
        self.player = Player.objects.create(
            name="Test Player",
            position="SS",
            school="Test University"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            ranking_length="100"
        )
    
    def test_player_slug_generation(self):
        """Test that player slugs are generated correctly"""
        player = Player.objects.create(
            name="Mike Trout Jr.",
            position="CF"
        )
        player.save()
        self.assertTrue(player.slug)
        self.assertIn('mike-trout-jr', player.slug)
    
    def test_ranking_string_representation(self):
        """Test ranking string representation for UI display"""
        ranking_str = str(self.ranking)
        self.assertIn("2024", ranking_str)
        self.assertIn("Top 100", ranking_str)
        self.assertIn("College", ranking_str)
    
    def test_article_player_relationships(self):
        """Test article-player many-to-many relationships"""
        article = Article.objects.create(
            headline="Test Article",
            body="<p>Test content</p>",
            publish=True
        )
        article.players.add(self.player)
        
        self.assertEqual(article.players.count(), 1)
        self.assertEqual(article.players.first(), self.player)
    
    def test_player_ranking_relationships(self):
        """Test player ranking relationships"""
        player_ranking = PlayerRanking.objects.create(
            player=self.player,
            ranking=self.ranking,
            rank=1,
            position="SS"
        )
        
        self.assertEqual(self.ranking.get_playerrankings().count(), 1)
        self.assertEqual(self.ranking.get_playerrankings().first(), player_ranking)
        self.assertEqual(self.ranking.get_initial_players().count(), 1)


class URLPatternTestCase(TestCase):
    """Test URL patterns resolve correctly"""
    
    def test_main_url_patterns_resolve(self):
        """Test that main URL patterns resolve without errors"""
        url_patterns = [
            'index',
            'articles_list',
            'rankings_list',
            'search',
            'magic_link',
            'magic_link_signup',
        ]
        
        for pattern in url_patterns:
            with self.subTest(pattern=pattern):
                url = reverse(pattern)
                self.assertTrue(url.startswith('/'))
    
    def test_detail_url_patterns_resolve(self):
        """Test that detail URL patterns resolve with slugs"""
        detail_patterns = [
            ('articles_detail', 'test-slug'),
            ('rankings_detail', 'test-slug'),
            ('players_detail', 'test-slug'),
            ('magic_link_verify', 'test-token'),
        ]
        
        for pattern, slug in detail_patterns:
            with self.subTest(pattern=pattern):
                url = reverse(pattern, kwargs={'slug': slug} if 'token' not in pattern else {'token': slug})
                self.assertTrue(url.startswith('/'))
                self.assertIn(slug, url)


class SecurityTestCase(TestCase):
    """Test security-related functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com'
        )
    
    def test_subscription_decorator_blocks_non_staff(self):
        """Test that subscription decorator blocks non-staff users"""
        article = Article.objects.create(
            headline="Test Article",
            body="<p>Test content</p>",
            publish=True,
            slug="test-article"
        )
        
        # Non-authenticated user should get preview
        response = self.client.get(reverse('articles_detail', kwargs={'slug': article.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'preview')
        
        # Regular authenticated user should get preview
        self.client.login(username='testuser@example.com', password='testpass123')
        response = self.client.get(reverse('articles_detail', kwargs={'slug': article.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'preview')
    
    def test_csrf_protection_on_forms(self):
        """Test that CSRF protection is enabled on forms"""
        # Magic link form should require CSRF token
        response = self.client.post(reverse('magic_link'), {
            'email': 'test@example.com'
        })
        # Should fail due to missing CSRF token
        self.assertEqual(response.status_code, 403)
    
    def test_search_xss_protection(self):
        """Test that search is protected against XSS"""
        malicious_query = '<script>alert("xss")</script>'
        response = self.client.get(reverse('search'), {'q': malicious_query})
        
        # Should return JSON, not execute script
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = json.loads(response.content)
        self.assertEqual(len(data['articles']), 0)
        self.assertEqual(len(data['players']), 0)
        self.assertEqual(len(data['rankings']), 0) 