import unittest
from datetime import date
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
import market_auto_refresh as m
from market_aggregate_adapters import AggregateStat,parse_autohledac_year,SourceParseError

def make_target(brand,model,year):
    return {"brand":brand,"model":model,"year":year,
            "url":f"https://autohledac.cz/znacky/{brand}/{model}/{year}"}
KUGA=make_target("ford","kuga",2021)
O22=make_target("skoda","octavia",2022)
O23=make_target("skoda","octavia",2023)
O24=make_target("skoda","octavia",2024)
def plan(*targets):
    return {"mode":"on_watch_cohort_refresh_v041","kind":"maintenance",
            "budget":4,"daily_budget":8,"ttl_days":6,"active_cohorts":5,"fresh_skipped":1,
            "due_count":len(targets),"targets":list(targets)}
def stat(t,date_text="2026-10-21"):
    return AggregateStat(
        "AutoHledac",t["url"],t["brand"],t["model"],"model_year",
        t["year"],None,None,None,None,None,None,58,
        "median",423000,None,None,date_text,
        "All engines")
def html(t):
    brand="Škoda" if t["brand"]=="skoda" else t["brand"]
    return f"""<html><h1>{brand} {t['model']} {t['year']}: cena a bazar</h1>
      <p>K 21. 10. 2026 je v české inzerci 58 nabídek {brand} {t['model']} {t['year']}
      z 3 inzertních serverů. Mediánová cena je 423 000 Kč.</p></html>""".encode()
class WatchCohortAutoRefreshTests(unittest.TestCase):
    def test_limits_and_dynamic_ids(self):
        self.assertEqual(m.MAX_PAGES,4)
        self.assertEqual(m.DELAY_SECONDS,6)
        self.assertEqual(m.validate_target(O24),("skoda","octavia",2024,O24["url"]))
        self.assertEqual(m.validate_target(make_target("hyundai","tucson",2023))[0],"hyundai")
    def test_reject_site_injection_and_unknown_models(self):
        bad=[
            dict(O22,url="https://evil.invalid/car"),
            dict(O22,year="2022"),
            dict(O22,brand="Skoda"),
            dict(O22,model="../../secret"),
            dict(O22,url=O22["url"]+"?q=1"),
        ]
        for x in bad:
            with self.subTest(bad=x),self.assertRaises(ValueError):
                m.validate_target(x)
    def test_plan_requests_authenticated_api_and_keeps_private_id_out(self):
        with patch.object(m,"rpc",return_value=plan(O22,O23,O24)) as call:
            x=m.fetch_plan()
            self.assertEqual(len(x["targets"]),3)
            call.assert_called_once_with("plan")
            self.assertNotIn("user_id",str(x))
            self.assertNotIn("arval_id",str(x))
    def test_private_planner_cannot_silently_revert_to_legacy_crawler(self):
        fixture=plan(O22)
        with patch.object(m,"rpc",return_value={**fixture,"mode":"dynamic_watchlist_cohorts"}):
            with self.assertRaisesRegex(ValueError,"planner version"):
                m.fetch_plan()
        with patch.object(m,"rpc",return_value={**fixture,"daily_budget":400}):
            with self.assertRaisesRegex(ValueError,"daily cap"):
                m.fetch_plan()
    def test_no_stale_oversized_plan_accepted(self):
        with patch.object(m,"rpc",return_value=plan(O22,O23,O24,KUGA,KUGA)):
            with self.assertRaises(ValueError):
                m.fetch_plan()
        with patch.object(m,"rpc",return_value=plan(O22,O22)):
            with self.assertRaises(ValueError):
                m.fetch_plan()
    def test_source_year_is_verified_and_not_claimed_motor_specific(self):
        t=O22
        x=m.validate_stat(stat(t),brand=t["brand"],model=t["model"],
                          year=t["year"],url=t["url"],as_of=date(2026,10,21))
        self.assertEqual(x["sample_n"],58)
        self.assertFalse(x["has_motor_filter"])
        self.assertFalse(x["estimated_independent_ads"])
        self.assertEqual(x["source_data_date"],"2026-10-21")
    def test_wrong_source_year_or_future_date_is_rejected(self):
        for invalid in [
          replace(stat(O22),provider="Autokuk"),
          replace(stat(O22),year=2021),
          replace(stat(O22),powertrain="HEV"),
          replace(stat(O22),coverage="motor_year"),
          replace(stat(O22),underlying_date="2026-10-22"),
          replace(stat(O22),sample_n=0),
        ]:
          with self.subTest(invalid=invalid),self.assertRaises(SourceParseError):
            m.validate_stat(invalid,brand="skoda",model="octavia",year=2022,
                            url=O22["url"],as_of=date(2026,10,21))
    def test_robots_denial_stops_all_public_http(self):
        with patch.object(m,"robots_allows",return_value=(False,"denied")),\
             patch.object(m,"read_limited") as req:
            report=m.collect(plan(O22,O23),as_of=date(2026,10,21))
            req.assert_not_called()
            self.assertEqual(report["success_count"],0)
            self.assertEqual(report["http_page_requests"],0)
            self.assertEqual(len(report["checks"]),2)
    def test_exactly_3_new_octavia_years_successful(self):
        pages={x["url"]:html(x) for x in (O22,O23,O24)}
        with patch.object(m,"robots_allows",return_value=(True,"ok")) as robots,\
             patch.object(m,"read_limited",side_effect=lambda url,limit:(200,pages[url],"utf-8")) as req,\
             patch.object(m.time,"sleep") as sleep:
            report=m.collect(plan(O22,O23,O24),as_of=date(2026,10,21))
        self.assertEqual(robots.call_count,3)
        self.assertEqual(req.call_count,3)
        self.assertEqual(sleep.call_count,2)
        self.assertEqual(report["http_page_requests"],3)
        self.assertEqual([x["registration_year"] for x in report["observations"]],[2022,2023,2024])
        self.assertEqual(report["fresh_skipped"],1)
    def test_unknown_page_html_not_invented(self):
        pages={O22["url"]:b"<html>Captcha</html>",O23["url"]:html(O23)}
        with patch.object(m,"robots_allows",return_value=(True,"ok")),\
             patch.object(m,"read_limited",side_effect=lambda url,limit:(200,pages[url],"utf-8")) ,\
             patch.object(m.time,"sleep"):
            result=m.collect(plan(O22,O23),as_of=date(2026,10,21))
        self.assertEqual(result["checks"][0]["state"],"parse_or_network_error")
        self.assertEqual(len(result["observations"]),1)
    def test_empty_plan_zero_web_requests_success(self):
        with patch.object(m,"robots_allows") as robots,\
             patch.object(m,"read_limited") as req:
            result=m.collect(plan(),as_of=date(2026,10,21))
        robots.assert_not_called();req.assert_not_called()
        self.assertEqual(result["success_count"],0)
    def test_unsupported_year_page_cannot_inherit_neighbor_stat(self):
        original=html(O22).decode()
        with self.assertRaises(SourceParseError):
            parse_autohledac_year(original,O23["url"])
    def test_other_brand_new_model_supported_after_verified_html(self):
        hy=make_target("hyundai","tucson",2023)
        s=parse_autohledac_year(html(hy).decode(),hy["url"])
        self.assertEqual((s.brand,s.model,s.year),("hyundai","tucson",2023))
    def test_no_publish_outside_actions_and_min_spacing(self):
        with patch.dict(m.os.environ,{"GITHUB_EVENT_NAME":"pull_request"}),\
             self.assertRaisesRegex(RuntimeError,"authorized GitHub workflow"):
            m.rpc("plan")
        with self.assertRaises(ValueError):
            m.collect(plan(O22),pause=2,as_of=date(2026,10,21))
    def test_publish_checks_runtime_before_reserving_source_pages(self):
        import sys
        with patch.object(m,"rpc",return_value={"ok":True}) as rpc, \
             patch.object(m,"fetch_plan") as plan, \
             patch.object(sys,"argv",["market_auto_refresh.py","--publish"]):
            with self.assertRaisesRegex(RuntimeError,"no pages reserved"):
                m.main()
            self.assertEqual([x.args[0] for x in rpc.call_args_list],["capabilities"])
            plan.assert_not_called()


if __name__=="__main__":
    unittest.main()

