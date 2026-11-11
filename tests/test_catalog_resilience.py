"""Regression tests for bounded crawl retries and current-day skipping."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_catalog
from check_catalog_freshness import already_imported


class CatalogResilienceTests(unittest.TestCase):
    def test_only_current_day_complete_catalog_skips_backup(self):
        self.assertTrue(already_imported(
            {'scan_date': '2026-11-11', 'total_unique': 607}, '2026-11-11'))
        self.assertFalse(already_imported(
            {'scan_date': '2026-11-10', 'total_unique': 599}, '2026-11-11'))
        self.assertFalse(already_imported(
            {'scan_date': '2026-11-11', 'total_unique': 42}, '2026-11-11'))
        self.assertFalse(already_imported(None, '2026-11-11'))

    def test_rejected_source_is_retried_three_times_but_never_imported(self):
        import os
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                with (patch('run_catalog.api', return_value={
                          'ok': True, 'baseline': {'scan_date': '2026-11-09', 'total_unique': 559}
                      }) as api,
                      patch('run_catalog.run') as crawl,
                      patch('run_catalog.validate', side_effect=ValueError('Invalid pending evidence')) as gate,
                      patch('run_catalog.time.sleep') as delay,
                      patch('sys.argv', ['run_catalog.py', '--mode', 'import'])):
                    with self.assertRaisesRegex(ValueError, 'Invalid pending evidence'):
                        run_catalog.main()
                    self.assertEqual(crawl.call_count, 3)
                    self.assertEqual(gate.call_count, 3)
                    self.assertEqual(delay.call_count, 2)
                    api.assert_called_once_with({'action': 'baseline'})
            finally:
                os.chdir(old)


if __name__ == '__main__':
    unittest.main()
