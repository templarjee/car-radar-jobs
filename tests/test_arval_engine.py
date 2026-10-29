import unittest

from arval_engine import extract_engine
from arval_normalize import normalize


class EngineTests(unittest.TestCase):
    def e(self, variant, kw, powertrain="unknown", fuel="Benzín"):
        return extract_engine(variant, kw, powertrain, fuel)

    def test_scala_85_differs_from_81(self):
        a = self.e("Scala 1.0 TSI 85 Selection", 85)
        b = self.e("Scala 1.0 TSI 81 Style", 81)
        self.assertEqual(a["engine_variant_normalized"], "1.0 TSI 85 kW")
        self.assertNotEqual(a["engine_variant_key"], b["engine_variant_key"])
        self.assertEqual(a["engine_confidence"], "high")

    def test_tsi_110_with_spaced_variant(self):
        v = self.e("Karoq 1.5 TSI 110 Style Exclus", 110)
        self.assertEqual((v["engine_family"], v["engine_displacement_l"]), ("TSI", 1.5))
        self.assertEqual(v["engine_variant_normalized"], "1.5 TSI 110 kW")

    def test_tsi_decimal_comma(self):
        v = self.e("Golf 1,5 TSI 96 Life 5d", 96)
        self.assertEqual(v["engine_variant_normalized"], "1.5 TSI 96 kW")

    def test_tsi_no_space(self):
        v = self.e("Kamiq 1.0TSI 85 First Edition", 85)
        self.assertEqual(v["engine_family"], "TSI")
        self.assertEqual(v["engine_displacement_l"], 1)

    def test_tdi_fuel(self):
        v = self.e("Superb 2.0TDI 147 4x4", 147, fuel="Nafta")
        self.assertEqual(v["engine_family"], "TDI")
        self.assertEqual(v["engine_confidence"], "high")

    def test_source_mislabels_tiguan_tsi_as_diesel(self):
        v = self.e("Tiguan 1.5 TSI 110 Life AT", 110, fuel="Nafta")
        self.assertEqual(v["engine_variant_normalized"], "1.5 TSI 110 kW")
        self.assertEqual(v["engine_confidence"], "conflict")
        self.assertIsNone(v["engine_variant_key"])
        self.assertIn("fuel_label_conflicts_engine_family", v["engine_evidence"]["conflicts"])
        self.assertEqual(v["engine_evidence"]["fuel_raw"], "Nafta")

    def test_ford_kuga_hybrid_power_is_ambiguous(self):
        v = self.e("KUGA 2.5DT HEV ST-Line X AT 5d", 140, "HEV", "Hybridní vozidlo")
        self.assertEqual(v["engine_variant_normalized"], "2.5 HEV 140 kW")
        self.assertIsNone(v["engine_variant_key"])
        self.assertEqual(v["engine_power_scope"], "hybrid_scope_unverified")

    def test_tfsi_180(self):
        v = self.e("A4 2.0 TFSI 180 S line", 180)
        self.assertEqual(v["engine_variant_normalized"], "2.0 TFSI 180 kW")

    def test_crdi_attached(self):
        v = self.e("i30 kom.1.6CRDi 115 Smart AT", 85, fuel="Nafta")
        self.assertEqual(v["engine_variant_normalized"], "1.6 CRDI 85 kW")

    def test_tgdi(self):
        v = self.e("i30 kom.1.0TGDI 120 Comfort", 88)
        self.assertEqual(v["engine_variant_normalized"], "1.0 T-GDI 88 kW")

    def test_bhdi_attached(self):
        v = self.e("Boxer 2.2BlueHDi 140", 103, fuel="Nafta")
        self.assertEqual(v["engine_variant_normalized"], "2.2 BLUEHDI 103 kW")

    def test_hyphenated_specific_family_does_not_conflict_with_its_suffix(self):
        for text, family in [("Ceed SW 1.5 T-GDI 118 Fresh", "T-GDI"),
                             ("Golf 1.5 e-TSI Life", "E-TSI"),
                             ("i30 kom.1.0T-GDI 74 Comfort", "T-GDI")]:
            with self.subTest(text=text):
                result = self.e(text, 118)
                self.assertEqual(result["engine_family"], family)
                self.assertEqual(result["engine_confidence"], "high")
                self.assertEqual(result["engine_evidence"]["conflicts"], [])

    def test_independent_families_and_fuel_conflict_remain_conflicts(self):
        for text in ["Golf 1.5 e-TSI TDI", "Ceed 1.5 T-GDI GDI"]:
            self.assertEqual(self.e(text, 118)["engine_confidence"], "conflict")
        self.assertEqual(self.e("Ceed 1.5 T-GDI", 118, fuel="Nafta")["engine_confidence"], "conflict")

    def test_hybrid_explicit_family_keeps_powertrain_separate(self):
        a = self.e("Golf 1.5 TSI PHEV", 150, "PHEV")
        b = self.e("Golf 1.5 TSI", 150, "unknown")
        self.assertNotEqual(a["engine_variant_key"], b["engine_variant_key"])
        self.assertEqual(a["engine_power_scope"], "hybrid_scope_unverified")
        self.assertEqual(a["engine_confidence"], "medium")

    def test_no_family_avoids_false_engine_id(self):
        v = self.e("EV6 77kWh 168 Earth Pro AT", 168, "EV", "Elektromobil")
        self.assertIsNone(v["engine_variant_key"])
        self.assertIsNone(v["engine_variant_normalized"])

    def test_missing_kw_cannot_establish_engine_key(self):
        v = self.e("Scala 1.0 TSI Selection", None)
        self.assertIsNone(v["engine_variant_key"])
        self.assertEqual(v["engine_variant_normalized"], "1.0 TSI")

    def test_integration_preserves_raw_fields(self):
        raw = "Volkswagen Tiguan Tiguan 1.5 TSI 110 Life AT 95 403 km | v provozu od: 12/2021 499 000 Kč vč. DPH Detail vozu Nafta, Převodovka automatická 110 kW (150 PS)"
        car = {"id": "91481", "title": "Volkswagen Tiguan",
               "url": "https://www.arvalclub.cz/cz/volkswagen/tiguan-1-5-tsi-110-life-at/91481/",
               "listing_text": raw, "price_czk_candidates": [499000],
               "mileage_km": 95403, "in_service_since": "12/2021"}
        result = normalize(car)
        self.assertEqual(result["engine_family"], "TSI")
        self.assertEqual(result["engine_variant_normalized"], "1.5 TSI 110 kW")
        self.assertEqual(result["fuel_raw"], "Nafta")
        self.assertEqual(result["engine_confidence"], "conflict")
        self.assertEqual(result["listing_text"], raw)


if __name__ == "__main__":
    unittest.main()


