"""
Staff review of college stat lines whose school doesn't match the player.

The loaders queue a StatTeamLink whenever a stat row's name matches a player but
its team isn't one of his schools. Here a reviewer answers once per
(name, team, player):

* Same player: the link is accepted and future loads attach that team's stats.
* Different person: the link is rejected and the stat seasons from that team
  are removed from the player.
* Move to another player: the seasons move to the right Overslot player, and
  the links record both answers.

The per-player page lists every college stat season grouped by team, so a
melted player (two people under one name) can be split by hand too.
"""

from collections import defaultdict

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from overslot import models
from overslot.stat_identity import normalize_person_name, normalize_school


def _seasons_for_team(player, team_key):
    trackman = [
        s
        for s in models.PlayerStatSeason.objects.filter(player=player, level="College")
        if normalize_school(s.school) == team_key
    ]
    six43 = [
        s
        for s in models.Player643StatSeason.objects.filter(player=player)
        if normalize_school(s.team_name) == team_key
    ]
    return trackman, six43


def _team_groups(player):
    """College stat seasons for a player, grouped by normalized team."""
    groups = defaultdict(lambda: {"team": None, "trackman": [], "six43": []})
    for s in models.PlayerStatSeason.objects.filter(player=player, level="College").order_by("year"):
        key = normalize_school(s.school) or "(no team)"
        groups[key]["team"] = groups[key]["team"] or s.school
        groups[key]["trackman"].append(s)
    for s in models.Player643StatSeason.objects.filter(player=player).order_by("year"):
        key = normalize_school(s.team_name) or "(no team)"
        groups[key]["team"] = groups[key]["team"] or s.team_name
        groups[key]["six43"].append(s)
    return groups


def _ranking_summary(player):
    rows = (
        models.PlayerRanking.objects.filter(player=player)
        .select_related("ranking")
        .order_by("-ranking__year")
    )
    seen, out = set(), []
    for pr in rows:
        key = (pr.ranking.year if pr.ranking else None, pr.school, pr.level)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "year": pr.ranking.year if pr.ranking else "",
                "school": pr.school,
                "level": pr.level,
                "commitment": pr.commitment,
                "rank": pr.rank,
            }
        )
    return out


def _best_rank(player_ids):
    ranks = (
        models.PlayerRanking.objects.filter(player_id__in=player_ids, active=True, rank__isnull=False)
        .values("player_id")
        .annotate(best=Min("rank"))
    )
    return {r["player_id"]: r["best"] for r in ranks}


@staff_member_required
def stat_link_queue(request):
    status = request.GET.get("status", models.StatTeamLink.PENDING)
    q = request.GET.get("q", "").strip()
    links = models.StatTeamLink.objects.select_related("player", "decided_by").filter(status=status)
    if q:
        links = links.filter(Q(raw_name__icontains=q) | Q(raw_team__icontains=q) | Q(player__name__icontains=q))
    links = list(links)
    best = _best_rank({l.player_id for l in links})
    # Conflicts first, then the players subscribers are most likely to look at.
    links.sort(
        key=lambda l: (
            l.reason != models.StatTeamLink.REASON_CONFLICT,
            best.get(l.player_id) if best.get(l.player_id) is not None else 10_000,
            l.raw_name or "",
        )
    )
    for l in links:
        l.best_rank = best.get(l.player_id)
        l.ranked = _ranking_summary(l.player)[:3]
    page = Paginator(links, 50).get_page(request.GET.get("page"))
    counts = dict(
        models.StatTeamLink.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    return render(
        request,
        "admin/stat_link_queue.html",
        {"page": page, "status": status, "q": q, "counts": counts},
    )


@staff_member_required
def stat_link_player(request, player_uuid):
    player = get_object_or_404(models.Player, uuid=player_uuid)
    groups = _team_groups(player)
    links = {
        (l.team_key): l
        for l in models.StatTeamLink.objects.filter(player=player).order_by("-last_modified")
    }
    ranked_keys = set()
    for pr in models.PlayerRanking.objects.filter(player=player).values_list("school", "commitment"):
        ranked_keys.update(normalize_school(v) for v in pr if v)
    teams = []
    for key, g in sorted(groups.items(), key=lambda kv: min([s.year for s in kv[1]["trackman"] + kv[1]["six43"]] or ["9999"])):
        teams.append(
            {
                "key": key,
                "team": g["team"],
                "trackman": g["trackman"],
                "six43": g["six43"],
                "on_record": key in ranked_keys,
                "link": links.get(key),
            }
        )
    return render(
        request,
        "admin/stat_link_player.html",
        {"player": player, "teams": teams, "rankings": _ranking_summary(player)},
    )


def _resolve_target(value):
    """Find a player from a UUID, slug or player-page URL typed by a reviewer."""
    value = (value or "").strip().rstrip("/")
    if not value:
        return None
    value = value.split("/")[-1]
    player = models.Player.objects.filter(slug=value).first()
    if player:
        return player
    try:
        return models.Player.objects.filter(uuid=value).first()
    except Exception:
        return None


@staff_member_required
@require_POST
def stat_link_decide(request, player_uuid):
    player = get_object_or_404(models.Player, uuid=player_uuid)
    team_key = request.POST.get("team_key", "")
    raw_team = request.POST.get("raw_team") or team_key
    action = request.POST.get("action")
    notes = request.POST.get("notes", "").strip() or None
    next_url = request.POST.get("next") or "stat_link_queue"
    if not team_key or action not in ("accept", "reject", "move"):
        messages.error(request, "Missing team or action.")
        return redirect(next_url)

    now = timezone.now()
    name_key = request.POST.get("name_key") or normalize_person_name(player.name)

    def decide(target_player, status):
        link, _ = models.StatTeamLink.objects.get_or_create(
            name_key=name_key,
            team_key=team_key,
            player=target_player,
            defaults={"raw_name": player.name, "raw_team": raw_team},
        )
        link.status = status
        link.decided_by = request.user
        link.decided_at = now
        if notes:
            link.notes = notes
        link.save()
        return link

    with transaction.atomic():
        if action == "accept":
            decide(player, models.StatTeamLink.ACCEPTED)
            messages.success(request, f"{player.name} at {raw_team}: marked as the same player.")
        else:
            trackman, six43 = _seasons_for_team(player, team_key)
            target = None
            if action == "move":
                target = _resolve_target(request.POST.get("target"))
                if not target or target.pk == player.pk:
                    messages.error(request, "Pick a different player to move these seasons to.")
                    return redirect(next_url)
            decide(player, models.StatTeamLink.REJECTED)
            if target is None:
                n1 = len(trackman)
                n2 = len(six43)
                for s in trackman:
                    s.delete()
                for s in six43:
                    s.delete()
                messages.success(
                    request,
                    f"{player.name} at {raw_team}: marked as a different person. "
                    f"Removed {n1} Trackman and {n2} 6-4-3 season(s).",
                )
            else:
                decide(target, models.StatTeamLink.ACCEPTED)
                moved, skipped = 0, []
                for s in trackman:
                    if models.PlayerStatSeason.objects.filter(player=target, year=s.year, level=s.level).exists():
                        skipped.append(f"Trackman {s.year}")
                        continue
                    s.player = target
                    s.save()
                    moved += 1
                for s in six43:
                    if models.Player643StatSeason.objects.filter(
                        player=target, year=s.year, team_name=s.team_name
                    ).exists():
                        skipped.append(f"6-4-3 {s.year}")
                        continue
                    s.player = target
                    s.save()
                    moved += 1
                msg = f"Moved {moved} season(s) from {player.name} to {target.name}."
                if skipped:
                    msg += f" {target.name} already had: {', '.join(skipped)} (left in place)."
                messages.success(request, msg)

        # Any other pending link for this name/team on this player is now settled.
        models.StatTeamLink.objects.filter(
            team_key=team_key, player=player, status=models.StatTeamLink.PENDING
        ).update(status=models.StatTeamLink.REJECTED if action != "accept" else models.StatTeamLink.ACCEPTED,
                 decided_by=request.user, decided_at=now)

    return redirect(next_url)
