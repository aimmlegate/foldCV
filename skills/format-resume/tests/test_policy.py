"""Exercise source loss, selection errors, and date overlap with synthetic data."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from archive import prepare
from check_archive import check
from finalize import finalize
from policy import estimate, old_job, union_months


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        source = root / 'input.txt'
        source.write_text('Alex Example\n\nAcme, Python developer\n\nJanuary 2020 — December 2022\n\nPython; reduced time from 8 to 2 seconds.')
        self.folder = root / 'case'
        prepare(source, self.folder, '2026-10-10')
        self.path = self.folder / 'archive.json'
        self.archive = json.loads(self.path.read_text())
        self.archive['classifications'] = {
            'u0001': {'category': 'identity', 'importance': 'essential', 'job_id': None},
            'u0002': {'category': 'job_header', 'importance': 'essential', 'job_id': 'acme'},
            'u0003': {'category': 'period', 'importance': 'essential', 'job_id': 'acme'},
            'u0004': {'category': 'result', 'importance': 'essential', 'job_id': 'acme'},
        }
        def s(text, ref):
            return {'text': text, 'sources': [ref]}
        job = {'id': 'acme', 'company': s('Acme', 'u0002'), 'role': s('Python developer', 'u0002'),
               'period': s('January 2020 — December 2022', 'u0003'), 'start': '2020-01', 'end': '2022-12',
               'observed_at': None, 'observed_sources': [], 'technologies': [{'name': 'Python', 'sources': ['u0004']}]}
        self.archive['jobs'] = [job]
        self.view = {'template': 'generic-v1', 'candidate': {'name': s('Alex Example', 'u0001'),
                     'title': job['role'], 'summary': s('Reduced time from 8 to 2 seconds using Python.', 'u0004')},
                     'recent_project_ids': ['acme'], 'focus': [{'label': s('Python', 'u0004'), 'icon': None, 'duration': None}],
                     'sidebar': [], 'projects': [{**{k: job[k] for k in ('id', 'company', 'period', 'role')},
                         'stack': s('Python', 'u0004'), 'description': None, 'tasks': [],
                         'results': [s('Reduced time from 8 to 2 seconds.', 'u0004')]}],
                     'earlier_experience': [], 'achievements': [], 'skill_groups': [], 'evidence': {},
                     'review': [], 'omitted': [], 'coverage': {u['id']: {'decision': 'shown', 'reason': ''} for u in self.archive['units']},
                     'archived_technologies': []}
        self.finish()

    def finish(self):
        self.path.write_text(json.dumps(self.archive))
        finalize(self.view, self.archive, self.path)

    def test_valid_case(self):
        result = check(self.view, self.archive, self.path)
        self.assertEqual(result['source_units'], 4)
        self.assertEqual(self.view['focus'][0]['estimate']['months_min'], 36)

    def test_source_and_selection_fail_closed(self):
        mutations = [
            lambda v: v['coverage'].pop('u0004'),
            lambda v: v['projects'].clear(),
            lambda v: v['projects'][0]['results'][0].update(text='Improved speed.'),
            lambda v: v.update(focus=v['focus'] * 9),
            lambda v: v['focus'][0]['duration'].update(text='20 years'),
            lambda v: v.update(archive_sha256='bad'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                view = copy.deepcopy(self.view)
                mutate(view)
                with self.assertRaises(ValueError):
                    check(view, self.archive, self.path)

    def test_missing_source_unit(self):
        self.archive['units'].pop()
        self.finish()
        with self.assertRaisesRegex(ValueError, 'Source units'):
            check(self.view, self.archive, self.path)

    def test_changed_source_bytes(self):
        (self.folder / 'original.txt').write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'Original bytes'):
            check(self.view, self.archive, self.path)

    def test_changed_extraction_in_both_copies(self):
        self.archive['source']['pages'][0]['text'] += '\nInvented statement'
        (self.folder / 'source.json').write_text(json.dumps(self.archive['source']))
        from archive import source_units
        self.archive['units'] = source_units(self.archive['source'])
        self.finish()
        with self.assertRaisesRegex(ValueError, 'fresh source extraction'):
            check(self.view, self.archive, self.path)

    def test_overlapping_months_count_once(self):
        self.assertEqual(union_months([[10, 15], [12, 17], [18, 18], [10, 15]]), 9)
        second = copy.deepcopy(self.archive['jobs'][0])
        second.update(id='second', start='2022-12', end=None, observed_at='2023-03-02', observed_sources=['u0003'])
        self.archive['jobs'].append(second)
        _, calculation = estimate('Python', self.archive)
        self.assertEqual(calculation['months_min'], 39)
        self.assertEqual(calculation['intervals'][-1]['end'], '2023-03-02')

    def test_global_or_undated_technology_has_no_duration(self):
        self.archive['global_technologies'] = [{'name': 'Go', 'sources': ['u0004']}]
        with self.assertRaises(ValueError):
            estimate('Go', self.archive)
        self.archive['jobs'][0]['technologies'][0]['duration_eligible'] = False
        with self.assertRaises(ValueError):
            estimate('Python', self.archive)

    def test_invented_dates_are_rejected(self):
        self.archive['jobs'][0]['start'] = '2019-01'
        self.finish()
        with self.assertRaisesRegex(ValueError, 'normalized start'):
            check(self.view, self.archive, self.path)
        self.archive['jobs'][0]['start'] = '2020-01'
        self.archive['jobs'][0]['technologies'][0]['start'] = '2021-01'
        self.finish()
        with self.assertRaisesRegex(ValueError, 'unsupported subproject date'):
            check(self.view, self.archive, self.path)

    def test_cutoff_and_year_precision(self):
        self.assertTrue(old_job({'end': '2011-09'}, '2026-10-10'))
        self.assertFalse(old_job({'end': '2011-10'}, '2026-10-10'))
        self.assertFalse(old_job({'end': '2011'}, '2026-10-10'))
        self.assertFalse(old_job({'end': None}, '2026-10-10'))
        self.archive['jobs'][0].update(start='2020', end='2021')
        _, calculation = estimate('Python', self.archive)
        self.assertEqual((calculation['months_min'], calculation['months_max']), (2, 24))


if __name__ == '__main__':
    unittest.main()
