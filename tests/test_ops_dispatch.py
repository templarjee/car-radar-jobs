import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class OpsContracts(unittest.TestCase):
    def test_catalog_has_correlation_and_preserves_shared_concurrency(self):
        text = (ROOT / '.github/workflows/arval-scheduled.yml').read_text()
        recovery = (ROOT / '.github/workflows/arval-recovery.yml').read_text()
        self.assertIn("format('ops:{0}', inputs.ops_request_id)", text)
        for workflow in (text, recovery):
            self.assertIn('group: arval-catalog-collection', workflow)
            self.assertIn('cancel-in-progress: false', workflow)
        self.assertIn("cron: '17 7 * * *'", text)

    def test_source_dispatch_kind_is_explicit_and_schedule_unchanged(self):
        text = (ROOT / '.github/workflows/market-research-refresh.yml').read_text()
        self.assertIn('options: [onboarding, maintenance]', text)
        self.assertIn('default: maintenance', text)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.kind", text)
        self.assertIn("cron: '7,22,37,52 * * * *'", text)
        self.assertIn("cron: '17 6 * * 1'", text)
        self.assertIn('group: external-market-low-volume-refresh', text)

if __name__ == '__main__':
    unittest.main()
