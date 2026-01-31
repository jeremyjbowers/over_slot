import time
from collections import defaultdict
from difflib import SequenceMatcher
from django.core.management.base import BaseCommand
from django.db import transaction
from overslot.models import Team, PotentialTeamDuplicate, TeamDuplicateDecision


def normalize_team_name(name):
    """Normalize team names for comparison"""
    if not name:
        return ""
    # Remove common words and normalize
    name = name.lower().strip()
    # Remove common prefixes/suffixes
    for word in ['university', 'univ', 'college', 'state', 'st', 'the']:
        name = name.replace(word, '')
    # Remove punctuation
    name = name.replace('.', '').replace(',', '').replace('-', ' ').replace("'", '')
    # Normalize whitespace
    return ' '.join(name.split())


def calculate_team_similarity(team1, team2):
    """Calculate similarity between two teams and return score and reasons"""
    reasons = []
    score = 0.0
    
    # Name similarity (weighted heavily)
    norm1 = normalize_team_name(team1.name)
    norm2 = normalize_team_name(team2.name)
    name_similarity = SequenceMatcher(None, norm1, norm2).ratio()
    
    if name_similarity > 0.7:
        score += name_similarity * 0.7
        reasons.append(f"Name similarity: {name_similarity:.2f}")
    
    # Exact name match (case-insensitive)
    if team1.name.lower().strip() == team2.name.lower().strip():
        score = 1.0
        reasons.append("Exact name match")
        return score, reasons
    
    # Abbreviation matching
    if team1.abbreviation and team2.abbreviation:
        if team1.abbreviation.lower() == team2.abbreviation.lower():
            score += 0.2
            reasons.append("Same abbreviation")
        elif team1.abbreviation.lower() in team2.name.lower() or team2.abbreviation.lower() in team1.name.lower():
            score += 0.15
            reasons.append("Abbreviation matches name")
    
    # Check if one name contains the other
    name1_lower = team1.name.lower()
    name2_lower = team2.name.lower()
    if name1_lower in name2_lower or name2_lower in name1_lower:
        if len(name1_lower) > 5 and len(name2_lower) > 5:  # Avoid matching very short names
            score += 0.1
            reasons.append("One name contains the other")
    
    # Check for common variations (e.g., "UCLA" vs "University of California Los Angeles")
    # Remove common words and compare
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if len(words1) > 0 and len(words2) > 0:
        common_words = words1.intersection(words2)
        if len(common_words) >= 2:  # At least 2 common words
            score += 0.1
            reasons.append(f"Common words: {', '.join(common_words)}")
    
    return min(score, 1.0), reasons


class Command(BaseCommand):
    help = 'Generate potential duplicate team pairs and store them for fast access'

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
            self.stdout.write('Clearing existing potential team duplicates...')
            PotentialTeamDuplicate.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing potential team duplicates'))
        
        # Get all active teams
        teams = list(Team.objects.filter(active=True).select_related())
        total_teams = len(teams)
        self.stdout.write(f'Processing {total_teams} active teams...')
        
        # Get existing decisions to avoid re-suggesting already decided pairs
        existing_decisions = set()
        for decision in TeamDuplicateDecision.objects.all():
            pair = tuple(sorted([decision.team1.pk, decision.team2.pk]))
            existing_decisions.add(pair)
        
        self.stdout.write(f'Found {len(existing_decisions)} existing decisions to skip')
        
        # Group teams by normalized name for faster processing
        name_groups = defaultdict(list)
        for team in teams:
            normalized = normalize_team_name(team.name)
            if normalized:
                # Use first few characters as grouping key
                key = normalized[:10] if len(normalized) > 10 else normalized
                name_groups[key].append(team)
        
        potential_duplicates = []
        pairs_processed = 0
        pairs_found = 0
        
        for group_teams in name_groups.values():
            if len(group_teams) < 2:
                continue
                
            # Compare all pairs within this name group
            for i, team1 in enumerate(group_teams):
                for team2 in group_teams[i+1:]:
                    pairs_processed += 1
                    
                    # Skip if already decided
                    pair_key = tuple(sorted([team1.pk, team2.pk]))
                    if pair_key in existing_decisions:
                        continue
                    
                    # Calculate similarity
                    score, reasons = calculate_team_similarity(team1, team2)
                    
                    if score >= min_score:
                        # Ensure consistent (ordered) pair to avoid (A,B) and (B,A) duplicates
                        t1, t2 = (team1, team2)
                        if team1.pk > team2.pk:
                            t1, t2 = team2, team1

                        # Populate denormalized fields since bulk_create bypasses save()
                        potential_duplicates.append(PotentialTeamDuplicate(
                            team1=t1,
                            team2=t2,
                            similarity_score=score,
                            match_reasons=reasons,
                            team1_name=t1.name,
                            team2_name=t2.name,
                            team1_abbreviation=t1.abbreviation,
                            team2_abbreviation=t2.abbreviation,
                        ))
                        pairs_found += 1
                        
                        if len(potential_duplicates) >= batch_size:
                            with transaction.atomic():
                                PotentialTeamDuplicate.objects.bulk_create(potential_duplicates, ignore_conflicts=True)
                            self.stdout.write(f'  Created batch of {len(potential_duplicates)} potential duplicates...')
                            potential_duplicates = []
        
        # Create remaining potential duplicates
        if potential_duplicates:
            with transaction.atomic():
                PotentialTeamDuplicate.objects.bulk_create(potential_duplicates, ignore_conflicts=True)
            self.stdout.write(f'  Created final batch of {len(potential_duplicates)} potential duplicates...')
        
        elapsed_time = time.time() - start_time
        
        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted in {elapsed_time:.2f} seconds:\n'
            f'  Teams processed: {total_teams}\n'
            f'  Pairs compared: {pairs_processed}\n'
            f'  Potential duplicates found: {pairs_found}\n'
            f'  Minimum score: {min_score}'
        ))
