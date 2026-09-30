FOOD = "food"
BEVERAGE = "beverage"
EXERCISE = "exercise"
SUPPLEMENT = "supplement"
MOBILITY = "mobility"
POMODORO = "pomodoro"
PLAN = "plan"
CHORE = "chore"

CATALOGUE_DOMAINS = (FOOD, BEVERAGE, EXERCISE, SUPPLEMENT, MOBILITY)

EVERY_DOMAIN = (*CATALOGUE_DOMAINS, POMODORO, PLAN, CHORE)

TABLE_DOMAINS = {
    **{f"{domain}_{kind}": domain for domain in CATALOGUE_DOMAINS
       for kind in ("items", "logs", "set_components")},
    "training_plans": PLAN,
    "plan_sessions": PLAN,
    "plan_movements": PLAN,
    "chores": CHORE,
    "chore_completions": CHORE,
    "pomodoro_heartbeats": POMODORO,
    "pomodoro_events": POMODORO,
    "pomodoro_dsi_overrides": POMODORO,
}


def domain_of_table(table: str):
    """Return the domain a database table belongs to, or None."""
    return TABLE_DOMAINS.get(table)
