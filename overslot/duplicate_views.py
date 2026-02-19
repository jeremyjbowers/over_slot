from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from collections import defaultdict
import difflib
from overslot.models import Player, DuplicateDecision, PlayerRanking, Article, PotentialDuplicate, PlayerStatSeason
from django.views.decorators.http import require_POST


def normalize_name(name):
    """Normalize player names for comparison"""
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace(",", "")


def get_name_similarity(name1, name2):
    """Calculate similarity between two names using difflib"""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


@staff_member_required
def duplicate_dashboard(request):
    """Main dashboard for duplicate management"""
    context = {}
    
    # Get counts
    context['total_players'] = Player.objects.filter(active=True).count()
    context['decisions_made'] = DuplicateDecision.objects.count()
    context['merged_count'] = DuplicateDecision.objects.filter(decision='merged').count()
    context['separate_count'] = DuplicateDecision.objects.filter(decision='separate').count()
    
    # Get potential duplicates count (much faster now!)
    context['pending_count'] = PotentialDuplicate.objects.count()
    
    # Get the highest scoring potential duplicate
    context['next_pair'] = PotentialDuplicate.objects.select_related('player1', 'player2').first()
    
    # Get recent decisions
    context['recent_decisions'] = DuplicateDecision.objects.select_related(
        'player1', 'player2', 'decided_by'
    ).order_by('-created')[:10]
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        potential_duplicates = PotentialDuplicate.objects.select_related('player1', 'player2').filter(
            Q(player1_name__icontains=search_query) |
            Q(player2_name__icontains=search_query) |
            Q(player1_school__icontains=search_query) |
            Q(player2_school__icontains=search_query)
        ).order_by('-similarity_score')
        context['search_query'] = search_query
    else:
        potential_duplicates = PotentialDuplicate.objects.select_related('player1', 'player2').order_by('-similarity_score')
    
    # Pagination
    paginator = Paginator(potential_duplicates, 50)
    page_number = request.GET.get('page')
    context['potential_duplicates'] = paginator.get_page(page_number)
    
    return render(request, 'admin/duplicate_dashboard.html', context)


@staff_member_required
def review_duplicate(request):
    """Review the next potential duplicate pair"""
    next_pair = PotentialDuplicate.objects.select_related('player1', 'player2').first()
    
    if not next_pair:
        messages.info(request, "No more potential duplicates to review! Run 'django-admin generate_player_duplicates' to find new ones.")
        return redirect('duplicate_dashboard')
    
    # Redirect to the specific pair review URL
    return redirect('review_duplicate_pair', 
                   player1_uuid=next_pair.player1.uuid, 
                   player2_uuid=next_pair.player2.uuid)


@staff_member_required
def review_duplicate_pair(request, player1_uuid, player2_uuid):
    """Review a specific duplicate pair"""
    context = {}
    context['player1'] = get_object_or_404(Player, uuid=player1_uuid)
    context['player2'] = get_object_or_404(Player, uuid=player2_uuid)
    
    # Try to get the potential duplicate record for similarity score and reasons
    potential_qs = PotentialDuplicate.objects.filter(
        Q(player1=context['player1'], player2=context['player2']) |
        Q(player1=context['player2'], player2=context['player1'])
    ).order_by('-similarity_score', '-created')
    if potential_qs.exists():
        potential_dup = potential_qs.first()
        context['similarity'] = potential_dup.similarity_score
        context['match_reasons'] = potential_dup.match_reasons
    else:
        # Fallback to calculating similarity
        context['similarity'] = get_name_similarity(context['player1'].name, context['player2'].name)
        context['match_reasons'] = []
    
    # Get related data for both players
    context['player1_rankings'] = PlayerRanking.objects.filter(
        player=context['player1']
    ).select_related('ranking').order_by('-ranking__year', 'rank')
    
    context['player2_rankings'] = PlayerRanking.objects.filter(
        player=context['player2']
    ).select_related('ranking').order_by('-ranking__year', 'rank')
    
    context['player1_articles'] = Article.objects.filter(
        players=context['player1'], publish=True, active=True
    ).order_by('-created')[:5]
    
    context['player2_articles'] = Article.objects.filter(
        players=context['player2'], publish=True, active=True
    ).order_by('-created')[:5]
    
    return render(request, 'admin/review_duplicate.html', context)


@staff_member_required
def merge_players(request, player1_uuid, player2_uuid):
    """Merge two players into one"""
    if request.method != 'POST':
        return redirect('duplicate_dashboard')
    
    primary_player = request.POST.get('primary_player')
    notes = request.POST.get('notes', '')
    
    if not primary_player:
        messages.error(request, "Please select which player to keep as primary")
        return redirect('review_duplicate_pair', player1_uuid=player1_uuid, player2_uuid=player2_uuid)
    
    try:
        player1 = get_object_or_404(Player, uuid=player1_uuid)
        player2 = get_object_or_404(Player, uuid=player2_uuid)
        
        # Determine which player to keep and which to remove
        if primary_player == str(player1.uuid):
            keeper = player1
            removed = player2
        else:
            keeper = player2
            removed = player1
        
        with transaction.atomic():
            # Move all PlayerRanking records to the keeper
            ranking_count = PlayerRanking.objects.filter(player=removed).update(player=keeper)
            
            # Move all Article relationships to the keeper
            article_count = 0
            for article in Article.objects.filter(players=removed):
                article.players.remove(removed)
                article.players.add(keeper)
                article_count += 1
            
            # Update any DuplicateDecision records that reference the removed player
            # (though these use SET_NULL, so they should be fine)
            DuplicateDecision.objects.filter(primary_player=removed).update(primary_player=keeper)
            
            # Clean up any other PotentialDuplicate records involving the removed player
            other_potential_dupes = PotentialDuplicate.objects.filter(
                Q(player1=removed) | Q(player2=removed)
            ).exclude(
                Q(player1=player1, player2=player2) | Q(player1=player2, player2=player1)
            )
            other_dupes_count = other_potential_dupes.count()
            other_potential_dupes.delete()
            
            # Record the decision with detailed merge information
            merge_notes = f"MERGE DETAILS:\n"
            merge_notes += f"Kept: {keeper.name} (UUID: {keeper.uuid})\n"
            merge_notes += f"Removed: {removed.name} (UUID: {removed.uuid})\n"
            merge_notes += f"Transferred {ranking_count} ranking records\n"
            merge_notes += f"Transferred {article_count} article relationships\n"
            merge_notes += f"Cleaned up {other_dupes_count} other potential duplicate records\n"
            if notes:
                merge_notes += f"\nUser Notes:\n{notes}"
            
            DuplicateDecision.objects.create(
                player1=player1,
                player2=player2,
                decision='merged',
                decided_by=request.user,
                primary_player=keeper,
                notes=merge_notes
            )
            
            # Remove the current potential duplicate record since it's now decided
            PotentialDuplicate.objects.filter(
                Q(player1=player1, player2=player2) |
                Q(player1=player2, player2=player1)
            ).delete()
            
            # Deactivate the removed player (don't delete to preserve referential integrity)
            removed.active = False
            removed.save()
            
            messages.success(request, 
                f"Successfully merged players. Kept: {keeper.name}. "
                f"Transferred {ranking_count} rankings and {article_count} article relationships."
            )
            
    except Exception as e:
        messages.error(request, f"Error merging players: {str(e)}")
    
    return redirect('duplicate_dashboard')


@staff_member_required
def mark_separate(request, player1_uuid, player2_uuid):
    """Mark two players as separate (not duplicates)"""
    if request.method != 'POST':
        return redirect('duplicate_dashboard')
    
    notes = request.POST.get('notes', '')
    
    try:
        player1 = get_object_or_404(Player, uuid=player1_uuid)
        player2 = get_object_or_404(Player, uuid=player2_uuid)
        
        with transaction.atomic():
            # Record the decision
            DuplicateDecision.objects.create(
                player1=player1,
                player2=player2,
                decision='separate',
                decided_by=request.user,
                notes=notes
            )
            
            # Remove the potential duplicate record since it's now decided
            PotentialDuplicate.objects.filter(
                Q(player1=player1, player2=player2) |
                Q(player1=player2, player2=player1)
            ).delete()
        
        messages.success(request, f"Marked {player1.name} and {player2.name} as separate players")
        
    except Exception as e:
        messages.error(request, f"Error recording decision: {str(e)}")
    
    return redirect('duplicate_dashboard')


@staff_member_required
def data_status(request):
    """
    Internal status page: shows PlayerStatSeason counts by stat year
    and level breakdowns. Draft year is intentionally not shown.
    """
    by_year = (
        PlayerStatSeason.objects.values('year')
        .annotate(
            total=Count('id'),
            high_school=Count('id', filter=Q(level="High School")),
            college=Count('id', filter=Q(level="College")),
        )
        .order_by('-year')
    )
    context = {
        'by_year': by_year,
    }
    return render(request, 'admin/data_status.html', context)

@staff_member_required
def duplicate_history(request):
    """View history of duplicate decisions"""
    context = {}
    
    # Get summary stats
    all_decisions = DuplicateDecision.objects.all()
    context['total_decisions'] = all_decisions.count()
    context['merged_count'] = all_decisions.filter(decision='merged').count()
    context['separate_count'] = all_decisions.filter(decision='separate').count()
    
    decisions = DuplicateDecision.objects.select_related(
        'player1', 'player2', 'decided_by'
    ).order_by('-created')
    
    # Pagination
    paginator = Paginator(decisions, 50)
    page_number = request.GET.get('page')
    context['decisions'] = paginator.get_page(page_number)
    
    return render(request, 'admin/duplicate_history.html', context)


@staff_member_required
def search_duplicates(request):
    """Search for specific players to check for duplicates"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'players': []})
    
    players = Player.objects.filter(
        Q(name__icontains=query),
        active=True
    ).values('uuid', 'name', 'position', 'school')[:20]
    
    return JsonResponse({'players': list(players)})


@staff_member_required
def manual_duplicate_check(request, player1_uuid, player2_uuid):
    """Manually check if two specific players are duplicates"""
    try:
        player1 = get_object_or_404(Player, uuid=player1_uuid)
        player2 = get_object_or_404(Player, uuid=player2_uuid)
        
        # Check if we already have a decision for this pair
        try:
            existing_decision = DuplicateDecision.objects.get(
                Q(player1=player1, player2=player2) | 
                Q(player1=player2, player2=player1)
            )
            messages.info(request, f"Already decided: {existing_decision.decision}")
            return redirect('duplicate_history')
        except DuplicateDecision.DoesNotExist:
            pass
        
        # Redirect to the pair review
        return redirect('review_duplicate_pair', 
                       player1_uuid=player1_uuid, 
                       player2_uuid=player2_uuid)
        
    except Player.DoesNotExist:
        messages.error(request, "One or both players not found")
        return redirect('duplicate_dashboard') 


@staff_member_required
@require_POST
def suggest_duplicate(request):
    """Allow staff to suggest a duplicate pair explicitly.
    Creates or updates a PotentialDuplicate entry with optional note as a reason,
    then redirects to review page for that pair.
    """
    player1_uuid = request.POST.get('player1_uuid')
    player2_uuid = request.POST.get('player2_uuid')
    note = request.POST.get('note', '').strip()

    if not player1_uuid or not player2_uuid:
        messages.error(request, "Please select two players to suggest as duplicates")
        return redirect('duplicate_dashboard')

    if player1_uuid == player2_uuid:
        messages.error(request, "Please choose two different players")
        return redirect('duplicate_dashboard')

    try:
        player1 = get_object_or_404(Player, uuid=player1_uuid)
        player2 = get_object_or_404(Player, uuid=player2_uuid)

        # Ensure ordering for uniqueness
        p_low, p_high = (player1, player2)
        if str(player1.uuid) > str(player2.uuid):
            p_low, p_high = (player2, player1)

        # If there's already a final decision, route accordingly
        existing_decision = DuplicateDecision.objects.filter(
            Q(player1=p_low, player2=p_high) | Q(player1=p_high, player2=p_low)
        ).first()
        if existing_decision:
            messages.info(request, f"Already decided: {existing_decision.decision}")
            return redirect('duplicate_history')

        # Upsert PotentialDuplicate with a high similarity and add note as a reason
        potential, created = PotentialDuplicate.objects.get_or_create(
            player1=p_low,
            player2=p_high,
            defaults={
                'similarity_score': get_name_similarity(p_low.name, p_high.name),
                'match_reasons': [],
            }
        )
        # Append note if provided and not already present
        if note:
            reasons = potential.match_reasons or []
            reason_text = f"Staff suggestion: {note}"
            if reason_text not in reasons:
                reasons.append(reason_text)
                potential.match_reasons = reasons
        # Save to ensure denormalized fields update
        potential.save()

        messages.success(request, "Suggestion recorded. Review this pair now.")
        return redirect('review_duplicate_pair', player1_uuid=p_low.uuid, player2_uuid=p_high.uuid)
    except Exception as exc:
        messages.error(request, f"Error suggesting duplicate: {exc}")
        return redirect('duplicate_dashboard')