from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
from unittest.mock import patch, Mock
from overslot.models import Player, Ranking, PlayerRanking, Article, Author
from sesame.utils import get_token


class AuthenticationIntegrationTestCase(TestCase):
    """Integration tests for the complete authentication flow"""
    
    def setUp(self):
        self.client = Client()
        self.test_email = "integration@example.com"
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_complete_signup_flow(self, mock_send_email):
        """Test complete user signup flow from start to finish"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Step 1: User visits signup page
        response = self.client.get(reverse('account_signup'))
        self.assertEqual(response.status_code, 200)
        
        # Step 2: User submits signup form
        response = self.client.post(reverse('magic_link_signup'), {
            'email': self.test_email,
            'first_name': 'Integration',
            'last_name': 'Test'
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 3: Verify user was created
        user = User.objects.get(email=self.test_email)
        self.assertEqual(user.first_name, 'Integration')
        self.assertEqual(user.last_name, 'Test')
        
        # Step 4: Simulate clicking magic link
        token = get_token(user)
        response = self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
        self.assertEqual(response.status_code, 302)
        
        # Step 5: Verify user is logged in and redirected to home
        self.assertTrue(self.client.session.get('_auth_user_id'))
        self.assertTrue(response.url.endswith(reverse('index')))
        
        # Step 6: Verify user can access authenticated pages
        response = self.client.get(reverse('index'))
        self.assertContains(response, self.test_email)
    
    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_complete_login_flow(self, mock_send_email):
        """Test complete user login flow for existing user"""
        mock_send_email.return_value = Mock(status_code=200)
        
        # Create existing user
        user = User.objects.create_user(
            username=self.test_email,
            email=self.test_email,
            first_name='Existing',
            last_name='User'
        )
        
        # Step 1: User visits login page
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        
        # Step 2: User requests magic link
        response = self.client.post(reverse('magic_link'), {
            'email': self.test_email
        })
        self.assertEqual(response.status_code, 302)
        
        # Step 3: User clicks magic link
        token = get_token(user)
        response = self.client.get(reverse('magic_link_verify', kwargs={'token': token}))
        self.assertEqual(response.status_code, 302)
        
        # Step 4: Verify user is logged in
        self.assertTrue(self.client.session.get('_auth_user_id'))
        
        # Step 5: User can access account features
        response = self.client.get(reverse('index'))
        self.assertContains(response, self.test_email)

    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_spammy_login_with_url_is_silently_ignored(self, mock_send_email):
        mock_send_email.return_value = Mock(status_code=200)
        response = self.client.post(reverse('magic_link'), {
            'email': 'http://spam.example.com@domain.com'
        })
        self.assertEqual(response.status_code, 302)
        # No email should be sent
        mock_send_email.assert_not_called()

    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_spammy_signup_with_url_in_name_is_silently_ignored(self, mock_send_email):
        mock_send_email.return_value = Mock(status_code=200)
        response = self.client.post(reverse('magic_link_signup'), {
            'email': 'valid@example.com',
            'first_name': 'http://bad',
            'last_name': 'User'
        })
        self.assertEqual(response.status_code, 302)
        mock_send_email.assert_not_called()

    @patch('overslot.auth.MailgunEmailer.send_email')
    def test_spammy_signup_with_very_long_name_is_silently_ignored(self, mock_send_email):
        mock_send_email.return_value = Mock(status_code=200)
        long_name = 'A' * 200
        response = self.client.post(reverse('magic_link_signup'), {
            'email': 'valid@example.com',
            'first_name': long_name,
            'last_name': 'User'
        })
        self.assertEqual(response.status_code, 302)
        mock_send_email.assert_not_called()


class ContentDiscoveryIntegrationTestCase(TestCase):
    """Integration tests for content discovery and navigation"""
    
    def setUp(self):
        self.client = Client()
        
        # Create staff user
        self.staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            is_staff=True
        )
        
        # Create comprehensive test data
        self.author = Author.objects.create(
            name="Test Author",
            email="author@example.com",
            bio="Test author bio"
        )
        
        self.player1 = Player.objects.create(
            name="John Doe",
            position="SS",
            school="University of Baseball",
            country="USA",
            slug="john-doe"
        )
        
        self.player2 = Player.objects.create(
            name="Jane Smith",
            position="CF",
            school="Baseball College",
            country="USA",
            slug="jane-smith"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            ranking_length="50",
            headline="Top College Prospects 2024",
            subhead="Best college players in the draft",
            slug="top-college-prospects-2024"
        )
        
        # Create player rankings
        PlayerRanking.objects.create(
            player=self.player1,
            ranking=self.ranking,
            rank=1,
            position="SS",
            school="University of Baseball",
            scouting_report="<p>Excellent prospect with great tools</p>"
        )
        
        PlayerRanking.objects.create(
            player=self.player2,
            ranking=self.ranking,
            rank=2,
            position="CF",
            school="Baseball College",
            scouting_report="<p>Fast player with good instincts</p>"
        )
        
        # Create articles
        self.article1 = Article.objects.create(
            headline="John Doe Scouting Report",
            subhead="Breaking down the top prospect",
            blurb="Detailed analysis of John Doe",
            body="<p>John Doe is an exceptional prospect...</p>",
            publish=True,
            slug="john-doe-scouting-report"
        )
        self.article1.authors.add(self.author)
        self.article1.players.add(self.player1)
        
        self.article2 = Article.objects.create(
            headline="2024 Draft Analysis",
            subhead="Complete breakdown",
            blurb="Analysis of the 2024 draft class",
            body="<p>The 2024 draft class features...</p>",
            publish=True,
            slug="2024-draft-analysis"
        )
        self.article2.authors.add(self.author)
        self.article2.players.add(self.player1, self.player2)
    
    def test_content_discovery_workflow(self):
        """Test complete content discovery workflow"""
        self.client.login(username='staff@example.com', password='testpass123')
        
        # Step 1: User visits homepage
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article1.headline)
        self.assertContains(response, self.ranking.headline)
        
        # Step 2: User clicks on an article
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article1.headline)
        self.assertContains(response, self.player1.name)
        
        # Step 3: User clicks on a player tag in the article
        response = self.client.get(reverse('players_detail', kwargs={'slug': self.player1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.player1.name)
        self.assertContains(response, self.player1.school)
        
        # Verify related content appears
        self.assertContains(response, self.ranking.headline)  # Player appears in this ranking
        self.assertContains(response, self.article1.headline)  # Article mentions this player
        
        # Step 4: User clicks on a ranking from player page
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ranking.headline)
        self.assertContains(response, self.player1.name)
        self.assertContains(response, self.player2.name)
        
        # Step 5: User explores all rankings
        response = self.client.get(reverse('rankings_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ranking.headline)
        
        # Step 6: User explores all articles
        response = self.client.get(reverse('articles_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article1.headline)
        self.assertContains(response, self.article2.headline)
    
    def test_search_integration_workflow(self):
        """Test search functionality integration"""
        # Search for player name
        response = self.client.get(reverse('search'), {'q': 'John Doe'})
        self.assertEqual(response.status_code, 200)
        
        import json
        data = json.loads(response.content)
        
        # Should find player
        self.assertEqual(len(data['players']), 1)
        self.assertEqual(data['players'][0]['name'], 'John Doe')
        
        # Should find related article
        self.assertEqual(len(data['articles']), 1)
        self.assertEqual(data['articles'][0]['headline'], 'John Doe Scouting Report')
        
        # Should find ranking containing player
        self.assertEqual(len(data['rankings']), 1)
        self.assertEqual(data['rankings'][0]['slug'], 'top-college-prospects-2024')
        
        # Search for school
        response = self.client.get(reverse('search'), {'q': 'University of Baseball'})
        data = json.loads(response.content)
        
        # Should find player by school
        self.assertEqual(len(data['players']), 1)
        self.assertEqual(data['players'][0]['school'], 'University of Baseball')
    
    def test_subscription_workflow(self):
        """Test subscription access workflow"""
        # Create regular user (non-staff)
        regular_user = User.objects.create_user(
            username='regular@example.com',
            email='regular@example.com'
        )
        
        # Step 1: Anonymous user sees limited content
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'preview')
        
        # Step 2: Regular authenticated user still sees limited content
        self.client.login(username='regular@example.com', password='testpass123')
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'preview')
        
        # Step 3: Staff user sees full content
        self.client.login(username='staff@example.com', password='testpass123')
        response = self.client.get(reverse('articles_detail', kwargs={'slug': self.article1.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article1.body)


class DataIntegrityIntegrationTestCase(TestCase):
    """Integration tests for data integrity and relationships"""
    
    def setUp(self):
        self.client = Client()
        
        self.author = Author.objects.create(
            name="Data Author",
            email="data@example.com"
        )
        
        self.player = Player.objects.create(
            name="Data Player",
            position="1B",
            school="Data University",
            slug="data-player"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            headline="Data Ranking",
            slug="data-ranking"
        )
    
    def test_content_relationships_maintained(self):
        """Test that content relationships are maintained across operations"""
        # Create interconnected content
        player_ranking = PlayerRanking.objects.create(
            player=self.player,
            ranking=self.ranking,
            rank=5,
            position="1B",
            school="Data University"
        )
        
        article = Article.objects.create(
            headline="Data Article",
            body="<p>Article about data player</p>",
            publish=True,
            slug="data-article"
        )
        article.authors.add(self.author)
        article.players.add(self.player)
        
        # Test that relationships are maintained in views
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            is_staff=True
        )
        self.client.login(username='staff@example.com', password='testpass123')
        
        # Player page should show related ranking and article
        response = self.client.get(reverse('players_detail', kwargs={'slug': self.player.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ranking.headline)
        self.assertContains(response, article.headline)
        
        # Article page should show related player
        response = self.client.get(reverse('articles_detail', kwargs={'slug': article.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.player.name)
        
        # Ranking page should show related player
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.player.name)
    
    def test_slug_uniqueness_and_generation(self):
        """Test that slug generation works correctly and handles duplicates"""
        # Create players with similar names
        player1 = Player.objects.create(
            name="Test Player",
            position="SS"
        )
        player1.save()
        
        player2 = Player.objects.create(
            name="Test Player",
            position="CF"
        )
        player2.save()
        
        # Slugs should be different
        self.assertNotEqual(player1.slug, player2.slug)
        self.assertTrue(player1.slug)
        self.assertTrue(player2.slug)
        
        # Both should be accessible via their slugs
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            is_staff=True
        )
        self.client.login(username='staff@example.com', password='testpass123')
        
        response1 = self.client.get(reverse('players_detail', kwargs={'slug': player1.slug}))
        self.assertEqual(response1.status_code, 200)
        
        response2 = self.client.get(reverse('players_detail', kwargs={'slug': player2.slug}))
        self.assertEqual(response2.status_code, 200)


class PerformanceIntegrationTestCase(TestCase):
    """Integration tests for performance-related concerns"""
    
    def setUp(self):
        self.client = Client()
        
        # Create a large dataset to test performance
        self.author = Author.objects.create(
            name="Performance Author",
            email="perf@example.com"
        )
        
        self.ranking = Ranking.objects.create(
            year="2024",
            ranking_type="College",
            ranking_length="100",
            headline="Large Ranking",
            slug="large-ranking"
        )
        
        # Create many players and rankings
        self.players = []
        for i in range(20):  # Reduced for test performance
            player = Player.objects.create(
                name=f"Player {i}",
                position="SS",
                school=f"University {i}",
                slug=f"player-{i}"
            )
            self.players.append(player)
            
            PlayerRanking.objects.create(
                player=player,
                ranking=self.ranking,
                rank=i + 1,
                position="SS",
                school=f"University {i}"
            )
        
        # Create articles
        for i in range(5):
            article = Article.objects.create(
                headline=f"Article {i}",
                body=f"<p>Content for article {i}</p>",
                publish=True,
                slug=f"article-{i}"
            )
            article.authors.add(self.author)
            # Add multiple players to each article
            for j in range(min(3, len(self.players))):
                article.players.add(self.players[j])
    
    def test_ranking_page_performance(self):
        """Test that ranking pages load efficiently with many players"""
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            is_staff=True
        )
        self.client.login(username='staff@example.com', password='testpass123')
        
        response = self.client.get(reverse('rankings_detail', kwargs={'slug': self.ranking.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ranking.headline)
        
        # Should contain all players
        for i in range(10):  # Check first 10
            self.assertContains(response, f"Player {i}")
    
    def test_search_performance_with_large_dataset(self):
        """Test search performance with larger dataset"""
        response = self.client.get(reverse('search'), {'q': 'Player'})
        self.assertEqual(response.status_code, 200)
        
        import json
        data = json.loads(response.content)
        
        # Should return results (limited to 5 each)
        self.assertLessEqual(len(data['players']), 5)
        self.assertLessEqual(len(data['articles']), 5)
        self.assertLessEqual(len(data['rankings']), 5)
    
    def test_article_with_many_players(self):
        """Test article pages with many related players"""
        staff_user = User.objects.create_user(
            username='staff@example.com',
            email='staff@example.com',
            is_staff=True
        )
        self.client.login(username='staff@example.com', password='testpass123')
        
        response = self.client.get(reverse('articles_detail', kwargs={'slug': 'article-0'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Article 0")
        
        # Should show related players
        for i in range(3):
            self.assertContains(response, f"Player {i}") 