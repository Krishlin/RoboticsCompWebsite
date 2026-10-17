# owner: Krish S
#
# The database side of the bracket. app/bracket/logic.py decides who plays
# whom; this file keeps the elimination Match rows in step with it:
#
#   build_bracket   seed from the final qualification standings and lock
#                   the seeds into a BracketConfig
#   sync_division   after any bracket result, create the series that have
#                   become playable (so a referee screen picks them up) and
#                   report anything that no longer adds up
#   bracket_view    everything the bracket page draws
#
# A series row is created only once both of its teams are known. Until then
# the bracket page draws the slot as TBD from the structure alone, and no
# referee screen offers a match with an empty side.

from app.bracket import logic
from app.db import db
from app.match_state import games_for, series_tally, series_winner_team_id
from app.models import BracketConfig, Match, Team


class BracketError(Exception):
    """A bracket action the head ref asked for that cannot be done as asked."""


def get_config(division):
    return BracketConfig.query.filter_by(division=division).first()


def seeds_for(config):
    return [int(line) for line in config.seeds.splitlines() if line.strip()]


def _elimination_matches(division):
    rows = Match.query.filter_by(division=division, phase="elimination").all()
    return {(m.bracket_side or "W", m.bracket_round, m.bracket_slot): m for m in rows}


def _resolve(config, matches):
    seeds = seeds_for(config)
    nodes = logic.build_nodes(len(seeds), config.format)
    winners = {key: series_winner_team_id(m) for key, m in matches.items()}
    states = logic.resolve(nodes, seeds, winners)
    return seeds, nodes, states


def _pick_arena(division):
    """The arena with the fewest series still to play, so bracket series
    spread across every field the qualification rounds used."""
    arenas = sorted(
        {a for (a,) in db.session.query(Match.arena).filter(Match.division == division).distinct()}
    ) or ["Arena 1"]
    load = dict.fromkeys(arenas, 0)
    pending = Match.query.filter(
        Match.division == division, Match.status.in_(("scheduled", "in_progress"))
    ).all()
    for match in pending:
        if match.arena in load:
            load[match.arena] += 1
    return min(arenas, key=lambda a: (load[a], arenas.index(a)))


def _next_match_number(division):
    highest = (
        db.session.query(db.func.max(Match.match_number))
        .filter(Match.division == division)
        .scalar()
    )
    return (highest or 0) + 1


def sync_division(division, dry_run=False):
    """Bring the elimination rows in line with the bracket. Returns conflicts.

    A conflict is a series that has already been played but whose teams the
    bracket now says are different - which only happens when the head ref
    changes an earlier result after a later series was played. Nothing is
    rewritten in that case; the conflict is reported for a person to settle.

    With dry_run, nothing is written: the admin panel uses it to refuse an
    edit that would cause a conflict before committing it.
    """
    config = get_config(division)
    if config is None:
        return []

    matches = _elimination_matches(division)
    _, nodes, states = _resolve(config, matches)
    conflicts = []
    changed = False

    for node in nodes:
        state = states[node.key]
        existing = matches.get(node.key)
        playable = state.needed and state.red is not None and state.blue is not None
        has_games = existing is not None and (
            games_for(existing.id) or existing.game_started_at is not None
        )

        if playable:
            if existing is None:
                if not dry_run:
                    db.session.add(Match(
                        match_number=_next_match_number(division),
                        phase="elimination",
                        division=division,
                        arena=_pick_arena(division),
                        scheduled_time=None,
                        red_team_id=state.red,
                        blue_team_id=state.blue,
                        status="scheduled",
                        bracket_side=node.key[0],
                        bracket_round=node.key[1],
                        bracket_slot=node.key[2],
                    ))
                    db.session.flush()
                    changed = True
            elif (existing.red_team_id, existing.blue_team_id) != (state.red, state.blue):
                if has_games:
                    conflicts.append(
                        f"Match {existing.match_number} ({node.title}) has been played by "
                        f"different teams than the bracket now puts there."
                    )
                elif not dry_run:
                    existing.red_team_id, existing.blue_team_id = state.red, state.blue
                    changed = True
        elif existing is not None:
            # The bracket no longer has two teams here (an earlier result was
            # undone), or a grand-final reset is no longer needed.
            if has_games:
                conflicts.append(
                    f"Match {existing.match_number} ({node.title}) has been played, but "
                    f"the bracket no longer has two teams in it."
                )
            elif not dry_run:
                if state.needed:
                    existing.red_team_id = existing.blue_team_id = None
                else:
                    db.session.delete(existing)
                changed = True

    if changed and not dry_run:
        db.session.commit()
    return conflicts


def qualification_unfinished(division):
    return Match.query.filter(
        Match.division == division,
        Match.phase == "qualification",
        Match.status != "complete",
    ).count()


def build_bracket(division, fmt, size, created_by):
    """Seed the bracket from the final qualification standings and lock it."""
    from app.rankings.logic import get_division_rankings

    if fmt not in logic.FORMATS:
        raise BracketError("Choose single or double elimination.")
    if get_config(division) is not None:
        raise BracketError("This division already has a bracket. Reset it first.")
    unfinished = qualification_unfinished(division)
    if unfinished:
        raise BracketError(
            f"{unfinished} qualification series are not finished. The bracket seeds "
            "from the final standings, so finish them (or enter their results on the "
            "admin panel) first."
        )

    standings = get_division_rankings(division)
    if not 2 <= size <= len(standings):
        raise BracketError(f"Teams advancing must be between 2 and {len(standings)}.")

    numbers = [row["team_number"] for row in standings[:size]]
    teams = {t.team_number: t.id for t in Team.query.filter(Team.team_number.in_(numbers))}
    config = BracketConfig(
        division=division,
        format=fmt,
        seeds="\n".join(str(teams[n]) for n in numbers),
        created_by=created_by,
    )
    db.session.add(config)
    db.session.commit()
    sync_division(division)
    return config


def reset_bracket(division):
    """Throw the bracket away so it can be rebuilt. Refused once any bracket
    game has been played: from then on it is a record, not a draft."""
    config = get_config(division)
    if config is None:
        return
    matches = Match.query.filter_by(division=division, phase="elimination").all()
    if any(games_for(m.id) or m.game_started_at for m in matches):
        raise BracketError(
            "Bracket games have already been played, so the bracket can no longer be reset."
        )
    for match in matches:
        db.session.delete(match)
    db.session.delete(config)
    db.session.commit()


def bracket_view(division):
    """Everything the bracket page draws, or None before the bracket is built."""
    config = get_config(division)
    if config is None:
        return None

    matches = _elimination_matches(division)
    seeds, nodes, states = _resolve(config, matches)
    seed_of = {team_id: i + 1 for i, team_id in enumerate(seeds)}
    teams = {t.id: t for t in Team.query.filter(Team.id.in_(seeds))}

    def slot(team_id, winner):
        if team_id is None:
            return {"kind": "tbd", "label": "TBD"}
        if team_id == logic.BYE:
            return {"kind": "bye", "label": "Bye"}
        team = teams.get(team_id)
        return {
            "kind": "team",
            "seed": seed_of.get(team_id),
            "number": team.team_number if team else "?",
            "name": team.name if team else "Unknown team",
            "won": winner == team_id,
        }

    columns = {}
    for node in nodes:
        state = states[node.key]
        if not state.needed:
            continue
        match = matches.get(node.key)
        score = series_tally(match) if match else None
        top_wins = bottom_wins = None
        # No score until a game has been played: "0 / 0" on every series not
        # yet started is noise on the big screen.
        if match and score and games_for(match.id):
            wins = {match.red_team_id: score.red_wins, match.blue_team_id: score.blue_wins}
            top_wins, bottom_wins = wins.get(state.top), wins.get(state.bottom)
        side = node.key[0]
        columns.setdefault((side, node.key[1]), {"title": node.title, "side": side, "series": []})
        columns[(side, node.key[1])]["series"].append({
            "top": slot(state.top, state.winner),
            "bottom": slot(state.bottom, state.winner),
            "top_wins": top_wins,
            "bottom_wins": bottom_wins,
            "walkover": state.walkover,
            "match": match,
            "decided": state.winner is not None,
        })

    sections = []
    for side, label in (("W", "Winners bracket"), ("L", "Losers bracket"), ("GF", "Grand final")):
        cols = [columns[k] for k in sorted(columns) if k[0] == side]
        if cols:
            sections.append({"side": side, "label": label, "columns": cols})

    champ_id = logic.champion(nodes, states)
    champ = teams.get(champ_id) if champ_id else None
    return {
        "config": config,
        "sections": sections,
        "champion": champ,
        "champion_seed": seed_of.get(champ_id),
        "conflicts": sync_division(division, dry_run=True),
    }
