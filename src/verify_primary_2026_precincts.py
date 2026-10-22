"""
Verify 2026 primary precinct-level CSVs against the county-level results file.

For each ``2026/counties/20260602__ca__primary__<county>__precinct.csv`` this
groups rows by ``(office, district, normalized_candidate)`` and sums ``votes``,
then compares those sums to the matching rows of
``2026/20260602__ca__primary__county.csv`` for the same county.

Candidate names come from different county sources in different casings/forms
(e.g. ``TONY K. THURMOND`` vs ``Tony K. Thurmond``), so comparison normalizes
names with an accent/initial/case-insensitive match key. Office and district are
produced by our own parsers on both sides, so they are compared exactly. Party
is reported for context but not used as a match key.

Mismatches are split into two classes:

* **Hard** — a real parser/data bug. A county with any hard mismatch FAILS.
  - EXTRA: a candidate in the precinct file that is not in the county file.
  - MISSING (non-write-in): a county candidate absent from the precinct file.
  - VOTES (precinct > county): the precinct sum exceeds the county total
    (impossible for a faithful precinct canvass -> double count / wrong rows).

* **Soft** — an expected, inherent discrepancy between a precinct canvass and
  the county-level export, reported but not a failure.
  - MISSING (write-in): write-in candidates the SOVC does not break out per
    precinct (the export attributes them; the precinct canvass does not).
  - VOTES (precinct < county): the precinct sum is short of the county total by
    the non-precinct-assignable vote (provisional / cured / late ballots counted
    countywide but not attributed to any precinct in the Statement of Votes
    Cast). The precinct CSV faithfully reflects the SOVC; the gap is reported
    with its max and total so anomalies stay visible.

Usage:
    uv run python src/verify_primary_2026_precincts.py [county ...]
    uv run python src/verify_primary_2026_precincts.py --all
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.parsers2026.common import match_key  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
COUNTY_FILE = REPO_ROOT / "2026/20260602__ca__primary__county.csv"
PRECINCT_DIR = REPO_ROOT / "2026/counties"


def norm_name(name: str) -> str:
    """Match key for candidate names: accent/initial/case insensitive."""
    return match_key(name)


def county_slug(name: str) -> str:
    return re.sub(r"\s+", "_", str(name).strip().lower())


def load_county_file():
    """Return {county_display: {(office, district, norm_candidate): (votes, write_in, party)}}."""
    by_county = defaultdict(dict)
    with open(COUNTY_FILE, newline="") as f:
        for r in csv.DictReader(f):
            key = (r["office"], r["district"], norm_name(r["candidate"]))
            by_county[r["county"]][key] = (int(r["votes"]), r.get("write_in", ""), r.get("party", ""))
    return by_county


def load_precinct_file(path):
    """Return {(office, district, norm_candidate): (votes_sum, set_of_parties)}."""
    sums = defaultdict(int)
    parties = defaultdict(set)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            key = (r["office"], r["district"], norm_name(r["candidate"]))
            sums[key] += int(r["votes"])
            if r.get("party"):
                parties[key].add(r["party"])
    return sums, parties


def verify_county(county_display, precinct_path, county_table):
    """Return (expected_count, got_count, hard, soft).

    hard/soft are lists of (kind, office, district, cand_display, got, expected, parties).
    """
    expected = county_table.get(county_display, {})
    sums, parties = load_precinct_file(precinct_path)

    hard, soft = [], []
    for key in sorted(set(expected) | set(sums)):
        office, district, cand = key
        exp_votes, write_in, exp_party = expected.get(key, (0, "", ""))
        got_votes = sums.get(key, 0)
        pinfo = sorted(parties.get(key, set())) or ([exp_party] if exp_party else [])
        if key not in expected:
            hard.append(("extra", office, district, cand, got_votes, 0, pinfo))
        elif key not in sums:
            (soft if write_in == "Y" else hard).append(
                ("missing", office, district, cand, 0, exp_votes, pinfo))
        elif got_votes != exp_votes:
            if got_votes > exp_votes:
                # The county SOV does not precinct-attribute qualified
                # write-ins, so a precinct source that DOES break them out
                # (e.g. Clarity XML naming a write-in) can exceed the county's
                # 0 -- the mirror of the missing-write-in case. Treat as soft.
                (soft if write_in == "Y" else hard).append(
                    ("votes_over", office, district, cand, got_votes, exp_votes, pinfo))
            else:
                soft.append(("votes_under", office, district, cand, got_votes, exp_votes, pinfo))
    return len(expected), len(sums), hard, soft


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("counties", nargs="*", help="county slugs (e.g. alameda) to verify")
    ap.add_argument("--all", action="store_true", help="verify every precinct CSV in 2026/counties/")
    ap.add_argument("--details", action="store_true", help="print every soft mismatch too (default: summary only)")
    args = ap.parse_args()

    county_table = load_county_file()
    slug_to_display = {county_slug(c): c for c in county_table}

    if args.all:
        targets = sorted(PRECINCT_DIR.glob("20260602__ca__primary__*__precinct.csv"))
    else:
        targets = []
        for slug in args.counties:
            p = PRECINCT_DIR / f"20260602__ca__primary__{slug}__precinct.csv"
            if not p.exists():
                print(f"!! {slug}: no precinct file at {p}")
                continue
            targets.append(p)

    if not targets:
        print("No precinct files to verify. Generate them first.")
        return 1

    overall_ok = True
    for path in targets:
        m = re.match(r"20260602__ca__primary__(.+?)__precinct\.csv", path.name)
        slug = m.group(1)
        disp = slug_to_display.get(slug, slug.replace("_", " ").title())
        n_exp, n_got, hard, soft = verify_county(disp, path, county_table)

        if hard:
            overall_ok = False
            print(f"\n[{disp}] FAIL — {len(hard)} hard mismatch(es) "
                  f"(county contests={n_exp}, precinct contests={n_got})")
            for kind, office, district, cand, got, exp, pinfo in hard[:60]:
                d = f" {district}" if district else ""
                pi = f" party={pinfo}" if pinfo else ""
                if kind == "extra":
                    print(f"  EXTRA      {office}{d} | {cand!r}: precinct={got}{pi}")
                elif kind == "missing":
                    print(f"  MISSING    {office}{d} | {cand!r}: county={exp}{pi}")
                else:
                    print(f"  VOTES-OVER {office}{d} | {cand!r}: precinct={got} county={exp} diff={got-exp}{pi}")
            if len(hard) > 60:
                print(f"  ... and {len(hard)-60} more hard mismatches")
        else:
            print(f"[{disp}] OK — {n_exp} county contests matched across {n_got} precinct contests")

        # soft summary (always)
        under = [s for s in soft if s[0] == "votes_under"]
        miss_wi = [s for s in soft if s[0] == "missing"]
        over_wi = [s for s in soft if s[0] == "votes_over"]
        if under or miss_wi or over_wi:
            bits = []
            if under:
                max_gap = max(s[5] - s[4] for s in under)
                total_gap = sum(s[5] - s[4] for s in under)
                bits.append(f"{len(under)} candidates short by <= {max_gap} votes "
                            f"(total {total_gap}) — non-precinct votes (provisional/cured)")
            if miss_wi:
                bits.append(f"{len(miss_wi)} write-in candidate(s) not precinct-attributable")
            if over_wi:
                bits.append(f"{len(over_wi)} write-in candidate(s) precinct-attributed "
                            f"but not in county SOV")
            print(f"  soft: {'; '.join(bits)}")
            if args.details:
                for kind, office, district, cand, got, exp, pinfo in soft[:60]:
                    d = f" {district}" if district else ""
                    if kind == "missing":
                        print(f"  MISSING-WI {office}{d} | {cand!r}: county={exp}")
                    elif kind == "votes_over":
                        print(f"  VOTES-OVER-WI {office}{d} | {cand!r}: precinct={got} county={exp}")
                    else:
                        print(f"  VOTES-UNDER {office}{d} | {cand!r}: precinct={got} county={exp} diff={got-exp}")
                if len(soft) > 60:
                    print(f"  ... and {len(soft)-60} more soft mismatches")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())