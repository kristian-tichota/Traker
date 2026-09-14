FOOD = "food"
BEVERAGE = "beverage"
EXERCISE = "exercise"
SUPPLEMENT = "supplement"
MOBILITY = "mobility"
POMODORO = "pomodoro"
PLAN = "plan"
CHORE = "chore"

EVERY_DOMAIN = (FOOD, BEVERAGE, EXERCISE, SUPPLEMENT, MOBILITY, POMODORO,
                PLAN, CHORE)

TABLE_DOMAINS = {
    "food_items": FOOD,
    "food_logs": FOOD,
    "beverage_items": BEVERAGE,
    "beverage_logs": BEVERAGE,
    "exercise_items": EXERCISE,
    "exercise_logs": EXERCISE,
    "supplement_items": SUPPLEMENT,
    "supplement_logs": SUPPLEMENT,
    "mobility_items": MOBILITY,
    "mobility_logs": MOBILITY,
    "food_set_components": FOOD,
    "beverage_set_components": BEVERAGE,
    "exercise_set_components": EXERCISE,
    "supplement_set_components": SUPPLEMENT,
    "mobility_set_components": MOBILITY,
    "training_plans": PLAN,
    "plan_sessions": PLAN,
    "plan_movements": PLAN,
    "chores": CHORE,
    "chore_completions": CHORE,
    "pomodoro_heartbeats": POMODORO,
    "pomodoro_events": POMODORO,
    "pomodoro_dsi_overrides": POMODORO,
}

TAB_DOMAINS = {
    "pomodoro": (POMODORO, CHORE),
    "food": (FOOD, EXERCISE, MOBILITY),
    "beverages": (BEVERAGE,),
    "exercise": (EXERCISE,),
    "supplements": (SUPPLEMENT,),
    "mobility": (MOBILITY,),
    "food_graphs": (FOOD,),
    "exercise_graphs": (EXERCISE,),
    "heatmap": (EXERCISE, MOBILITY),
    "caffeine_graph": (BEVERAGE,),
    "supplement_graphs": (SUPPLEMENT,),
    "plans": (PLAN, EXERCISE),
    "chores": (CHORE,),
}


def domain_of_table(table: str):
    """Return the domain a database table belongs to, or None."""
    return TABLE_DOMAINS.get(table)


def domains_for_tab(registry_key: str) -> tuple:
    """Return the domains a tab reads."""
    return TAB_DOMAINS.get(registry_key, EVERY_DOMAIN)


def tabs_reading(domains) -> set:
    """Return every registry key that reads any of domains."""
    wanted = set(domains)
    return {key for key, read in TAB_DOMAINS.items() if wanted & set(read)}
