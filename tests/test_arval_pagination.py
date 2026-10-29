import unittest

from bs4 import BeautifulSoup
from arval_full_snapshot import page_next as next_page_url
from arval_cards import car_records


class ArvalPaginationTests(unittest.TestCase):
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

