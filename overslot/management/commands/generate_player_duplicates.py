import time
from collections import defaultdict
from difflib import SequenceMatcher
from django.core.management.base import BaseCommand
from django.db import transaction
from overslot.models import Player, PotentialDuplicate, DuplicateDecision


class Command(BaseCommand):
    help = 'Generate potential duplicate player pairs and store them for fast access'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-score',
            type=float,
            default=0.6,
            help='Minimum similarity score to consider as potential duplicate (0.0-1.0)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing potential duplicates before generating new ones'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of potential duplicates to create in each batch'
        )

    def handle(self, *args, **options):
        min_score = options['min_score']
        clear_existing = options['clear']
        batch_size = options['batch_size']
        
        start_time = time.time()
        
        if clear_existing:
            self.stdout.write('Clearing existing potential duplicates...')
            PotentialDuplicate.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing potential duplicates'))
        
        # Get all active players
        players = list(Player.objects.filter(active=True).select_related())
        total_players = len(players)
        self.stdout.write(f'Processing {total_players} active players...')
        
        # Get existing decisions to avoid re-suggesting already decided pairs
        existing_decisions = set()
        for decision in DuplicateDecision.objects.all():
            pair = tuple(sorted([str(decision.player1.uuid), str(decision.player2.uuid)]))
            existing_decisions.add(pair)
        
        self.stdout.write(f'Found {len(existing_decisions)} existing decisions to skip')
        
        # Group players by name similarity for faster processing
        name_groups = self._group_players_by_name(players)
        
        potential_duplicates = []
        pairs_processed = 0
        pairs_found = 0
        
        for group_players in name_groups.values():
            if len(group_players) < 2:
                continue
                
            # Compare all pairs within this name group
            for i, player1 in enumerate(group_players):
                for player2 in group_players[i+1:]:
                    pairs_processed += 1
                    
                    # Skip if already decided
                    pair_key = tuple(sorted([str(player1.uuid), str(player2.uuid)]))
                    if pair_key in existing_decisions:
                        continue
                    
                    # Calculate similarity
                    score, reasons = self._calculate_similarity(player1, player2)
                    
                    if score >= min_score:
                        # Ensure consistent (ordered) pair to avoid (A,B) and (B,A) duplicates
                        p1, p2 = (player1, player2)
                        if str(player1.uuid) > str(player2.uuid):
                            p1, p2 = player2, player1

                        # Populate denormalized fields since bulk_create bypasses save()
                        potential_duplicates.append(PotentialDuplicate(
                            player1=p1,
                            player2=p2,
                            similarity_score=score,
                            match_reasons=reasons,
                            player1_name=p1.name,
                            player2_name=p2.name,
                            player1_school=p1.school,
                            player2_school=p2.school,
                            player1_state=p1.state,
                            player2_state=p2.state,
                        ))
                        pairs_found += 1
                        
                        # Batch insert for performance
                        if len(potential_duplicates) >= batch_size:
                            self._bulk_create_duplicates(potential_duplicates)
                            potential_duplicates = []
                    
                    # Progress update
                    if pairs_processed % 10000 == 0:
                        elapsed = time.time() - start_time
                        self.stdout.write(f'Processed {pairs_processed:,} pairs, found {pairs_found:,} potential duplicates ({elapsed:.1f}s)')
        
        # Insert remaining duplicates
        if potential_duplicates:
            self._bulk_create_duplicates(potential_duplicates)
        
        elapsed = time.time() - start_time
        total_potential = PotentialDuplicate.objects.count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Complete! Processed {pairs_processed:,} pairs in {elapsed:.1f}s. '
                f'Found {pairs_found:,} new potential duplicates. '
                f'Total potential duplicates in database: {total_potential:,}'
            )
        )

    def _group_players_by_name(self, players):
        """Group players by similar names to reduce comparison space."""
        groups = defaultdict(list)
        
        for player in players:
            if not player.name:
                continue
                
            # Create a normalized name key for grouping
            name_key = self._normalize_name(player.name)
            groups[name_key].append(player)
        
        return groups

    def _normalize_name(self, name):
        """Create a normalized version of name for grouping similar names."""
        if not name:
            return ""
        
        # Remove common suffixes and prefixes, normalize case
        name = name.lower().strip()
        
        # Remove common suffixes
        suffixes = [' jr', ' jr.', ' sr', ' sr.', ' ii', ' iii', ' iv']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
                break
        
        # Sort the words to catch "John Smith" vs "Smith John"
        words = sorted(name.split())
        return ' '.join(words)

    def _calculate_similarity(self, player1, player2):
        """Calculate similarity score and reasons between two players."""
        score = 0.0
        reasons = []
        
        # Name similarity (primary factor - 90% weight)
        name_sim = self._string_similarity(player1.name or "", player2.name or "")
        if name_sim > 0.6:  # Lower threshold since name is primary
            score = name_sim * 0.9  # 90% weight for name
            reasons.append(f"Name similarity: {name_sim:.2f}")
        
        # Additional context information (not heavily weighted since players change schools/positions)
        context_info = []
        
        # School information (just for context)
        if player1.school and player2.school:
            school_sim = self._string_similarity(player1.school, player2.school)
            if school_sim > 0.8:
                score += school_sim * 0.05  # Only 5% weight
                context_info.append(f"School match: {school_sim:.2f}")
            elif school_sim > 0.5:
                context_info.append(f"Similar school: {school_sim:.2f}")
        
        # State information (just for context)
        if player1.state and player2.state:
            if player1.state.lower() == player2.state.lower():
                score += 0.03  # Only 3% weight
                context_info.append("Same state")
            else:
                context_info.append(f"Different states: {player1.state} vs {player2.state}")
        
        # Position information (just for context - players often change positions)
        if player1.position and player2.position:
            pos_sim = self._string_similarity(player1.position, player2.position)
            if pos_sim > 0.8:
                score += pos_sim * 0.02  # Only 2% weight
                context_info.append(f"Position match: {pos_sim:.2f}")
            elif pos_sim > 0.3:
                context_info.append(f"Similar position: {pos_sim:.2f}")
            else:
                context_info.append(f"Different positions: {player1.position} vs {player2.position}")
        
        # Birthdate proximity (just for context)
        if player1.birthdate and player2.birthdate:
            date_diff = abs((player1.birthdate - player2.birthdate).days)
            if date_diff <= 365:  # Within a year
                date_score = max(0, (365 - date_diff) / 365) * 0.02  # Only 2% weight
                score += date_score
                context_info.append(f"Birthdate proximity: {date_diff} days apart")
            else:
                context_info.append(f"Birthdate difference: {date_diff} days apart")
        
        # Add context info to reasons
        reasons.extend(context_info)
        
        return min(score, 1.0), reasons

    def _string_similarity(self, str1, str2):
        """Calculate similarity between two strings using SequenceMatcher."""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def _bulk_create_duplicates(self, potential_duplicates):
        """Bulk create potential duplicates with error handling."""
        try:
            with transaction.atomic():
                PotentialDuplicate.objects.bulk_create(
                    potential_duplicates, 
                    ignore_conflicts=True
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Error bulk creating duplicates: {e}')
            )
            # Fall back to individual creation
            for duplicate in potential_duplicates:
                try:
                    duplicate.save()
                except Exception as individual_error:
                    self.stdout.write(
                        self.style.WARNING(f'Error creating duplicate {duplicate}: {individual_error}')
                    )
