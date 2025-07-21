import time
import json
import statistics
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from overslot import models

User = get_user_model()

class Command(BaseCommand):
    help = 'Test frontend performance of rankings detail page'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ranking-slug',
            type=str,
            help='Test specific ranking by slug (optional)',
        )
        parser.add_argument(
            '--players',
            type=int,
            default=30,
            help='Number of test players to create (default: 30)',
        )
        parser.add_argument(
            '--runs',
            type=int,
            default=3,
            help='Number of test runs to average (default: 3)',
        )
        parser.add_argument(
            '--no-browser',
            action='store_true',
            help='Skip browser tests, only run server tests',
        )
        parser.add_argument(
            '--headless',
            action='store_true',
            default=True,
            help='Run browser tests in headless mode (default: True)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Rankings Detail Performance Tests')
        )
        
        # Setup test data
        ranking_slug = options.get('ranking_slug')
        ranking_slug = "2026-draft-top-200-41f2cc5d-13a7-4c6e-9604-a65261bc09ae"
        if ranking_slug:
            try:
                ranking = models.Ranking.objects.get(slug=ranking_slug, publish=True)
                self.stdout.write(f"Testing existing ranking: {ranking}")
            except models.Ranking.DoesNotExist:
                raise CommandError(f"Ranking with slug '{ranking_slug}' not found")
        else:
            ranking = self.create_test_ranking(options['players'])
            self.stdout.write(f"Created test ranking with {options['players']} players")

        # Run server performance tests
        self.stdout.write("\n" + "="*50)
        self.stdout.write("📊 SERVER PERFORMANCE TESTS")
        self.stdout.write("="*50)
        
        server_results = self.test_server_performance(ranking, options['runs'])
        self.display_server_results(server_results)

        # Run browser performance tests (if not disabled)
        if not options['no_browser']:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("🌐 BROWSER PERFORMANCE TESTS")
            self.stdout.write("="*50)
            
            try:
                browser_results = self.test_browser_performance(
                    ranking, 
                    options['runs'], 
                    options['headless']
                )
                self.display_browser_results(browser_results)
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Browser tests failed: {e}")
                )
                self.stdout.write(
                    self.style.WARNING("Run with --no-browser to skip browser tests")
                )

        # Overall performance score
        self.display_performance_score(server_results)

        # Cleanup test data (if we created it)
        if not ranking_slug:
            self.cleanup_test_data(ranking)

        self.stdout.write(
            self.style.SUCCESS('\n✅ Performance testing complete!')
        )

    def create_test_ranking(self, num_players):
        """Create test ranking with specified number of players."""
        ranking = models.Ranking.objects.create(
            name=f"Performance Test Ranking ({num_players} players)",
            slug=f"perf-test-{int(time.time())}",
            year=2024,
            publish=True
        )

        self.stdout.write(f"Creating {num_players} test players...")
        
        for i in range(num_players):
            player = models.Player.objects.create(
                name=f"Test Player {i+1:03d}",
                slug=f"test-player-{ranking.id}-{i+1:03d}",
                position=["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF"][i % 10],
                school=f"Test University {(i % 20) + 1}",
                height=f"{5 + (i % 3)}'{6 + (i % 6)}\"",
                weight=160 + (i % 80),
                bats=["R", "L", "S"][i % 3],
                throws=["R", "L"][i % 2],
                active=True
            )

            # Create scouting report of varying lengths
            report_length = 1 + (i % 5)  # 1-5 paragraphs
            scouting_report = ""
            for j in range(report_length):
                scouting_report += f"<p>Analysis paragraph {j+1} for {player.name}. Shows promise in multiple areas.</p>"

            models.PlayerRanking.objects.create(
                player=player,
                ranking=ranking,
                rank=i + 1,
                position=player.position,
                school=player.school,
                scouting_report=scouting_report,
                role=["Future Value", "Role Player", "Utility", "Specialist"][i % 4],
                risk=["Safe", "Moderate", "High"][i % 3]
            )

        return ranking

    def test_server_performance(self, ranking, runs):
        """Test server-side performance metrics."""
        client = Client()
        url = reverse('rankings_detail', kwargs={'slug': ranking.slug})
        
        results = []
        
        for run in range(runs):
            self.stdout.write(f"  📡 Server test run {run + 1}/{runs}...")
            
            # Measure response time
            start_time = time.time()
            response = client.get(url)
            response_time = time.time() - start_time
            
            # Analyze response
            html_size = len(response.content)
            html_content = response.content.decode('utf-8', errors='ignore')
            
            # Count various elements
            dom_elements = html_content.count('<')
            player_cards = html_content.count('class="player-card"')
            
            results.append({
                'response_time': response_time,
                'html_size': html_size,
                'dom_elements': dom_elements,
                'player_cards': player_cards,
                'status_code': response.status_code
            })
            
            time.sleep(0.5)  # Brief pause between tests
        
        # Calculate averages
        avg_results = {
            'avg_response_time': statistics.mean([r['response_time'] for r in results]),
            'max_response_time': max([r['response_time'] for r in results]),
            'avg_html_size': statistics.mean([r['html_size'] for r in results]),
            'avg_dom_elements': statistics.mean([r['dom_elements'] for r in results]),
            'player_cards': results[0]['player_cards'],
            'runs': len(results)
        }
        
        return avg_results

    def test_browser_performance(self, ranking, runs, headless):
        """Test browser-side performance metrics."""
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        results = []
        
        for run in range(runs):
            self.stdout.write(f"  🌐 Browser test run {run + 1}/{runs}...")
            
            driver = None
            try:
                driver = webdriver.Chrome(options=chrome_options)
                
                url = f"http://localhost:8000{reverse('rankings_detail', kwargs={'slug': ranking.slug})}"
                
                # Measure page load
                start_time = time.time()
                driver.get(url)
                
                # Wait for DOM ready
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                load_time = time.time() - start_time
                
                # Get performance metrics
                metrics = driver.execute_script("""
                    return {
                        dom_elements: document.querySelectorAll('*').length,
                        images: document.images.length,
                        scripts: document.scripts.length,
                        memory_used: performance.memory ? performance.memory.usedJSHeapSize : null,
                        player_cards: document.querySelectorAll('.player-card').length
                    };
                """)
                
                results.append({
                    'load_time': load_time,
                    **metrics
                })
                
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"    ⚠️  Browser test run {run + 1} failed: {e}")
                )
                
            finally:
                if driver:
                    driver.quit()
            
            time.sleep(1)  # Pause between runs
        
        if not results:
            raise Exception("All browser test runs failed")
        
        # Calculate averages
        avg_results = {
            'avg_load_time': statistics.mean([r['load_time'] for r in results]),
            'max_load_time': max([r['load_time'] for r in results]),
            'avg_dom_elements': statistics.mean([r['dom_elements'] for r in results]),
            'avg_memory_used': statistics.mean([r['memory_used'] for r in results if r['memory_used']]),
            'player_cards': results[0]['player_cards'],
            'successful_runs': len(results)
        }
        
        return avg_results

    def display_server_results(self, results):
        """Display server performance results."""
        self.stdout.write("\n📈 Server Performance Results:")
        self.stdout.write(f"  Response Time: {results['avg_response_time']:.3f}s (max: {results['max_response_time']:.3f}s)")
        self.stdout.write(f"  HTML Size: {results['avg_html_size']/1024:.1f}KB")
        self.stdout.write(f"  DOM Elements: {results['avg_dom_elements']:.0f}")
        self.stdout.write(f"  Player Cards: {results['player_cards']}")
        self.stdout.write(f"  Test Runs: {results['runs']}")

    def display_browser_results(self, results):
        """Display browser performance results."""
        self.stdout.write("\n🌐 Browser Performance Results:")
        self.stdout.write(f"  Page Load Time: {results['avg_load_time']:.2f}s (max: {results['max_load_time']:.2f}s)")
        self.stdout.write(f"  DOM Elements: {results['avg_dom_elements']:.0f}")
        
        if results['avg_memory_used']:
            self.stdout.write(f"  Memory Usage: {results['avg_memory_used']/1024/1024:.1f}MB")
        
        self.stdout.write(f"  Player Cards: {results['player_cards']}")
        self.stdout.write(f"  Successful Runs: {results['successful_runs']}")

    def display_performance_score(self, server_results):
        """Calculate and display overall performance score."""
        score = 100
        issues = []
        
        # Server response time scoring
        if server_results['avg_response_time'] > 1.0:
            score -= 30
            issues.append(f"Slow server response ({server_results['avg_response_time']:.2f}s)")
        elif server_results['avg_response_time'] > 0.5:
            score -= 15
            issues.append(f"Moderate server response ({server_results['avg_response_time']:.2f}s)")
        
        # HTML size scoring
        html_size_kb = server_results['avg_html_size'] / 1024
        if html_size_kb > 300:
            score -= 25
            issues.append(f"Large HTML size ({html_size_kb:.1f}KB)")
        elif html_size_kb > 200:
            score -= 10
            issues.append(f"Moderate HTML size ({html_size_kb:.1f}KB)")
        
        # DOM complexity scoring
        if server_results['avg_dom_elements'] > 2000:
            score -= 20
            issues.append(f"High DOM complexity ({server_results['avg_dom_elements']:.0f} elements)")
        elif server_results['avg_dom_elements'] > 1500:
            score -= 10
            issues.append(f"Moderate DOM complexity ({server_results['avg_dom_elements']:.0f} elements)")
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write("🎯 PERFORMANCE SCORE")
        self.stdout.write("="*50)
        
        if score >= 90:
            score_style = self.style.SUCCESS
            rating = "EXCELLENT ✨"
        elif score >= 75:
            score_style = self.style.SUCCESS
            rating = "GOOD ✅"
        elif score >= 60:
            score_style = self.style.WARNING
            rating = "NEEDS IMPROVEMENT ⚠️"
        else:
            score_style = self.style.ERROR
            rating = "POOR ❌"
        
        self.stdout.write(score_style(f"Score: {score}/100 - {rating}"))
        
        if issues:
            self.stdout.write("\n🔍 Issues Found:")
            for issue in issues:
                self.stdout.write(f"  • {issue}")
        
        self.stdout.write("\n💡 Recommendations:")
        if server_results['avg_response_time'] > 0.5:
            self.stdout.write("  • Optimize database queries and caching")
        if html_size_kb > 200:
            self.stdout.write("  • Reduce HTML payload size")
        if server_results['avg_dom_elements'] > 1500:
            self.stdout.write("  • Simplify DOM structure")

    def cleanup_test_data(self, ranking):
        """Clean up test data."""
        self.stdout.write("🧹 Cleaning up test data...")
        
        # Delete player rankings first (foreign key constraint)
        models.PlayerRanking.objects.filter(ranking=ranking).delete()
        
        # Delete players
        players = models.Player.objects.filter(slug__startswith=f'test-player-{ranking.id}-')
        player_count = players.count()
        players.delete()
        
        # Delete ranking
        ranking.delete()
        
        self.stdout.write(f"Cleaned up {player_count} players and 1 ranking") 