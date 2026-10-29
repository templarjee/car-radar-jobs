import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from validate_arval_snapshot import validate
from arval_db_sync import prepare


class SnapshotGateTests(unittest.TestCase):
    def fixture(self):
        cars = [{"id":str(i),"title":"Ford Kuga","url":f"https://www.arvalclub.cz/cz/ford/kuga/{i}/",
                 "listing_text":"Ford Kuga 95 403 km | v provozu od: 12/2021 499 000 Kč",
                 "price_czk_candidates":[499000],"mileage_km":95403} for i in range(1,101)]
        pages = [{"page":i,"http_status":200,"count":20,"new":20,"next_url":"next" if i<5 else None} for i in range(1,6)]
        return {"complete":True,"finish_reason":"end_of_catalog","total_unique":100,"cars":cars,"pages":pages}

    def check(self, data, baseline=100):
        old=os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                path=Path("data/arval-baseline-2026-10-29.json")
                path.parent.mkdir()
                path.write_text(json.dumps(data))
                Path("baseline.json").write_text(json.dumps({"total_unique":baseline}))
                Path("arval_snapshot_status.json").write_text(json.dumps({"complete":True,"finish_reason":"end_of_catalog","path":str(path),"total_unique":100,"page_count":5}))
                return validate()
            finally:
                os.chdir(old)

    def test_complete_valid_snapshot(self):
        self.assertEqual(self.check(self.fixture()).name,"arval-baseline-2026-10-29.json")

    def test_partial_and_inconsistent_pages_rejected(self):
        for mutate in [lambda d:d.update(complete=False),
                       lambda d:d["pages"][-1].update(next_url="more"),
                       lambda d:d["pages"][2].update(new=19),
                       lambda d:d["pages"][2].update(http_status=503)]:
            data=self.fixture();mutate(data)
            with self.assertRaises(ValueError): self.check(data)

    def test_duplicate_ids_rejected(self):
        data=self.fixture();data['cars'][-1]=copy.deepcopy(data['cars'][0])
        with self.assertRaises(ValueError):self.check(data)

    def test_production_baseline_drop_rejected(self):
        with self.assertRaises(ValueError):self.check(self.fixture(),baseline=608)

    def test_capture_date_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('arval_db_sync.Path.read_text',return_value=json.dumps({'captured_at_utc':'2026-10-30T12:00:00+00:00'})):
                with self.assertRaisesRegex(ValueError,'actual capture date'):
                    prepare(Path('data/arval-baseline-2026-10-29.json'))
