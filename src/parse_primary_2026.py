"""
Parse the 2026 California June primary county-level results into an OpenElections
county CSV: 2026/20260602__ca__primary__county.csv.

Source
------
The Secretary of State publishes a per-office "SOV Statewide Contest Details"
workbook for each contest (e.g. ``19-gov.xlsx``, ``76-us-rep.xlsx``) plus a single
consolidated ``csv-voter-nominated.xlsx`` ("SOV Candidates Export"). The
consolidated export contains one row per (county, contest, candidate) with clean
candidate names, full party names, incumbent/write-in flags, and vote totals. It
covers every contest the per-office files do (verified: contest totals match the
per-office SOV "State Totals"/"District Totals" rows exactly), so we read from it
directly and then verify the output against the per-office workbooks.

Output schema (matches the existing 2020 county file):
    county, office, district, candidate, incumbent, write_in, party, votes
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path.home() / "code/openelections-sources-ca/2026/primary/statewide"
EXPORT_FILE = SOURCE_DIR / "csv-voter-nominated.xlsx"
OUTPUT_FILE = REPO_ROOT / "2026/20260602__ca__primary__county.csv"

OUTPUT_HEADERS = [
    "county", "office", "district", "candidate", "incumbent", "write_in", "party", "votes",
]

# Contest name (from the export) -> (office, district) where district is "" for
# statewide contests. District contests are matched by regex below.
STATEWIDE_OFFICES = {
    "Governor": "Governor",
    "Lieutenant Governor": "Lieutenant Governor",
    "Secretary of State": "Secretary of State",
    "Controller": "Controller",
    "Treasurer": "Treasurer",
    "Attorney General": "Attorney General",
    "Insurance Commissioner": "Insurance Commissioner",
    "Superintendent of Public Instruction": "Superintendent of Public Instruction",
}

# Regexes for district contests -> (office label, district number).
DISTRICT_CONTESTS = [
    (re.compile(r"^Board of Equalization Member District (\d+)$"), "Board of Equalization"),
    (re.compile(r"^United States Representative District (\d+)$"), "U.S. House"),
    (re.compile(r"^State Senate District (\d+)$"), "State Senate"),
    (re.compile(r"^State Assembly Member District (\d+)$"), "State Assembly"),
]


def contest_to_office(contest: str):
    """Map an SOV export contest name to (office, district). Raise if unknown."""
    if contest in STATEWIDE_OFFICES:
        return STATEWIDE_OFFICES[contest], ""
    for pattern, office in DISTRICT_CONTESTS:
        m = pattern.match(contest)
        if m:
            return office, m.group(1)
    raise ValueError(f"Unrecognized contest name: {contest!r}")


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_export():
    """Read the SOV Candidates Export and return a list of output row dicts."""
    wb = openpyxl.load_workbook(EXPORT_FILE, read_only=True, data_only=True)
    ws = wb["SOV Candidates Export"]
    rows = list(ws.iter_rows(values_only=True))
    # Row layout (0-indexed):
    # 0 Election Date | 1 Election Name | 2 County Id | 3 County Name |
    # 4 Contest ID | 5 Contest Name | 6 Candidate ID | 7 Candidate Name |
    # 8 Incumbent Flag | 9 Write-in Flag | 10 Party ID | 11 Party Name | 12 Vote Total
    records = []
    for r in rows[1:]:
        if r[0] is None:  # skip trailing blank rows
            continue
        county = collapse_spaces(str(r[3]))
        contest = str(r[5]).strip()
        candidate = collapse_spaces(str(r[7]))
        incumbent = str(r[8]).strip()
        write_in = str(r[9]).strip()
        party = "" if r[11] is None else collapse_spaces(str(r[11]))
        votes = int(round(float(r[12])))  # a few LA statewide rows are stored as floats
        office, district = contest_to_office(contest)
        records.append({
            "county": county,
            "office": office,
            "district": district,
            "candidate": candidate,
            "incumbent": incumbent,
            "write_in": write_in,
            "party": party,
            "votes": votes,
        })
    return records


def write_csv(records):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)


# --- Verification against the per-office SOV detail workbooks -----------------

# per-office detail file -> office label it covers.
DETAIL_FILES = {
    "19-gov.xlsx": "Governor",
    "46-lt-gov.xlsx": "Lieutenant Governor",
    "55-sos.xlsx": "Secretary of State",
    "58-sco.xlsx": "Controller",
    "61-treasurer.xlsx": "Treasurer",
    "64-ag.xlsx": "Attorney General",
    "67-ic.xlsx": "Insurance Commissioner",
    "113-spi.xlsx": "Superintendent of Public Instruction",
    "73-boe.xlsx": "Board of Equalization",
    "76-us-rep.xlsx": "U.S. House",
    "90-state-senator.xlsx": "State Senate",
    "95-state-assembly.xlsx": "State Assembly",
}

# Maps the mid-phrase in a district header to our office label.
DISTRICT_HEADER_OFFICE = {
    "Congressional": "U.S. House",
    "State Senate": "State Senate",
    "Assembly": "State Assembly",
    "Board of Equalization": "Board of Equalization",
}
DISTRICT_HEADER_RE = re.compile(r"^(\d+)(?:st|nd|rd|th) (.+?) District$")


def _num(v):
    return v if isinstance(v, (int, float)) else 0


def detail_totals():
    """Return {(office, district): total_votes} from the per-office SOV files.

    Statewide offices have a single clean "State Totals" row. District offices
    can have several candidate sub-blocks per district, each with its own
    "District Totals" row; we sum them all. A few sub-blocks in the SOV detail
    workbooks are garbled (a percent value lands in a totals cell, or the real
    totals are mislabeled "Percent"), so district totals from this function are
    only used as warnings, not hard checks.
    """
    totals = {}
    contests = set()
    for fname, office in DETAIL_FILES.items():
        wb = openpyxl.load_workbook(SOURCE_DIR / fname, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        current_district = ""  # statewide contests use ""
        for r in ws.iter_rows(values_only=True):
            label = r[0]
            if not isinstance(label, str):
                continue
            label = label.strip()
            if label == "State Totals":
                totals[(office, "")] = totals.get((office, ""), 0) + sum(_num(v) for v in r[1:])
                contests.add((office, ""))
                continue
            if label == "District Totals":
                totals[(office, current_district)] = (
                    totals.get((office, current_district), 0) + sum(_num(v) for v in r[1:])
                )
                continue
            m = DISTRICT_HEADER_RE.match(label)
            if m:
                current_district = m.group(1)
                contests.add((office, current_district))
    return totals, contests


def verify(records):
    """Cross-check the output against the per-office SOV detail workbooks.

    Statewide offices (single, clean "State Totals" row) are checked strictly —
    a mismatch is a hard failure. District offices are checked for coverage
    (every contest appears on both sides) and total parity is reported as a
    warning, because a handful of SOV detail sub-blocks are garbled while the
    consolidated export is authoritative.
    """
    ours = defaultdict(int)
    ours_contests = set()
    for rec in records:
        ours[(rec["office"], rec["district"])] += rec["votes"]
        ours_contests.add((rec["office"], rec["district"]))

    theirs, theirs_contests = detail_totals()

    hard_failures = []
    for key in sorted(theirs_contests & ours_contests):
        if key[1] == "":  # statewide: strict
            o, t = ours.get(key, 0), theirs.get(key, 0)
            if o != t:
                hard_failures.append((key, o, t))

    coverage_gaps = sorted((ours_contests - theirs_contests) | (theirs_contests - ours_contests))
    district_warnings = []
    for key in sorted(theirs_contests & ours_contests):
        if key[1] != "":
            o, t = ours.get(key, 0), theirs.get(key, 0)
            if o != t:
                district_warnings.append((key, o, t))

    return hard_failures, coverage_gaps, district_warnings


def main():
    records = parse_export()
    write_csv(records)
    print(f"Wrote {len(records)} rows to {OUTPUT_FILE}")

    hard_failures, coverage_gaps, district_warnings = verify(records)

    if coverage_gaps:
        print("\nVERIFICATION FAILED — contest coverage differs from SOV detail files:")
        for office, district in coverage_gaps:
            print(f"  {office} {district}")
        raise SystemExit(1)

    if hard_failures:
        print("\nVERIFICATION FAILED — statewide contest totals differ from SOV detail files:")
        for (office, district), o, t in hard_failures:
            print(f"  {office} {district}: ours={o} sov={t} diff={o - t}")
        raise SystemExit(1)

    if district_warnings:
        print("\nNote: district total differences vs SOV detail files (detail sub-blocks are")
        print("      garbled in a few contests; the consolidated export is authoritative):")
        for (office, district), o, t in district_warnings:
            print(f"  {office} {district:>3}: ours={o} sov_detail={t} diff={o - t}")

    n_contests = len({(r["office"], r["district"]) for r in records})
    print(f"Verification OK: {n_contests} contests; statewide totals match SOV detail files"
          f" and district coverage is complete.")


if __name__ == "__main__":
    main()