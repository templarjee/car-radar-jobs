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
                Path("arval_snapshot_status.json").write_text(json.dumps({"complete":True,"finish_reason":"end_of_catalog","path":str(path),"total_unique":100,"page_count":len(data['pages'])}))
                return validate()
            finally:
                os.chdir(old)

    def test_complete_valid_snapshot(self):
        self.assertEqual(self.check(self.fixture()).name,"arval-baseline-2026-10-29.json")

    def test_terminal_pending_price_page_has_explicit_evidence(self):
        data = self.fixture()
        data['pages'][-1]['next_url'] = 'terminal'
        data['pages'].append({'page':6, 'http_status':200, 'count':1, 'new':0,
                              'next_url':None, 'pending_price_ids':['95143']})
        data['pending_price_cars'] = [{'id':'95143', 'title':'DS DS4',
                                      'url':'https://www.arvalclub.cz/cz/ds/ds4/95143/',
                                      'mileage_km':42332, 'price_status':'pending'}]
        self.check(data)
        for mutate in [lambda d:d.pop('pending_price_cars'),
                       lambda d:d['pages'][-1].update(pending_price_ids=[]),
                       lambda d:d['pending_price_cars'][0].update(price_status='unknown'),
                       lambda d:d['pages'][-1].update(next_url='more'),
                       lambda d:d['pages'][-1].update(count=0)]:
            broken = copy.deepcopy(data); mutate(broken)
            with self.assertRaises(ValueError): self.check(broken)

    def test_pending_to_priced_transition_is_not_a_false_snapshot_failure(self):
        data = self.fixture()
        data['pages'][-1]['next_url'] = 'next'
        data['pages'].append({'page':6, 'http_status':200, 'count':1, 'new':0,
                              'next_url':None, 'pending_price_ids':['1']})
        # A priced listing can also have appeared as pending on another page.
        data['pending_price_cars'] = []
        self.check(data)

    def test_pending_repeat_across_pages_is_valid_source_evidence(self):
        data = self.fixture()
        data['pages'][-1]['next_url'] = 'next'
        data['pages'].append({'page':6, 'http_status':200, 'count':1, 'new':0,
                              'next_url':'next', 'pending_price_ids':['95143']})
        data['pages'].append({'page':7, 'http_status':200, 'count':1, 'new':0,
                              'next_url':None, 'pending_price_ids':['95143']})
        data['pending_price_cars'] = [{'id':'95143', 'title':'DS DS4',
                                      'url':'https://www.arvalclub.cz/cz/ds/ds4/95143/',
                                      'mileage_km':42332, 'price_status':'pending'}]
        self.check(data)

    def test_pending_evidence_still_fails_closed_on_missing_or_malformed_record(self):
        data = self.fixture()
        data['pages'][-1]['next_url'] = 'next'
        data['pages'].append({'page':6, 'http_status':200, 'count':1, 'new':0,
                              'next_url':None, 'pending_price_ids':['95143']})
        with self.assertRaisesRegex(ValueError, 'missing='):
            self.check(data)
        data['pending_price_cars'] = [{'id':'95143', 'title':'DS DS4',
                                      'url':'https://www.arvalclub.cz/cz/ds/ds4/95143/?track=x',
                                      'mileage_km':42332, 'price_status':'pending'}]
        with self.assertRaisesRegex(ValueError, 'Malformed pending-price record'):
            self.check(data)

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
