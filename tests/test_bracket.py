"""The elimination bracket: the pure engine, then the whole flow through the
pages - build from final standings, referee results advance it, a tie
replays instead of advancing, and edits that would rewrite history are
refused.
"""

import random
from datetime import datetime

import pytest

from app.bracket import logic
from app.bracket.service import get_config, seeds_for
from app.db import db
from app.match_state import series_tally
from app.models import Match, MatchResult, Team
from tests.conftest import _build, head_ref_auth, staff_auth

STAFF = staff_auth(name="Ref Ana")
HEAD = head_ref_auth()


# --- the engine ------------------------------------------------------------------

def test_seed_order_keeps_top_seeds_apart():
    assert logic.seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    order = logic.seed_order(16)
    # Seeds 1 and 2 are in opposite halves, so they can only meet in the final.
    assert order.index(1) < 8 <= order.index(2)


def test_byes_go_to_the_highest_seeds_and_lower_seed_is_red():
    nodes = logic.build_nodes(6, logic.SINGLE)
    states = logic.resolve(nodes, ["s1", "s2", "s3", "s4", "s5", "s6"], {})
    first_round = [states[n.key] for n in nodes if n.key[:2] == ("W", 1)]
    walkovers = sorted(s.winner for s in first_round if s.walkover)
    assert walkovers == ["s1", "s2"]
    played = {(s.red, s.blue) for s in first_round if not s.walkover}
    assert played == {("s5", "s4"), ("s6", "s3")}


def test_titles_and_sizes():
    single = logic.build_nodes(8, logic.SINGLE)
    assert next(n.title for n in single if n.key[1] == 1) == "Quarterfinals"
    assert single[-1].title == "Final"
    double = logic.build_nodes(8, logic.DOUBLE)
    sides = [n.key[0] for n in double]
    assert sides.count("W") == 7 and sides.count("L") == 6 and sides.count("GF") == 2


def test_grand_final_reset_only_when_the_losers_bracket_team_wins():
    nodes = logic.build_nodes(2, logic.DOUBLE)
    winners = {("W", 1, 1): "a"}
    states = logic.resolve(nodes, ["a", "b"], winners)
    gf = states[("GF", 1, 1)]
    assert (gf.top, gf.bottom) == ("a", "b")

    states = logic.resolve(nodes, ["a", "b"], {**winners, ("GF", 1, 1): "a"})
    assert not states[("GF", 2, 1)].needed
    assert logic.champion(nodes, states) == "a"

    states = logic.resolve(nodes, ["a", "b"], {**winners, ("GF", 1, 1): "b"})
    assert states[("GF", 2, 1)].needed
    assert logic.champion(nodes, states) is None
    states = logic.resolve(nodes, ["a", "b"], {**winners, ("GF", 1, 1): "b", ("GF", 2, 1): "b"})
    assert logic.champion(nodes, states) == "b"


@pytest.mark.parametrize("fmt", logic.FORMATS)
@pytest.mark.parametrize("count", [2, 3, 5, 6, 8, 11, 16, 24])
def test_random_brackets_always_finish_with_the_right_number_of_losses(fmt, count):
    rng = random.Random(count)
    for _ in range(20):
        nodes = logic.build_nodes(count, fmt)
        seeds = list(range(1, count + 1))
        winners, losses = {}, dict.fromkeys(seeds, 0)
        while True:
            states = logic.resolve(nodes, seeds, winners)
            champ = logic.champion(nodes, states)
            if champ is not None:
                break
            ready = [s for s in states.values() if s.needed and s.red and s.winner is None]
            playing = [t for s in ready for t in (s.red, s.blue)]
            assert len(playing) == len(set(playing)), "a team is due in two series at once"
            state = rng.choice(ready)
            won = rng.choice([state.red, state.blue])
            winners[state.node.key] = won
            losses[state.blue if won == state.red else state.red] += 1
        out_after = 1 if fmt == logic.SINGLE else 2
        assert all(losses[t] == out_after for t in seeds if t != champ)
        assert losses[champ] < out_after or fmt == logic.DOUBLE


# --- through the pages -------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    return _build(tmp_path, REGISTRATION_ONLY=False)


@pytest.fixture
def client(app):
    return app.test_client()


def _finish(match, *outcomes):
    for number, outcome in enumerate(outcomes, start=1):
        db.session.add(MatchResult(
            match_id=match.id, game_number=number, outcome=outcome,
            red_final_zone="Plateau", blue_final_zone="Ring-out", submitted_by="seed",
        ))
    match.status = "complete"


@pytest.fixture
def six_teams_after_quals(app):
    """Six teams; every qualification series played."""
    with app.app_context():
        teams = []
        for number in range(101, 107):
            team = Team(
                team_number=number, name=f"Team {number}", affiliation="School",
                division="High School", students="A", adult_name="Coach",
                adult_email=f"c{number}@example.org", checked_in=True,
            )
            db.session.add(team)
            teams.append(team)
        db.session.flush()
        pairs = [(0, 1), (2, 3), (4, 5), (0, 2), (1, 4), (3, 5)]
        for i, (r, b) in enumerate(pairs, start=1):
            match = Match(
                match_number=i, phase="qualification", division="High School",
                arena=f"Arena {1 + i % 2}", scheduled_time=datetime(2026, 10, 24, 10, 0),
                red_team_id=teams[r].id, blue_team_id=teams[b].id,
            )
            db.session.add(match)
            db.session.flush()
            _finish(match, "red", "red")
        db.session.commit()


def _seeds(app):
    with app.app_context():
        return seeds_for(get_config("High School"))


def _elim(app, side, rnd, slot):
    with app.app_context():
        match = Match.query.filter_by(
            phase="elimination", bracket_side=side, bracket_round=rnd, bracket_slot=slot
        ).first()
        if match is None:
            return None
        db.session.expunge(match)
        return match


def _play(client, match_id, *outcomes):
    for number, outcome in enumerate(outcomes, start=1):
        resp = client.post(f"/referee/submit/{match_id}", headers=STAFF, data={
            "game_number": str(number), "outcome": outcome,
            "red_final_zone": "Plateau", "blue_final_zone": "Edge Band",
            "win_time_seconds": "30" if outcome in ("red", "blue") else "",
        })
        assert resp.status_code == 302, resp.get_data(as_text=True)


def test_single_elimination_from_build_to_champion(app, client, six_teams_after_quals):
    assert "built from the final qualification" in client.get("/bracket/High_School").get_data(as_text=True)
    assert client.get("/bracket/High_School/manage", headers=STAFF).status_code == 401

    resp = client.post("/bracket/High_School/build", data={"format": "single", "size": "6"}, headers=HEAD)
    assert resp.status_code == 302
    seeds = _seeds(app)
    from app.rankings.logic import get_division_rankings

    with app.app_context():
        standings = get_division_rankings("High School")
        by_number = {t.team_number: t.id for t in Team.query}
        assert seeds == [by_number[r["team_number"]] for r in standings]
        # Seeds 1 and 2 have byes, so only two first-round series exist.
        assert Match.query.filter_by(phase="elimination").count() == 2

    # 4 v 5: the lower seed (5) is red.
    qf = _elim(app, "W", 1, 2)
    assert (qf.red_team_id, qf.blue_team_id) == (seeds[4], seeds[3])

    # A tie advances nobody: it is replayed as the next game.
    _play(client, qf.id, "tie")
    with app.app_context():
        assert series_tally(db.session.get(Match, qf.id)).winner is None
        assert _elim(app, "W", 2, 1) is None
    client.post(f"/referee/submit/{qf.id}", headers=STAFF, data={
        "game_number": "2", "outcome": "red", "red_final_zone": "Plateau", "blue_final_zone": "Ring-out",
    })
    client.post(f"/referee/submit/{qf.id}", headers=STAFF, data={
        "game_number": "3", "outcome": "red", "red_final_zone": "Plateau", "blue_final_zone": "Ring-out",
    })

    # Seed 5 advanced to meet seed 1, and is red again as the lower seed.
    sf1 = _elim(app, "W", 2, 1)
    assert sf1 is not None
    assert (sf1.red_team_id, sf1.blue_team_id) == (seeds[4], seeds[0])
    assert sf1.arena.startswith("Arena")

    qf2 = _elim(app, "W", 1, 4)  # 3 v 6
    _play(client, qf2.id, "blue", "blue")
    sf2 = _elim(app, "W", 2, 2)
    assert (sf2.red_team_id, sf2.blue_team_id) == (seeds[2], seeds[1])

    _play(client, sf1.id, "blue", "blue")
    _play(client, sf2.id, "red", "blue", "red")
    final = _elim(app, "W", 3, 1)
    assert (final.red_team_id, final.blue_team_id) == (seeds[2], seeds[0])

    # The final is on a referee screen.
    arena_page = client.get(f"/referee/arena/{final.arena.replace(' ', '_')}", headers=STAFF)
    assert f"Match {final.match_number}" in arena_page.get_data(as_text=True)

    _play(client, final.id, "blue", "red", "blue")
    page = client.get("/bracket/High_School").get_data(as_text=True)
    with app.app_context():
        champion = db.session.get(Team, seeds[0])
        assert f"Champion: {champion.team_number} {champion.name}" in page

    # From here the bracket is a record: no reset, and no edit that would
    # change who advanced from a series that later series were built on.
    client.post("/bracket/High_School/reset", headers=HEAD)
    with app.app_context():
        assert get_config("High School") is not None
        game_id = MatchResult.query.filter_by(match_id=qf2.id, game_number=1).one().id
    resp = client.post(f"/admin/edit/{qf2.id}", headers=HEAD, data={
        "game_id": game_id, "outcome": "red", "red_final_zone": "Plateau",
        "blue_final_zone": "Ring-out", "win_time_seconds": "",
    })
    assert resp.status_code == 409
    assert "Not saved" in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(MatchResult, game_id).outcome == "blue"


def test_build_refused_until_qualification_is_finished(app, client, six_teams_after_quals):
    with app.app_context():
        teams = Team.query.all()
        db.session.add(Match(
            match_number=99, phase="qualification", division="High School", arena="Arena 1",
            red_team_id=teams[0].id, blue_team_id=teams[1].id,
        ))
        db.session.commit()
    client.post("/bracket/High_School/build", data={"format": "single", "size": "4"}, headers=HEAD)
    with app.app_context():
        assert get_config("High School") is None
    page = client.get("/bracket/High_School/manage", headers=HEAD).get_data(as_text=True)
    assert "1 qualification series are not finished" in page


def test_reset_allowed_before_any_bracket_game(app, client, six_teams_after_quals):
    client.post("/bracket/High_School/build", data={"format": "single", "size": "4"}, headers=HEAD)
    client.post("/bracket/High_School/reset", headers=HEAD)
    with app.app_context():
        assert get_config("High School") is None
        assert Match.query.filter_by(phase="elimination").count() == 0


def test_double_elimination_plays_through_the_pages(app, client, six_teams_after_quals):
    resp = client.post("/bracket/High_School/build", data={"format": "double", "size": "5"}, headers=HEAD)
    assert resp.status_code == 302
    rng = random.Random(5)
    for _ in range(40):
        with app.app_context():
            waiting = Match.query.filter(
                Match.phase == "elimination", Match.status != "complete",
                Match.red_team_id.isnot(None), Match.blue_team_id.isnot(None),
            ).all()
            ids = [m.id for m in waiting]
        if not ids:
            break
        winner = rng.choice(["red", "blue"])
        _play(client, rng.choice(ids), winner, winner)
    page = client.get("/bracket/High_School").get_data(as_text=True)
    assert "Champion:" in page
    assert "Losers bracket" in page and "Grand final" in page
