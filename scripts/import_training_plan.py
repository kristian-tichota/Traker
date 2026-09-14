#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.config import API_TOKEN, LOCAL_SERVER_URL  # noqa: E402

TIMEOUT_S = 30

SESSION_KEYS = {"date", "week", "name", "block", "notes", "movements"}
MOVEMENT_KEYS = {"exercise", "position", "sets", "target_low", "target_high",
                 "weight_kg", "rpe", "tempo", "grouping", "notes"}

SHOWN_COMPLAINTS = 20
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def call(url, path, token, payload=None, method=None):
    """Send one request and return (status, body)."""
    request = urllib.request.Request(
        url.rstrip("/") + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method=method or ("POST" if payload is not None else "GET"))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as answer:
            return answer.status, json.load(answer)
    except urllib.error.HTTPError as refused:
        body = refused.read().decode()
        try:
            return refused.code, json.loads(body)
        except ValueError:
            return refused.code, {"error": body[:400]}


def complaints(document):
    """List everything wrong with the document shape, as sentences."""
    found = []
    for field in ("name", "start_date", "weeks"):
        if document.get(field) in (None, ""):
            found.append(f"the cycle needs a {field}")
    if not ISO_DATE.match(str(document.get("start_date", ""))):
        found.append("start_date must be ISO, as 2026-09-14")

    sessions = document.get("sessions") or []
    if not isinstance(sessions, list) or not sessions:
        found.append("the cycle has no sessions")
        return found

    seen = {}
    for session in sessions:
        where = f"{session.get('name', '?')} on {session.get('date', '?')}"
        if not ISO_DATE.match(str(session.get("date", ""))):
            found.append(f"{where}: date must be ISO, as 2026-09-14")
        elif session["date"] in seen:
            found.append(f"{where}: {seen[session['date']]} is already on that day")
        else:
            seen[session["date"]] = session.get("name", "a session")
        if not session.get("week"):
            found.append(f"{where}: needs a week number")
        found += [f"{where}: unknown key '{key}'"
                  for key in sorted(set(session) - SESSION_KEYS)]

        for movement in session.get("movements") or []:
            named = movement.get("exercise") or ""
            if not named:
                found.append(f"{where}: a movement with no exercise")
            sets = _whole(movement.get("sets", 0))
            if sets is None or not 0 <= sets <= 5:
                found.append(f"{where}, {named or '?'}: sets must be a whole "
                             f"number from 0 to 5, because one ledger row "
                             f"holds five")
            found += [f"{where}, {named or '?'}: unknown key '{key}'"
                      for key in sorted(set(movement) - MOVEMENT_KEYS)]
    return found


def _whole(value):
    """Return value as an integer, or None where it is not one."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return None


def movements_named(document):
    return {movement.get("exercise")
            for session in document.get("sessions") or []
            for movement in session.get("movements") or []}


DOCUMENT_SHAPE = """the document:

  {
    "name": "Cycle 1",
    "start_date": "2026-09-14",            ISO, and the Monday of week 1
    "weeks": 17,
    "notes": "...",                        optional
    "sessions": [
      {
        "date": "2026-09-14",              ISO; the day this session falls on
        "week": 1,                         the cycle week, a label the tab shows
        "name": "Upper A",
        "block": "block 1",                optional; shown beside the week
        "notes": "...",                    optional
        "movements": [
          {
            "exercise": "DB Floor Press",  a catalog name, exactly
            "sets": 3,                     1-5, what one ledger row holds
            "target_low": 8,               reps, or seconds for a hold
            "target_high": 12,
            "weight_kg": 20.5,             per dumbbell, as the plan is written
            "rpe": 8,
            "tempo": "3/3",                optional
            "grouping": "A1",              optional; supersets share a label
            "notes": "..."                 optional
          }
        ]
      }
    ]
  }

Every movement must already be in the exercise catalog; the service refuses the
whole import otherwise, naming it. A second cycle of the same name is refused,
which --replace deletes first.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Import a training cycle into the household service from a JSON file.",
        epilog=DOCUMENT_SHAPE,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", help="the plan, as JSON")
    parser.add_argument("--url", default=LOCAL_SERVER_URL,
                        help=f"the service (default {LOCAL_SERVER_URL})")
    parser.add_argument("--token", default=API_TOKEN, required=not API_TOKEN,
                        help="the member's API token (default: the one in the profile)")
    parser.add_argument("--dry-run", action="store_true",
                        help="check the document and the catalog, write nothing")
    parser.add_argument("--check", action="store_true",
                        help="same as --dry-run")
    parser.add_argument("--replace", action="store_true",
                        help="delete an existing cycle of the same name first")
    args = parser.parse_args()

    with open(args.document, encoding="utf-8") as handle:
        document = json.load(handle)

    wrong = complaints(document)
    if wrong:
        print(f"{len(wrong)} problem(s) with {args.document}:")
        for complaint in wrong[:SHOWN_COMPLAINTS]:
            print(f"  - {complaint}")
        if len(wrong) > SHOWN_COMPLAINTS:
            print(f"  ... and {len(wrong) - SHOWN_COMPLAINTS} more")
        return 1

    sessions = document["sessions"]
    movements = sum(len(s.get("movements") or []) for s in sessions)
    print(f"{document['name']}: {document['weeks']} weeks, "
          f"{len(sessions)} sessions, {movements} movements, "
          f"from {document['start_date']}")

    status, catalog = call(args.url, "/api/catalog/exercise", args.token)
    if status != 200:
        print(f"Could not read the exercise catalog at {args.url}: {catalog}")
        return 2
    known = {item["name"].lower() for item in catalog}
    missing = sorted(name for name in movements_named(document)
                     if (name or "").lower() not in known)
    if missing:
        print(f"\n{len(missing)} movement(s) are not in the catalog. Define them "
              f"first, with :exdefine or POST /api/catalog/exercise:")
        for name in missing:
            print(f"  - {name}")
        return 1
    print(f"Every movement is in the catalog ({len(known)} items).")

    if args.dry_run or args.check:
        print("\n--dry-run: nothing was written.")
        return 0

    status, held = call(args.url, "/api/plans", args.token)
    existing = [row for row in (held if status == 200 else [])
                if str(row[1]).lower() == document["name"].lower()]
    if existing and args.replace:
        plan_id = existing[0][0]
        status, answer = call(args.url, f"/api/logs/training_plans/{plan_id}",
                              args.token, method="DELETE")
        if status != 200:
            print(f"Could not delete cycle {plan_id} ({status}): "
                  f"{answer.get('error', answer)}")
            return 2
        print(f"Replaced: deleted cycle {plan_id}. "
              f"The exercise rows it produced are untouched.")
    elif existing:
        print(f"\nA cycle called '{document['name']}' is already there. "
              f"Re-run with --replace to overwrite it.")
        return 1

    status, answer = call(args.url, "/api/plans", args.token, document)
    if status != 200:
        print(f"\nRefused ({status}): {answer.get('error', answer)}")
        return 2
    print(f"\nImported: plan {answer['plan_id']}, {answer['sessions']} sessions, "
          f"{answer['movements']} movements. Open the Plans tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
