from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
import difflib
from overslot.models import Team, TeamDuplicateDecision, PlayerRanking, Game, PotentialTeamDuplicate
from django.views.decorators.http import require_POST


def normalize_team_name(name):
    """Normalize team names for comparison"""
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace(",", "")


def get_name_similarity(name1, name2):
    """Calculate similarity between two names using difflib"""
    norm1 = normalize_team_name(name1)
    norm2 = normalize_team_name(name2)
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


@staff_member_required
def team_duplicate_dashboard(request):
    """Main dashboard for duplicate team management"""
    context = {}
    
    # Get counts
    context['total_teams'] = Team.objects.filter(active=True).count()
    context['decisions_made'] = TeamDuplicateDecision.objects.count()
    context['merged_count'] = TeamDuplicateDecision.objects.filter(decision='merged').count()
    context['separate_count'] = TeamDuplicateDecision.objects.filter(decision='separate').count()
    
    # Get potential duplicates count
    context['pending_count'] = PotentialTeamDuplicate.objects.count()
    
    # Get the highest scoring potential duplicate
    context['next_pair'] = PotentialTeamDuplicate.objects.select_related('team1', 'team2').first()
    
    # Get recent decisions
    context['recent_decisions'] = TeamDuplicateDecision.objects.select_related(
        'team1', 'team2', 'decided_by'
    ).order_by('-created')[:10]
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        potential_duplicates = PotentialTeamDuplicate.objects.select_related('team1', 'team2').filter(
            Q(team1_name__icontains=search_query) |
            Q(team2_name__icontains=search_query) |
            Q(team1_abbreviation__icontains=search_query) |
            Q(team2_abbreviation__icontains=search_query)
        ).order_by('-similarity_score')
        context['search_query'] = search_query
    else:
        potential_duplicates = PotentialTeamDuplicate.objects.select_related('team1', 'team2').order_by('-similarity_score')
    
    # Pagination
    paginator = Paginator(potential_duplicates, 50)
    page_number = request.GET.get('page')
    context['potential_duplicates'] = paginator.get_page(page_number)
    
    return render(request, 'admin/team_duplicate_dashboard.html', context)


@staff_member_required
def review_team_duplicate(request):
    """Review the next potential duplicate team pair"""
    next_pair = PotentialTeamDuplicate.objects.select_related('team1', 'team2').first()
    
    if not next_pair:
        messages.info(request, "No more potential duplicates to review! Run 'django-admin generate_team_duplicates' to find new ones.")
        return redirect('team_duplicate_dashboard')
    
    # Redirect to the specific pair review URL
    return redirect('review_team_duplicate_pair', 
                   team1_id=next_pair.team1.pk, 
                   team2_id=next_pair.team2.pk)


@staff_member_required
def review_team_duplicate_pair(request, team1_id, team2_id):
    """Review a specific duplicate team pair"""
    context = {}
    context['team1'] = get_object_or_404(Team, pk=team1_id)
    context['team2'] = get_object_or_404(Team, pk=team2_id)
    
    # Try to get the potential duplicate record for similarity score and reasons
    potential_qs = PotentialTeamDuplicate.objects.filter(
        Q(team1=context['team1'], team2=context['team2']) |
        Q(team1=context['team2'], team2=context['team1'])
    ).order_by('-similarity_score', '-created')
    if potential_qs.exists():
        potential_dup = potential_qs.first()
        context['similarity'] = potential_dup.similarity_score
        context['match_reasons'] = potential_dup.match_reasons
    else:
        # Fallback to calculating similarity
        context['similarity'] = get_name_similarity(context['team1'].name, context['team2'].name)
        context['match_reasons'] = []
    
    # Get related data for both teams
    # Count player rankings (using school_team FK, not school field)
    context['team1_player_rankings_count'] = PlayerRanking.objects.filter(
        school_team=context['team1']
    ).count()
    
    context['team2_player_rankings_count'] = PlayerRanking.objects.filter(
        school_team=context['team2']
    ).count()
    
    # Get sample player rankings
    context['team1_player_rankings'] = PlayerRanking.objects.filter(
        school_team=context['team1']
    ).select_related('player', 'ranking')[:10]
    
    context['team2_player_rankings'] = PlayerRanking.objects.filter(
        school_team=context['team2']
    ).select_related('player', 'ranking')[:10]
    
    # Count games
    context['team1_games_count'] = Game.objects.filter(
        Q(home_team=context['team1']) | Q(away_team=context['team1'])
    ).count()
    
    context['team2_games_count'] = Game.objects.filter(
        Q(home_team=context['team2']) | Q(away_team=context['team2'])
    ).count()
    
    # Get sample games
    context['team1_games'] = Game.objects.filter(
        Q(home_team=context['team1']) | Q(away_team=context['team1'])
    ).select_related('home_team', 'away_team')[:10]
    
    context['team2_games'] = Game.objects.filter(
        Q(home_team=context['team2']) | Q(away_team=context['team2'])
    ).select_related('home_team', 'away_team')[:10]
    
    return render(request, 'admin/review_team_duplicate.html', context)


@staff_member_required
def merge_teams(request, team1_id, team2_id):
    """Merge two teams into one"""
    if request.method != 'POST':
        return redirect('team_duplicate_dashboard')
    
    primary_team = request.POST.get('primary_team')
    notes = request.POST.get('notes', '')
    
    if not primary_team:
        messages.error(request, "Please select which team to keep as primary")
        return redirect('review_team_duplicate_pair', team1_id=team1_id, team2_id=team2_id)
    
    try:
        team1 = get_object_or_404(Team, pk=team1_id)
        team2 = get_object_or_404(Team, pk=team2_id)
        
        # Determine which team to keep and which to remove
        if primary_team == str(team1.pk):
            keeper = team1
            removed = team2
        else:
            keeper = team2
            removed = team1
        
        with transaction.atomic():
            # Update PlayerRanking records - update school_team FK (NOT the school CharField)
            ranking_count = PlayerRanking.objects.filter(school_team=removed).update(school_team=keeper)
            
            # Update Game records
            home_games_count = Game.objects.filter(home_team=removed).update(home_team=keeper)
            away_games_count = Game.objects.filter(away_team=removed).update(away_team=keeper)
            total_games = home_games_count + away_games_count
            
            # Update any TeamDuplicateDecision records that reference the removed team
            TeamDuplicateDecision.objects.filter(primary_team=removed).update(primary_team=keeper)
            
            # Clean up any other PotentialTeamDuplicate records involving the removed team
            other_potential_dupes = PotentialTeamDuplicate.objects.filter(
                Q(team1=removed) | Q(team2=removed)
            ).exclude(
                Q(team1=team1, team2=team2) | Q(team1=team2, team2=team1)
            )
            other_dupes_count = other_potential_dupes.count()
            other_potential_dupes.delete()
            
            # Record the decision with detailed merge information
            merge_notes = f"MERGE DETAILS:\n"
            merge_notes += f"Kept: {keeper.name} (ID: {keeper.pk})\n"
            merge_notes += f"Removed: {removed.name} (ID: {removed.pk})\n"
            merge_notes += f"Transferred {ranking_count} player ranking records (school_team FK)\n"
            merge_notes += f"Transferred {total_games} game records ({home_games_count} home, {away_games_count} away)\n"
            merge_notes += f"Cleaned up {other_dupes_count} other potential duplicate records\n"
            merge_notes += f"\nNOTE: The 'school' CharField in PlayerRanking was NOT modified - only the school_team FK was updated.\n"
            if notes:
                merge_notes += f"\nUser Notes:\n{notes}"
            
            TeamDuplicateDecision.objects.create(
                team1=team1,
                team2=team2,
                decision='merged',
                decided_by=request.user,
                primary_team=keeper,
                notes=merge_notes
            )
            
            # Remove the current potential duplicate record since it's now decided
            PotentialTeamDuplicate.objects.filter(
                Q(team1=team1, team2=team2) |
                Q(team1=team2, team2=team1)
            ).delete()
            
            # Deactivate the removed team (don't delete to preserve referential integrity)
            removed.active = False
            removed.save()
            
            messages.success(request, 
                f"Successfully merged teams. Kept: {keeper.name}. "
                f"Transferred {ranking_count} player rankings and {total_games} games. "
                f"Note: The 'school' field in PlayerRanking was NOT modified - only the FK was updated."
            )
            
    except Exception as e:
        messages.error(request, f"Error merging teams: {str(e)}")
    
    return redirect('team_duplicate_dashboard')


@staff_member_required
def mark_teams_separate(request, team1_id, team2_id):
    """Mark two teams as separate (not duplicates)"""
    if request.method != 'POST':
        return redirect('team_duplicate_dashboard')
    
    notes = request.POST.get('notes', '')
    
    try:
        team1 = get_object_or_404(Team, pk=team1_id)
        team2 = get_object_or_404(Team, pk=team2_id)
        
        with transaction.atomic():
            # Record the decision
            TeamDuplicateDecision.objects.create(
                team1=team1,
                team2=team2,
                decision='separate',
                decided_by=request.user,
                notes=notes
            )
            
            # Remove the potential duplicate record since it's now decided
            PotentialTeamDuplicate.objects.filter(
                Q(team1=team1, team2=team2) |
                Q(team1=team2, team2=team1)
            ).delete()
        
        messages.success(request, f"Marked {team1.name} and {team2.name} as separate teams")
        
    except Exception as e:
        messages.error(request, f"Error recording decision: {str(e)}")
    
    return redirect('team_duplicate_dashboard')


@staff_member_required
def team_duplicate_history(request):
    """View history of team duplicate decisions"""
    context = {}
    
    # Get summary stats
    all_decisions = TeamDuplicateDecision.objects.all()
    context['total_decisions'] = all_decisions.count()
    context['merged_count'] = all_decisions.filter(decision='merged').count()
    context['separate_count'] = all_decisions.filter(decision='separate').count()
    
    decisions = TeamDuplicateDecision.objects.select_related(
        'team1', 'team2', 'decided_by'
    ).order_by('-created')
    
    # Pagination
    paginator = Paginator(decisions, 50)
    page_number = request.GET.get('page')
    context['decisions'] = paginator.get_page(page_number)
    
    return render(request, 'admin/team_duplicate_history.html', context)
