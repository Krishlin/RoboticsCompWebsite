# owner: Krish S
#
# The elimination bracket as plain data: no Flask, no database. Given how
# many teams are seeded and the format, build_nodes() lays out every series
# in the bracket; given the seeds and which series have been won, resolve()
# works out who is in each one, who has advanced, and who has won it all.
# app/bracket/service.py turns that into Match rows.
#
# Rules (Summit game manual v1.0, T5 and 3.1):
#   - Teams are seeded by qualification rank. Byes, if needed, go to the
#     highest seeds.
#   - Every pairing is a best-of-three series; a tied game is replayed. That
#     happens inside the series (app/series.py), so here a node simply has a
#     winner or does not have one yet. A tie never advances anybody.
#   - In the bracket the lower seed is red. Read here as the worse-ranked
#     team, i.e. the larger seed number.
#   - The manual's bracket is single elimination. Double elimination is also
#     built, because the project plan asks for it per division.
#
# A node is one series, named by (side, round, slot):
#   side "W" winners bracket, "L" losers bracket, "GF" grand final.
# Each node takes its two teams from two Sources: a seed, or the winner or
# loser of an earlier node.

from dataclasses import dataclass, field

# A participant that is not a team: an empty seed, or the "loser" of a series
# that was a bye. Anything paired with a BYE advances without playing.
BYE = "BYE"

SINGLE = "single"
DOUBLE = "double"
FORMATS = (SINGLE, DOUBLE)


@dataclass(frozen=True)
class Source:
    kind: str  # "seed", "winner" or "loser"
    ref: object  # a seed number, or the key of an earlier node


@dataclass(frozen=True)
class Node:
    key: tuple  # (side, round, slot)
    top: Source
    bottom: Source
    title: str


@dataclass
class NodeState:
    node: Node
    top: object = None  # team id, BYE, or None while not known yet
    bottom: object = None
    winner: object = None
    loser: object = None
    walkover: bool = False  # decided by a bye, never played
    needed: bool = True  # False only for a grand-final reset nobody forced
    red: object = None  # team ids, set once both teams are real
    blue: object = None
    extra: dict = field(default_factory=dict)


def bracket_size(team_count: int) -> int:
    """The smallest power of two that holds every team."""
    size = 1
    while size < team_count:
        size *= 2
    return size


def seed_order(size: int) -> list[int]:
    """Seeds in first-round bracket order, so seeds 1 and 2 can only meet in
    the final. For 8: [1, 8, 4, 5, 2, 7, 3, 6] -> 1v8, 4v5, 2v7, 3v6."""
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [seed for s in order for seed in (s, total - s)]
    return order


def _round_title(fmt: str, side: str, round_number: int, winners_rounds: int) -> str:
    if side == "GF":
        return "Grand final" if round_number == 1 else "Grand final (reset)"
    if side == "L":
        return f"Losers round {round_number}"
    from_end = winners_rounds - round_number
    if fmt == DOUBLE:
        return "Winners final" if from_end == 0 else f"Winners round {round_number}"
    if from_end == 0:
        return "Final"
    if from_end == 1:
        return "Semifinals"
    if from_end == 2:
        return "Quarterfinals"
    return f"Round of {2 ** (from_end + 1)}"


def build_nodes(team_count: int, fmt: str = SINGLE) -> list[Node]:
    """Every series in the bracket, in an order where each node comes after
    the nodes it takes teams from."""
    if team_count < 2:
        raise ValueError("A bracket needs at least two teams.")
    if fmt not in FORMATS:
        raise ValueError(f"Unknown bracket format {fmt!r}.")

    size = bracket_size(team_count)
    rounds = size.bit_length() - 1  # winners-bracket rounds
    order = seed_order(size)
    nodes = []

    def add(side, rnd, slot, top, bottom):
        nodes.append(Node((side, rnd, slot), top, bottom, _round_title(fmt, side, rnd, rounds)))

    for slot in range(1, size // 2 + 1):
        add("W", 1, slot, Source("seed", order[2 * slot - 2]), Source("seed", order[2 * slot - 1]))
    for rnd in range(2, rounds + 1):
        for slot in range(1, size // 2**rnd + 1):
            add("W", rnd, slot,
                Source("winner", ("W", rnd - 1, 2 * slot - 1)),
                Source("winner", ("W", rnd - 1, 2 * slot)))

    if fmt == SINGLE:
        return nodes

    if rounds == 1:
        # Two teams: the loser of the only winners-bracket series is the
        # losers-bracket champion by default.
        losers_champion = Source("loser", ("W", 1, 1))
    else:
        # Losers round 1 pairs off the first-round losers. After that the
        # rounds alternate: an even round brings in the losers dropping from
        # the next winners round, an odd round halves the field. The drop-ins
        # are reversed every other round so teams that just played in the
        # winners bracket are not paired again straight away.
        for slot in range(1, size // 4 + 1):
            add("L", 1, slot,
                Source("loser", ("W", 1, 2 * slot - 1)),
                Source("loser", ("W", 1, 2 * slot)))
        for j in range(1, rounds):
            count = size // 2 ** (j + 1)
            for slot in range(1, count + 1):
                drop_slot = count + 1 - slot if j % 2 == 1 else slot
                add("L", 2 * j, slot,
                    Source("winner", ("L", 2 * j - 1, slot)),
                    Source("loser", ("W", j + 1, drop_slot)))
            if j < rounds - 1:
                for slot in range(1, count // 2 + 1):
                    add("L", 2 * j + 1, slot,
                        Source("winner", ("L", 2 * j, 2 * slot - 1)),
                        Source("winner", ("L", 2 * j, 2 * slot)))
        losers_champion = Source("winner", ("L", 2 * (rounds - 1), 1))

    add("GF", 1, 1, Source("winner", ("W", rounds, 1)), losers_champion)
    # Only played if the losers-bracket team wins the first grand final, so
    # that both finalists have lost exactly once.
    add("GF", 2, 1, Source("winner", ("GF", 1, 1)), Source("loser", ("GF", 1, 1)))
    return nodes


def resolve(nodes: list[Node], seeds: list, winners: dict) -> dict:
    """Work out every node's teams and outcome.

    seeds:   team ids in seed order (seed 1 first). Seeds beyond the list are byes.
    winners: node key -> the team id that won that series. Entries for nodes
             whose teams don't match (an upstream result was changed) are
             ignored rather than trusted.
    Returns node key -> NodeState.
    """
    seed_of = {team: i + 1 for i, team in enumerate(seeds)}
    states = {}

    def participant(source):
        if source.kind == "seed":
            return seeds[source.ref - 1] if source.ref <= len(seeds) else BYE
        earlier = states.get(source.ref)
        if earlier is None or not earlier.needed:
            return None
        return earlier.winner if source.kind == "winner" else earlier.loser

    for node in nodes:
        state = NodeState(node)
        states[node.key] = state

        if node.key == ("GF", 2, 1):
            first = states[("GF", 1, 1)]
            # Needed only when the team from the losers bracket (bottom) won
            # the first grand final.
            state.needed = first.winner is not None and first.winner == first.bottom
            if not state.needed:
                continue

        state.top = participant(node.top)
        state.bottom = participant(node.bottom)
        top, bottom = state.top, state.bottom

        if top is None or bottom is None:
            continue
        if top == BYE or bottom == BYE:
            state.walkover = True
            state.winner = bottom if top == BYE else top
            state.loser = BYE
            continue

        # Both real teams. The lower seed (larger number) is red.
        if seed_of.get(top, 0) > seed_of.get(bottom, 0):
            state.red, state.blue = top, bottom
        else:
            state.red, state.blue = bottom, top

        won = winners.get(node.key)
        if won in (top, bottom):
            state.winner = won
            state.loser = bottom if won == top else top

    return states


def champion(nodes: list[Node], states: dict):
    """The bracket winner's team id, or None while it is still being played."""
    if not nodes:
        return None
    if nodes[-1].key[0] != "GF":
        return states[nodes[-1].key].winner  # single elimination: the final
    first = states[("GF", 1, 1)]
    if first.winner is None:
        return None
    reset = states[("GF", 2, 1)]
    return reset.winner if reset.needed else first.winner


def eliminated_place(nodes: list[Node], states: dict) -> dict:
    """team id -> the title of the round each team went out in.

    For the T9 awards (finalists and semifinalists are recognised) and for
    showing a team on the pit page that its day is done.
    """
    out = {}
    for node in nodes:
        state = states[node.key]
        if state.loser in (None, BYE) or not state.needed:
            continue
        if node.key[0] == "W" and nodes[-1].key[0] == "GF":
            continue  # double elimination: a winners-bracket loss is not the end
        if node.key == ("GF", 1, 1) and states[("GF", 2, 1)].needed:
            continue  # the first grand-final loser plays again in the reset
        out[state.loser] = node.title
    return out
