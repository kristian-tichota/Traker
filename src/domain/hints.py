from itertools import product

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def letters_of(written, fallback=LETTERS) -> str:
    """Return the distinct letters written, lowercased, or fallback where fewer than two."""
    found = "".join(dict.fromkeys(c for c in str(written or "").lower() if c in LETTERS))
    return found if len(found) > 1 else fallback


def labels(count, letters) -> list:
    """Return count labels over letters, none the start of another, the shortest first."""
    letters = str(letters)
    if count <= 0 or not letters:
        return []
    if count <= len(letters) or len(letters) < 2:
        return list(letters[:count])
    width = 1
    while len(letters) ** (width + 1) < count:
        width += 1
    stems = ["".join(chars) for chars in product(letters, repeat=width)]
    grown = -(-(count - len(stems)) // (len(letters) - 1))
    kept = stems[:len(stems) - grown]
    longer = [stem + letter for stem in stems[len(kept):] for letter in letters]
    return kept + longer[:count - len(kept)]
