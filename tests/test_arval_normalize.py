import unittest
from arval_normalize import normalize, normalize_snapshot

class NormalizeTests(unittest.TestCase):
    def item(self, number, brand, slug, title, raw, prices):
        return {"id":number, "title":title, "url":f"https://www.arvalclub.cz/cz/{brand}/{slug}/{number}/",
                "listing_text":raw, "price_czk_candidates":prices, "mileage_km":95403,
                "in_service_since":"12/2021"}

    def test_kuga(self):
        raw="Ford Kuga KUGA 2.5DT HEV ST-Line X AT 5d 95 403 km | v provozu od: 12/2021 499 000 Kč vč. DPH Detail vozu Hybridní vozidlo, Převodovka automatická 140 kW (190 PS)"
        c=normalize(self.item("92947","ford","kuga-2-5dt-hev-st-line-x-at-5d","Ford Kuga",raw,[499000]))
        self.assertEqual((c["powertrain"],c["gearbox"],c["drive"]),("HEV","automatic","unknown"))
        self.assertEqual(c["variant_raw"], "KUGA 2.5DT HEV ST-Line X AT 5d")
        self.assertEqual(c["power_kw_raw"],140)

    def test_hybrid_badged_benzin(self):
        raw="Toyota RAV4 2019 RAV4 2.5 Hybrid Comfort 4WD AT 103 248 km | v provozu od: 04/2023 739 000 Kč vč. DPH Detail vozu Benzín, Převodovka automatická 163 kW (222 PS)"
        c=normalize(self.item("93076","toyota","rav4-2-5-hybrid-comfort-4wd-at","Toyota RAV4 2019",raw,[739000]))
        self.assertEqual((c["fuel_raw"],c["powertrain"],c["drive"]),("Benzín","HEV","AWD"))

    def test_discount(self):
        raw="Sleva 23 % Hyundai Bayon Bayon 1.2i Comfort Club 5d 113 528 km | v provozu od: 03/2024 279 000 Kč 215 000 Kč vč. DPH Detail vozu Benzín, Převodovka manuální 62 kW (84 PS)"
        c=normalize(self.item("89760","hyundai","bayon-1-2i-comfort-club-5d","Hyundai Bayon",raw,[279000,215000]))
        self.assertEqual((c["amount_czk"],c["previous_displayed_amount_czk"],c["advertised_discount_pct"]),(215000,279000,23))

    def test_mild_hybrid_abbreviation_is_not_full_hybrid(self):
        raw = "Hyundai i30 i30 1.5 T-GDI M.Hyb Smart kom. 95 403 km | v provozu od: 12/2021 499 000 Kč vč. DPH Detail vozu Benzín, Převodovka automatická 118 kW (160 PS)"
        car = self.item("93528", "hyundai", "i30-1-5-t-gdi-m-hyb-smart-kom", "Hyundai i30", raw, [499000])
        result = normalize(car)
        self.assertEqual(result["powertrain"], "MHEV")
        self.assertEqual(result["engine_power_scope"], "hybrid_scope_unverified")
        self.assertEqual(result["engine_family"], "T-GDI")
        self.assertEqual(result["listing_text"], raw)

    def test_lease_no_purchasing_price(self):
        raw="Operativní leasing Ford Kuga '19 KUGA 2.5HEV ST-Line X AWD AT 40 234 km | v provozu od: 01/2025 10 307 Kč vč. DPH/měsíčně Detail vozu Benzín, Převodovka automatická 111 kW (151 PS)"
        c=normalize(self.item("94337","ford","kuga-2-5hev-st-line-x-awd-at","Ford Kuga '19",raw,[10307]))
        self.assertEqual((c["offer_type"],c["amount_unit"],c["powertrain"]),("operating_lease","CZK_per_month","HEV"))

    def test_missing_catalog_heading_preserves_visible_variant(self):
        raw = "Jum.4-35 L4H2 2.2BHDi 140 S&S 118 558 km | v provozu od: 09/2023 459 000 Kč vč. DPH Detail vozu Nafta, Převodovka manuální 103 kW (140 PS)"
        car = self.item("94359", "-", "jum-4-35-l4h2-2-2bhdi-140-s-amp-amp-s", "", raw, [459000])
        result = normalize(car)
        self.assertEqual(result["title"], "Jum.4-35 L4H2 2.2BHDi 140 S&S")
        self.assertEqual(result["brand_slug"], "-")
        self.assertEqual(result["power_kw_raw"], 103)

    def test_incomplete_and_mismatch_fail(self):
        with self.assertRaises(ValueError): normalize_snapshot({"complete":False,"cars":[]})
        c=self.item("1","ford","kuga","Ford Kuga","", [123456])
        c["id"]="2"
        with self.assertRaises(ValueError): normalize(c)

if __name__ == "__main__":
    unittest.main()


