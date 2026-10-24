# owner: shared / lead
#
# Facts about the event that more than one module needs and that are not
# configuration: they are the same on every laptop and every deployment.

# The event has one division, and every team in it is a high school team.
# The schedule, rankings and bracket pages are keyed by it
# ("/rankings/High_School").
DIVISION = "High School"

# Team numbers start here rather than at 1. Three digits reads as a team
# number at a glance on a pit sign, a match schedule and a bracket, and it
# leaves 1-99 free for anything that needs a reserved number later. The
# registration form and the roster import (seed/teams.py) both number from it.
FIRST_TEAM_NUMBER = 100
