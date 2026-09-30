from src.domain.tables import (BEVERAGE, CHORE, EVERY_DOMAIN, EXERCISE, FOOD, MOBILITY,
                               PLAN, POMODORO, SUPPLEMENT, TABLE_DOMAINS, domain_of_table)

__all__ = ["BEVERAGE", "CHORE", "EVERY_DOMAIN", "EXERCISE", "FOOD", "MOBILITY", "PLAN",
           "POMODORO", "SUPPLEMENT", "TABLE_DOMAINS", "TAB_DOMAINS", "domain_of_table",
           "domains_for_tab", "tabs_reading"]

TAB_DOMAINS = {
    "pomodoro": (POMODORO, CHORE),
    "food": (FOOD, EXERCISE, MOBILITY),
    "beverages": (BEVERAGE,),
    "exercise": (EXERCISE,),
    "supplements": (SUPPLEMENT,),
    "mobility": (MOBILITY,),
    "food_graphs": (FOOD, EXERCISE, MOBILITY),
    "exercise_graphs": (EXERCISE,),
    "heatmap": (EXERCISE, MOBILITY),
    "caffeine_graph": (BEVERAGE,),
    "supplement_graphs": (SUPPLEMENT,),
    "plans": (PLAN, EXERCISE),
    "chores": (CHORE,),
}


def domains_for_tab(registry_key: str) -> tuple:
    """Return the domains a tab reads."""
    return TAB_DOMAINS.get(registry_key, EVERY_DOMAIN)


def tabs_reading(domains) -> set:
    """Return every registry key that reads any of domains."""
    wanted = set(domains)
    return {key for key, read in TAB_DOMAINS.items() if wanted & set(read)}
