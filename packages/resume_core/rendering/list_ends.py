"""Closing marks of list items (D152): a semicolon after each item and a full stop after the last item of a list, as
Russian lists are written. The screen draws the same marks (apps/web/src/rich/list-ends.ts); neither puts them into
the text, so an item that closes itself keeps its own mark."""

ITEM_END = ';'
LAST_END = '.'
CLOSING = '.;!?:…'
LISTS = ('bullet_list', 'numbered_list')


def list_end(text, last):
    """The mark after a list item's text: none for an empty item or one that closes itself."""
    stripped = text.rstrip()
    if not stripped or stripped[-1] in CLOSING:
        return None
    return LAST_END if last else ITEM_END


def list_runs(blocks):
    """Neighbouring list blocks of one type among sibling blocks, each run in order."""
    run = []
    for block in blocks:
        if block.type in LISTS and (not run or run[-1].type == block.type):
            run.append(block)
            continue
        if run:
            yield run
        run = [block] if block.type in LISTS else []
    if run:
        yield run
