"""Technology names against the lines that name them."""

import re

from packages.resume_core.technologies import BY_ID, resolve_technology


def named_in(name, texts):
    """Whether lines name a technology: as it is written (case aside), or by a catalog alias of it."""
    folded = ' '.join(' '.join(texts).split()).casefold()
    if ' '.join(name.split()).casefold() in folded:
        return True
    resolved = resolve_technology(name)
    if resolved.canonical_id is not None:
        return any(re.search(r'(?<![\w.+#])' + re.escape(alias) + r'(?![\w+#])', folded)
                   for alias in BY_ID[resolved.canonical_id].aliases)
    return False


def source_spelling(name, texts):
    """How the lines spell a name that differs only in case, spaces or punctuation (WinForms for Win Forms), so
    code copies the source's spelling; None when no line spells it so."""
    target = ''.join(char.casefold() for char in name if char.isalnum())
    if len(target) < 2:
        return None
    for text in texts:
        letters = [(char.casefold(), position) for position, char in enumerate(text) if char.isalnum()]
        flat = ''.join(char for char, _position in letters)
        at = flat.find(target)
        while at >= 0:
            start, end = letters[at][1], letters[at + len(target) - 1][1] + 1
            # Whole words only: the match neither starts nor ends inside a word.
            if (start == 0 or not text[start - 1].isalnum()) and (end == len(text) or not text[end].isalnum()):
                return text[start:end]
            at = flat.find(target, at + 1)
    return None
