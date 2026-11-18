"""Technology names against the lines that name them."""

import re

from packages.resume_core.technologies import BY_ID, resolve_technology

# A name stands on its own: not inside a longer word or a longer name (Java in JavaScript, C in C++).
BEFORE, AFTER = r'(?<![\w.+#])', r'(?![\w+#])'


def named_in(name, texts):
    """Whether lines name a technology: as it is written (case aside), or by a catalog alias of it. The name is a
    whole word of a line, never a part of one."""
    folded = ' '.join(' '.join(texts).split()).casefold()
    if re.search(BEFORE + re.escape(' '.join(name.split()).casefold()) + AFTER, folded):
        return True
    resolved = resolve_technology(name)
    if resolved.canonical_id is not None:
        return any(re.search(BEFORE + re.escape(alias) + AFTER, folded) for alias in BY_ID[resolved.canonical_id].aliases)
    return False


def source_spelling(name, texts):
    """How the lines spell a name that differs only in case, spaces or punctuation (WinForms for Win Forms), so
    code copies the source's spelling; None when no line spells it so."""
    # One folded character for each character: casefold may give two (ß, a ligature a PDF keeps), and the positions
    # below are positions of the text.
    fold = lambda char: char.casefold()[:1] or char
    target = ''.join(fold(char) for char in name if char.isalnum())
    if len(target) < 2:
        return None
    for text in texts:
        letters = [(fold(char), position) for position, char in enumerate(text) if char.isalnum()]
        flat = ''.join(char for char, _position in letters)
        at = flat.find(target)
        while at >= 0:
            start, end = letters[at][1], letters[at + len(target) - 1][1] + 1
            # Whole words only: the match neither starts nor ends inside a word.
            if (start == 0 or not text[start - 1].isalnum()) and (end == len(text) or not text[end].isalnum()):
                return text[start:end]
            at = flat.find(target, at + 1)
    return None
