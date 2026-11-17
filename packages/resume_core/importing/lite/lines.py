"""The CV as the lite import reads it: the lines the product's map offers, one by one, under its S refs."""

from packages.resume_core.importing.template_map import Lines, map_evidence


class CV:
    def __init__(self, sources):
        self.sources = list(sources)
        self.source = self.sources[0]
        self.offered = {option.ref: option for option in map_evidence(self.sources)}
        self.table = Lines(self.offered, self.sources)
        self.lines = self.table.lines          # single lines in CV order (EvidenceOption)
        self.by_ref = {line.ref: line for line in self.lines}
        self.order = {line.ref: index for index, line in enumerate(self.lines)}

    def text(self, ref):
        return ' '.join(self.by_ref[ref].text.split())

    def span(self, ref):
        return self.by_ref[ref].span.model_dump(mode='json', by_alias=True)
