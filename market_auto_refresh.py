#!/usr/bin/env python3
"""V0.4.1: on-watch queued model/year refresh plus weekly maintenance.

Production acceptance: docs/external-market-v05-production-acceptance-2026-10-21.md.
Passat production acceptance source-path smoke: database migration 026 repairs
Arval pas-* to canonical volkswagen/passat/year before source planning.

No watch rules, users, VIN, individual listing IDs or vehicle details leave
Supabase. A locked-down GitHub OIDC endpoint exposes only deduplicated
brand/model/first-registration-year cohorts, prioritizing uncached/stale rows.
Maximum 4 external pages per run, <=8 claimed pages/day, >=6s gaps. Failure outcomes are recorded with per-source cooldowns.
Robots checked, no retries on access blocks or unexpected site changes.
"""
from __future__ import annotations
import argparse
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse,urlencode
from urllib.request import Request,urlopen
import json
import os
import re
import time
from zoneinfo import ZoneInfo

from market_source_probe import read_limited,robots_allows
from market_aggregate_adapters import parse_autohledac_year,SourceParseError,SourceZeroResults

MAX_PAGES=4
DELAY_SECONDS=6
OUTPUT=Path("market-auto-refresh-evidence.json")
API="https://umplaiqonphkrtfslsxj.supabase.co/functions/v1/market-research-ingest"
AUDIENCE="car-radar-market-research-refresh"
ALLOWED_EVENTS=("schedule","workflow_dispatch","push")


def get_oidc()->str:
    uri=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    token=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not uri or not token:
        raise RuntimeError("GitHub Actions OIDC is required for private planning")
    req=Request(uri+("&" if "?" in uri else "?")+urlencode({"audience":AUDIENCE}),
                headers={"Authorization":"Bearer "+token})
    with urlopen(req,timeout=20) as response:
        value=json.loads(response.read(25000)).get("value")
    if not isinstance(value,str) or not value:
        raise RuntimeError("OIDC token missing")
    return value


def rpc(action:str,observations:list[dict]|None=None)->dict:
    if os.environ.get("GITHUB_EVENT_NAME") not in ALLOWED_EVENTS:
        raise RuntimeError("Only the authorized GitHub workflow may plan/archive")
    body={"action":action}
    if action=="plan":
        kind=os.environ.get("MARKET_REFRESH_KIND","maintenance")
        if kind not in ("onboarding","maintenance"):
            raise RuntimeError("Unsupported source-refresh mode")
        body["kind"]=kind
    if observations is not None:
        body["checks" if action=="complete" else "observations"]=observations
    raw=json.dumps(body,ensure_ascii=False).encode("utf-8")
    req=Request(API,data=raw,method="POST",headers={
        "Authorization":"Bearer "+get_oidc(),"Content-Type":"application/json"})
    with urlopen(req,timeout=45) as response:
        response_body=json.loads(response.read(50000))
    if response_body.get("ok") is not True:
        raise RuntimeError("Private source archive rejected "+action)
    return response_body


def validate_target(target:dict)->tuple[str,str,int,str]:
    if not isinstance(target,dict):raise ValueError("Invalid plan target")
    brand,model,year,url=(target.get(k) for k in ("brand","model","year","url"))
    if not isinstance(brand,str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,23}",brand):
        raise ValueError("Invalid planned brand")
    if not isinstance(model,str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}",model):
        raise ValueError("Invalid planned model")
    if type(year) is not int or not 2010<=year<=datetime.now(timezone.utc).year:
        raise ValueError("Invalid planned year")
    expected=f"https://autohledac.cz/znacky/{brand}/{model}/{year}"
    if url!=expected or urlparse(url).hostname!="autohledac.cz":
        raise ValueError("Private planner returned unexpected public site URL")
    return brand,model,year,url


def fetch_plan()->dict:
    response=rpc("plan")
    expected_kind=os.environ.get("MARKET_REFRESH_KIND","maintenance")
    recovery_budget=(response.get("daily_budget")==10 and
        response.get("recovery_budget_date")=="2026-10-29" and
        datetime.now(timezone.utc).date().isoformat()=="2026-10-29")
    if (response.get("mode")!="on_watch_cohort_refresh_v041"
        or response.get("kind")!=expected_kind
        or not (response.get("daily_budget")==8 or recovery_budget)):
        raise ValueError("Private planner version, mode or daily cap mismatch")
    targets=response.get("targets")
    if not isinstance(targets,list) or len(targets)>MAX_PAGES:
        raise ValueError("Invalid source plan size")
    pairs=[validate_target(x) for x in targets]
    if len(set(pairs))!=len(pairs):
        raise ValueError("Duplicated source cohorts in plan")
    if response.get("budget")!=MAX_PAGES:
        raise ValueError("Private/runner page budget disagreement")
    return response


def publish(rows:list[dict])->dict:
    if not 1<=len(rows)<=MAX_PAGES:raise ValueError("Invalid source batch count")
    return rpc("archive",rows)


def validate_stat(stat,*,brand:str,model:str,year:int,url:str,as_of:date)->dict:
    if (stat.provider!="AutoHledac" or stat.url!=url or stat.brand!=brand
        or stat.model!=model or stat.year!=year or stat.coverage!="model_year"
        or stat.metric!="median" or stat.powertrain is not None):
        raise SourceParseError("Wrong source identity / pooled cohort")
    if type(stat.central_czk) is not int or not 100_000<=stat.central_czk<=5_000_000:
        raise SourceParseError("Implausible median")
    if type(stat.sample_n) is not int or not 1<=stat.sample_n<=100_000:
        raise SourceParseError("Invalid source sample")
    try:
        publication=date.fromisoformat(stat.underlying_date)
    except (TypeError,ValueError) as exc:
        raise SourceParseError("Dated source statement missing/invalid") from exc
    if publication>as_of or publication.year<2025:
        raise SourceParseError("Future or obsolete source date")
    return {
        "provider":"AutoHledac","brand_slug":brand,"model_family":model,
        "registration_year":year,"source_url":url,
        "scope_label":f"{brand} {model} {year} – všechny motorizace",
        "coverage":"model_year","metric":"median",
        "central_czk":stat.central_czk,"sample_n":stat.sample_n,
        "source_data_date":publication.isoformat(),
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "has_motor_filter":False,"has_mileage_filter":False,
        "has_gearbox_filter":False,"has_body_filter":False,
        "estimated_independent_ads":False,
    }


def collect(plan:dict,*,pause:int=DELAY_SECONDS,as_of:date|None=None)->dict:
    if pause<DELAY_SECONDS:raise ValueError("Minimum 6 second spacing")
    targets=plan.get("targets")
    if not isinstance(targets,list) or len(targets)>MAX_PAGES:
        raise ValueError("Invalid plan size")
    selected=[validate_target(target) for target in targets]
    if len(set(selected))!=len(selected):raise ValueError("Duplicate plan targets")
    as_of=as_of or datetime.now(ZoneInfo("Europe/Prague")).date()
    report={"mode":"dynamic_watchlist_public_source_v04",
            "captured_at":datetime.now(timezone.utc).isoformat(),
            "max_source_pages":MAX_PAGES,"ttl_days":plan.get("ttl_days"),
            "refresh_kind":plan.get("kind"),
            "daily_budget":plan.get("daily_budget"),
            "planned_today":plan.get("planned_today"),
            "active_cohorts":plan.get("active_cohorts"),
            "fresh_skipped":plan.get("fresh_skipped"),
            "due_count":plan.get("due_count"),
            "observations":[],"checks":[]}
    requests_made=0
    for brand,model,year,url in selected:
        check={"brand":brand,"model":model,"year":year,"url":url}
        allowed,robots=robots_allows(url)
        check["robots"]=robots
        if not allowed:
            check["state"]="skipped_robots"
            check["diagnostic_kind"]=("blocked" if robots=="robots_disallows" or
                robots in ("robots_http_401_not_confirmed","robots_http_403_not_confirmed","robots_http_429_not_confirmed") else "fetch_failed")
            report["checks"].append(check)
            continue
        if requests_made:time.sleep(pause)
        requests_made+=1
        try:
            status,body,charset=read_limited(url,900_000)
            if status!=200:
                check["state"]="http_status_unexpected"
                check["http_status"]=status
                check["diagnostic_kind"]="blocked" if status in (401,403,429) else "source_unavailable"
                report["checks"].append(check)
                if status in (401,403,429):break
                continue
            parsed=parse_autohledac_year(body.decode(charset,errors="replace"),url)
            observation=validate_stat(parsed,brand=brand,model=model,year=year,
                                      url=url,as_of=as_of)
            report["observations"].append(observation)
            check["state"]="parsed"
            check["diagnostic_kind"]="parsed_aggregate"
            check["source_data_date"]=observation["source_data_date"]
            check["sample_n"]=observation["sample_n"]
            check["median_czk"]=observation["central_czk"]
        except HTTPError as e:
            check["state"]="access_blocked" if e.code in (401,403,429) else "http_error"
            check["http_status"]=e.code
            check["diagnostic_kind"]="blocked" if e.code in (401,403,429) else "source_unavailable"
            report["checks"].append(check)
            if e.code in (401,403,429):break
            continue
        except (URLError,TimeoutError,ValueError,SourceParseError,UnicodeError) as e:
            check["state"]="parse_or_network_error"
            check["diagnostic_kind"]=("zero_results" if isinstance(e,SourceZeroResults) else
                "parse_failed" if isinstance(e,SourceParseError) else
                "fetch_failed" if isinstance(e,(URLError,TimeoutError)) else "normalization_failed")
            check["error_class"]=type(e).__name__
            check["reason"]=str(e)[:160] if isinstance(e,SourceParseError) else "Network or source format unavailable"
        report["checks"].append(check)
        # Private planning cohorts are deliberately absent from public logs.
    report["http_page_requests"]=requests_made
    report["success_count"]=len(report["observations"])
    return report


def main()->None:
    cli=argparse.ArgumentParser()
    cli.add_argument("--publish",action="store_true")
    args=cli.parse_args()
    if args.publish:
        try:
            capability=rpc("capabilities")
        except (HTTPError,URLError,TimeoutError,ValueError) as exc:
            OUTPUT.write_text(json.dumps({"mode":"source_runtime_bootstrap",
                "phase":"capabilities","diagnostic_kind":"source_unavailable",
                "http_status":getattr(exc,"code",None),"source_pages_reserved":0,
                "error_class":type(exc).__name__},indent=2)+"\n",encoding="utf-8")
            raise RuntimeError("Source runtime capability check failed; no pages reserved") from None
        if capability.get("recovery_contract")!="external-context-v225":
            raise RuntimeError("Source runtime is not ready for V2.25; no pages reserved")
    plan=fetch_plan()
    report=collect(plan)
    OUTPUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if args.publish and report["observations"]:
        report["archive_response"]=publish(report["observations"])
        OUTPUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    failures=[x for x in report["checks"] if x["state"]!="parsed"]
    if args.publish and failures:
        # Persist robots denials, HTTP 403/429 and HTML parse problems. The
        # source never receives retries during the same run.
        report["completion_response"]=rpc("complete",failures)
        OUTPUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if args.publish and report["checks"] and not report["observations"]:
        raise RuntimeError("Every due cohort failed; source failures recorded with cooldown")
    note=os.environ.get("GITHUB_STEP_SUMMARY")
    if note:
        with open(note,"a",encoding="utf-8") as output:
            output.write("### Dynamic market-statistics refresh\n\n")
            output.write(f"Refresh kind: {report.get('refresh_kind')}; "
                         f"daily planned: {report.get('planned_today')}/{report.get('daily_budget')}.\\n\\n")
            output.write(f"Active source cohorts: {report['active_cohorts']}; "
                         f"fresh skipped: {report['fresh_skipped']}; due: {report['due_count']}.\n\n")
            output.write(f"Public source pages requested: **{report['http_page_requests']} / {MAX_PAGES}**; "
                         f"valid observations: **{report['success_count']}**.\n\n")
            if args.publish and report.get("archive_response"):
                output.write("\nPrivate research-only Supabase archive acknowledged by OIDC.\n")
    print("Dynamic watchlist source run:",report["http_page_requests"],
          "HTTP source pages,",report["success_count"],"verified stats",flush=True)


if __name__=="__main__":
    main()



