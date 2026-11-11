"""Offline deployment contract: keep one idempotent daily catalog workflow.

Exact workflow predicates are intentional fail-closed guards against adding a
date gate. No Actions dispatch, OIDC request or source HTTP is performed.
"""
import ast
from datetime import date, timedelta
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DailyCatalogPolicyTests(unittest.TestCase):
    def test_daily_cron_has_no_calendar_cutoff(self):
        workflow = (ROOT / '.github/workflows/arval-scheduled.yml').read_text()
        crons = re.findall(r"^\s+- cron: '([^']+)'$", workflow, re.M)
        self.assertEqual(crons, ['17 7 * * *', '47 14 * * *', '47 18 * * *'])
        # Resolve the actual configured day/month/weekday fields, including the
        # former cutover dates, weekends, Mondays and a complete future year.
        minute, hour, dom, month, dow = crons[0].split()
        self.assertEqual((minute, hour), ('17', '7'))
        days = [date(2026, 11, n) for n in (3, 4, 5, 7, 8, 9)]
        days += [date(2027, 1, 1) + timedelta(days=n) for n in range(365)]
        for cron in crons:
            self.assertEqual(cron.split()[2:], ['*', '*', '*'])
        for day in days:
            with self.subTest(day=day):
                self.assertTrue(all(field == '*' for field in (dom, month, dow)))
        conditions = re.findall(r'^    if: (.+)$', workflow, re.M)
        self.assertEqual(conditions, ["github.repository == 'templarjee/car-radar-jobs' && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch' && inputs.mode != 'smoke'))"])
        self.assertIn("steps.freshness.outputs.current != 'true'", workflow)
        self.assertIn("run: python check_catalog_freshness.py", workflow)
        self.assertIn('run: python run_catalog.py --mode import', workflow)
        tree = ast.parse((ROOT / 'run_catalog.py').read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        crawl = next(n for n in main.body if isinstance(n, ast.If) and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == 'run' for c in ast.walk(n)))
        self.assertEqual(ast.unparse(crawl.test), "args.mode == 'saved-import'")
        self.assertTrue(any(isinstance(n, ast.For) for n in ast.walk(crawl)))

    def test_single_scheduled_catalog_and_serialized_recovery(self):
        workflows = ROOT / '.github/workflows'
        scheduled = []
        for path in workflows.glob('*.yml'):
            source = path.read_text()
            if 'run_catalog.py' in source:
                self.assertIn('group: arval-catalog-collection', source)
                self.assertIn('cancel-in-progress: false', source)
                self.assertIn("github.ref == 'refs/heads/main'", source)
                if re.search(r'^  schedule:', source, re.M):
                    scheduled.append(path.name)
        self.assertEqual(scheduled, ['arval-scheduled.yml'])
        self.assertFalse((workflows / 'arval-targeted-daily.yml').exists())
        recovery = (workflows / 'arval-recovery.yml').read_text()
        self.assertIn("paths: ['recovery-request.json']", recovery)

    def test_collection_cannot_bypass_full_snapshot_validation(self):
        tree = ast.parse((ROOT / 'run_catalog.py').read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        calls = [n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        validation = next(n.lineno for n in calls if n.func.id == 'validate')
        prepare = next(n.lineno for n in calls if n.func.id == 'prepare')
        ingest = next(n.lineno for n in calls if n.func.id == 'api' and ast.unparse(n.args[0]) == 'payload')
        self.assertLess(validation, prepare)
        self.assertLess(prepare, ingest)

