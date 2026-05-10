"""Refresh data/growth-metrics.csv from GA4 + Google Search Console.

Run by .github/workflows/refresh.yml on a daily cron. The workflow
checks out the repo, runs this script (which writes the CSV in place),
and commits if anything changed. The Streamlit app reads the CSV.

Auth: service account via GOOGLE_SA_JSON env var (the JSON content of
the SA key, set as a GitHub Actions secret). GA4 columns stay empty
until the SA is granted Viewer access on the GA4 property; once granted,
set GA4_PROPERTY_ID in the workflow's secrets and they populate.
"""
import csv
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    Metric,
    RunReportRequest,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]
DAYS = 90
SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:latinometrics.com")
GA4_PROPERTY = os.environ.get("GA4_PROPERTY_ID")
ARTICLE_PATH_REGEX = r"^/articles/[^/]+/?$"
OUTPUT = Path("data/growth-metrics.csv")


def fetch_ga4(creds, start, end, page_path_regex=None):
    client = BetaAnalyticsDataClient(credentials=creds)
    request = RunReportRequest(
        property=f"properties/{GA4_PROPERTY}",
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="engagedSessions"),
            Metric(name="averageSessionDuration"),
            Metric(name="screenPageViews"),
        ],
    )
    if page_path_regex:
        request.dimension_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.PARTIAL_REGEXP,
                    value=page_path_regex,
                ),
            )
        )
    try:
        response = client.run_report(request)
    except Exception as exc:
        print(f"GA4 fetch failed (likely SA lacks property access): {exc}", flush=True)
        return {}
    out = {}
    for row in response.rows:
        d = row.dimension_values[0].value
        iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        out[iso] = {
            "engaged_sessions": int(row.metric_values[0].value),
            "avg_session_duration_s": round(float(row.metric_values[1].value), 1),
            "page_views": int(row.metric_values[2].value),
        }
    return out


def fetch_gsc(creds, start, end, search_type):
    service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    rows = service.searchanalytics().query(
        siteUrl=SITE_URL,
        body={
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["date"],
            "type": search_type,
            "rowLimit": 25000,
        },
    ).execute().get("rows", [])
    return {
        r["keys"][0]: {"clicks": int(r["clicks"]), "impressions": int(r["impressions"])}
        for r in rows
    }


def main():
    sa_json = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json:
        sys.exit("GOOGLE_SA_JSON env var is required (the service account JSON content).")
    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json), scopes=SCOPES)

    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=DAYS - 1)

    if GA4_PROPERTY:
        ga4 = fetch_ga4(creds, start, end)
        ga4_articles = fetch_ga4(creds, start, end, page_path_regex=ARTICLE_PATH_REGEX)
    else:
        print("GA4_PROPERTY_ID unset — GA4 columns will be empty", flush=True)
        ga4 = {}
        ga4_articles = {}
    web = fetch_gsc(creds, start, end, "web")
    discover = fetch_gsc(creds, start, end, "discover")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    all_dates = [(start + timedelta(days=i)).isoformat() for i in range(DAYS)]

    with OUTPUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date",
            "engaged_sessions", "avg_session_duration_s", "page_views",
            "articles_engaged_sessions", "articles_avg_session_duration_s", "articles_page_views",
            "search_clicks", "search_impressions",
            "discover_clicks", "discover_impressions",
        ])
        for d in all_dates:
            ga = ga4.get(d, {})
            ga_a = ga4_articles.get(d, {})
            w = web.get(d, {})
            disc = discover.get(d, {})
            writer.writerow([
                d,
                ga.get("engaged_sessions", ""),
                ga.get("avg_session_duration_s", ""),
                ga.get("page_views", ""),
                ga_a.get("engaged_sessions", ""),
                ga_a.get("avg_session_duration_s", ""),
                ga_a.get("page_views", ""),
                w.get("clicks", ""),
                w.get("impressions", ""),
                disc.get("clicks", ""),
                disc.get("impressions", ""),
            ])

    totals = {
        "engaged": sum(r.get("engaged_sessions", 0) for r in ga4.values()),
        "articles": sum(r.get("engaged_sessions", 0) for r in ga4_articles.values()),
        "search_clicks": sum(r.get("clicks", 0) for r in web.values()),
        "search_imp": sum(r.get("impressions", 0) for r in web.values()),
        "discover_clicks": sum(r.get("clicks", 0) for r in discover.values()),
        "discover_imp": sum(r.get("impressions", 0) for r in discover.values()),
    }
    print(
        f"wrote {OUTPUT} ({DAYS} days, {start} → {end})  "
        f"engaged: {totals['engaged']:,} (articles {totals['articles']:,})  "
        f"search: {totals['search_clicks']:,}/{totals['search_imp']:,}  "
        f"discover: {totals['discover_clicks']:,}/{totals['discover_imp']:,}",
        flush=True,
    )


if __name__ == "__main__":
    main()
