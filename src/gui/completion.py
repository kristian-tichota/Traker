import unicodedata

PREFIX, SUBSTRING, SUBSEQUENCE = 0, 1, 2


def normalize(text: str) -> str:
    """Fold a name to the form matching compares: no diacritics, no capitals."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def nocase_fold(text: str) -> str:
    """Fold a name the way the server's COLLATE NOCASE lookup does."""
    return "".join(ch.lower() if "A" <= ch <= "Z" else ch for ch in text)


def is_subsequence(needle: str, haystack: str) -> bool:
    """Do the characters of needle appear in haystack, in order?"""
    position = 0
    for char in needle:
        found = haystack.find(char, position)
        if found < 0:
            return False
        position = found + 1
    return True


def _score(typed_norm: str, name: str):
    """Rank one candidate, or None when it does not match at all."""
    name_norm = normalize(name)
    if name_norm.startswith(typed_norm):
        quality, offset = PREFIX, 0
    else:
        offset = name_norm.find(typed_norm)
        if offset >= 0:
            quality = SUBSTRING
        elif is_subsequence(typed_norm, name_norm):
            quality, offset = SUBSEQUENCE, 0
        else:
            return None
    return quality, offset, len(name), name


def best_match(typed: str, names) -> str | None:
    """The catalog name that best answers what the user typed, or None."""
    typed_norm = normalize(typed)
    if not typed_norm:
        return None
    scored = [score for score in (_score(typed_norm, name) for name in names) if score]
    return min(scored)[-1] if scored else None


def ranked_matches(typed: str, names, prefer=None) -> list:
    """Every name that answers typed, best answer first."""
    typed_norm = normalize(typed)
    keys = []
    for position, name in enumerate(names):
        preferred = 0 if prefer is not None and prefer(name) else 1
        if not typed_norm:
            keys.append((PREFIX, preferred, 0, position, name))
            continue
        scored = _score(typed_norm, name)
        if scored is None:
            continue
        quality, offset, length, tiebreak = scored
        keys.append((quality, preferred, offset, length, tiebreak))
    return [key[-1] for key in sorted(keys)]


def completion_tail(typed: str, name: str) -> str | None:
    """Characters to append so typed becomes name, None when that breaks lookup."""
    if nocase_fold(name[:len(typed)]) != nocase_fold(typed):
        return None
    return name[len(typed):]
