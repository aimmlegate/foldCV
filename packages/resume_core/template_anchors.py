"""Mutable authored anchors retain immutable import ledger and issue identity."""

import json

from .models.template_mutations import CoverageAnchorTarget, IssueAnchorTarget, SetAuthoredAnchors
from .templates.compiler import canonical, sha256


def coverage_identity(coverage):
    return coverage.model_dump(mode='json', by_alias=True, exclude={'block_ids'})


def coverage_sequence(project):
    return sha256(canonical([coverage_identity(value) for value in project.import_coverage]))


def coverage_address(project, index, sequence=None):
    return canonical([index, sha256(canonical(coverage_identity(project.import_coverage[index]))),
        sequence or coverage_sequence(project)]).decode()


def coverage_addresses(project):
    # The sequence hash covers the whole ledger; hashing it per entry made saves quadratic in coverage size.
    sequence = coverage_sequence(project)
    return [coverage_address(project, index, sequence) for index in range(len(project.import_coverage))]


def coverage_at(project, address):
    try:
        values = json.loads(address)
        if (not isinstance(values, list) or len(values) != 3 or type(values[0]) is not int
                or not 0 <= values[0] < len(project.import_coverage) or coverage_address(project, values[0]) != address):
            return None
        return project.import_coverage[values[0]]
    except (ValueError, TypeError):
        return None


def coverage_target(project, index, sequence=None):
    return CoverageAnchorTarget(kind='coverage', coverageIndex=index,
        coverageIdentityHash=sha256(canonical(coverage_identity(project.import_coverage[index]))),
        coverageSequenceHash=sequence or coverage_sequence(project))


def issue_target(issue):
    return IssueAnchorTarget(kind='issue', issueId=issue.id, importedFingerprint=issue.imported_fingerprint,
        beforeLifecycleId=issue.lifecycle_id, beforeState=issue.state)


def apply_anchor_steps(project, request, before):
    seen, live = set(), {block.id for block in project.document.blocks()}
    original_issues = {issue.id: issue for issue in before.import_issues}
    current_issues = {issue.id: issue for issue in project.import_issues}
    sequence = None
    for step in request.steps:
        if not isinstance(step, SetAuthoredAnchors):
            continue
        target = step.target
        if isinstance(target, IssueAnchorTarget):
            key = ('issue', target.issue_id)
            old = original_issues.get(target.issue_id)
            if old is None or issue_target(old) != target:
                raise ValueError('stale issue anchor identity or lifecycle')
            current = current_issues[target.issue_id]
        else:
            key = ('coverage', target.coverage_index)
            sequence = sequence or coverage_sequence(before)
            if (target.coverage_index >= len(before.import_coverage)
                    or coverage_target(before, target.coverage_index, sequence) != target):
                raise ValueError('stale coverage anchor identity or sequence')
            old = before.import_coverage[target.coverage_index]
            current = project.import_coverage[target.coverage_index]
        if key in seen or old.block_ids != step.before_block_ids or not set(step.after_block_ids) <= live:
            raise ValueError('duplicate, stale or missing authored anchor')
        seen.add(key)
        current.block_ids = list(step.after_block_ids)


def anchor_steps(before, replacements):
    def mapped(identifiers):
        result = []
        for identifier in identifiers:
            for replacement in replacements.get(identifier, [identifier]):
                if replacement not in result:
                    result.append(replacement)
        return result
    steps = []
    sequence = coverage_sequence(before)
    targets = [(coverage_target(before, index, sequence), value) for index, value in enumerate(before.import_coverage)]
    targets += [(issue_target(issue), issue) for issue in before.import_issues]
    for target, value in targets:
        after = mapped(value.block_ids)
        if after != value.block_ids:
            steps.append(SetAuthoredAnchors(kind='set_authored_anchors', target=target,
                beforeBlockIds=value.block_ids, afterBlockIds=after))
    return steps
