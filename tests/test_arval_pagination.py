import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from arval_full_snapshot import page_next as next_page_url
from arval_cards import car_records, pending_price_records


class ArvalPaginationTests(unittest.TestCase):
    def test_crawl_reaches_end_on_pending_price_only_page(self):
        import arval_full_snapshot as crawl
        first = BeautifulSoup('''<article><h2>Ford Kuga</h2><p>90 875 km</p>
            <b>355 000 Kč</b><a href="/cz/ford/kuga/12345/">Detail vozu</a></article>
            <a href="/pages.script.php?action=cars-pos&amp;pos=20">Dalších 20 nabídek</a>''', 'html.parser')
        terminal = BeautifulSoup('''<div class="cars-list"><div><div class="content-container">
            <h2>DS DS4</h2><p>42 332 km</p><a href="/cz/ds/ds4/95143/">Detail vozu</a>
            <div class="prices"><div class="price">Cenu připravujeme</div></div>
            </div></div></div>''', 'html.parser')
        for soup, complete in [(terminal, True), (BeautifulSoup('<p>Server error</p>', 'html.parser'), False)]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                with patch.object(crawl, 'ARCHIVE', root/'data.json'), patch.object(crawl, 'PARTIAL', root/'partial.json'), patch.object(crawl, 'RESULT', root/'status.json'), patch.object(crawl, 'check_robots', return_value=(None, {})), patch.object(crawl.time, 'sleep'), patch.object(crawl, 'download', side_effect=[(first, crawl.START), (soup, 'https://www.arvalclub.cz/pages.script.php?action=cars-pos&pos=20')]):
                    crawl.run()
                status = json.loads((root/'status.json').read_text())
                self.assertEqual(status['complete'], complete)
                self.assertEqual(status['total_unique'], 1)

    def test_explicit_pending_price_cards_are_separate_from_prices(self):
        html = '''<div class="cars-list"><div><div class="content-container">
          <a href="/cz/ds/ds4/95143/">Detail vozu</a><h2>DS DS4</h2>
          <div>42 332 km | v provozu od: 10/2023</div>
          <div class="prices"><div class="price">Cenu připravujeme</div></div>
        </div></div></div>'''
        base = 'https://www.arvalclub.cz/'
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(car_records(soup, base), [])
        records = pending_price_records(soup, base)
        self.assertEqual([r['id'] for r in records], ['95143'])
        self.assertEqual(records[0]['mileage_km'], 42332)
        for invalid in [html.replace('Cenu připravujeme', 'Chyba serveru'),
                        html.replace('42 332 km', 'Neznámý nájezd'),
                        html.replace('/cz/ds/ds4/95143/', 'https://other.example/cz/ds/ds4/95143/')]:
            self.assertEqual(pending_price_records(BeautifulSoup(invalid, 'html.parser'), base), [])

    def test_next_link_uses_arval_navigation_endpoint(self):
        html = '<a href="/pages.script.php?action=cars-pos&amp;pos=20">Dalších 20 nabídek</a>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(
            next_page_url(soup, "https://www.arvalclub.cz/nabidka-vozu/prodej/"),
            "https://www.arvalclub.cz/pages.script.php?action=cars-pos&pos=20",
        )

    def test_external_url_rejected(self):
        html = '<a href="https://another-site.example/?pg=2">Dalších 20 nabídek</a>'
        self.assertIsNone(next_page_url(BeautifulSoup(html, "html.parser"),
                                         "https://www.arvalclub.cz/nabidka-vozu/"))

    def test_parses_unique_cars_by_stable_id(self):
        html = '''
        <article><h2>Ford Kuga</h2><div>90 875 km | v provozu od: 09/2023</div>
          <strong>355 000 Kč</strong>
          <a href="/cz/ford/kuga-1-5/12345/">Detail vozu</a>
          <a href="/cz/ford/kuga-1-5/12345/">Další odkaz na stejné auto</a></article>
        <article><h2>Toyota RAV4</h2><div>20 000 km | v provozu od: 01/2024</div>
          <strong>500 000 Kč</strong>
          <a href="/cz/toyota/rav4-2-5/23456/">Detail vozu</a></article>
        '''
        records = car_records(BeautifulSoup(html, "html.parser"),
                              "https://www.arvalclub.cz/nabidka-vozu/")
        self.assertEqual([r["id"] for r in records], ["12345", "23456"])
        self.assertEqual(records[0]["mileage_km"], 90875)
        self.assertEqual(records[1]["price_czk_candidates"], [500000])


if __name__ == "__main__":
    unittest.main()

