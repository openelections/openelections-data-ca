"""
Re-extract 2018 Sutter County general precinct results from the county's
Statement of Vote PDF and regenerate
``2018/counties/20181106__ca__general__sutter__precinct.csv``.

This fixes openelections/openelections-data-ca#233: in the previous file the
``election_day`` and ``mail`` vote-breakdown columns were read from the wrong
candidate columns for every page after the first page of each contest block
(a two-column shift). The PDF's candidate headers run vertically (each label
word is mirrored), so the column -> candidate mapping is rebuilt here from
word geometry:

  * Data rows (upright text): one line per precinct x counting group -- a
    precinct row (label + 4-digit id + numbers), a "<precinct> - Vote-By-Mail
    Ballot Total" row, and a "<precinct> - All-Mail-Ballot Totals" row.
  * Header labels (rotated): an office label ("GOVERNOR", "STATE TREASURER",
    ...) precedes its two candidate labels; each candidate label sits centered
    over its own vote column. For contests whose pages print no rotated
    office label (U.S. Senate, SPI, House/Senate/Assembly), the contest comes
    from the "NON-PARTISAN ..." title line under the page footer.
    Proposition / judge / local-office pages are skipped.
  * Each precinct block is printed several times (the precinct list repeats
    across the pages of a contest group); a value for a precinct x candidate
    is overwritten, never summed.

votes = election_day + mail, where election_day = the precinct row and mail =
the Vote-By-Mail row plus the All-Mail-Ballot row (zero except for the
"Mail Ballot" precincts, whose votes exist only on the All-Mail-Ballot row;
the previous file carried those precincts under bare ids like "41").

Parsed totals are verified against the PDF's per-contest "Grand Totals" rows
and diffed against the file being regenerated; write the new file only if the
totals check is clean.

Candidate spellings, parties, the party-before-candidate column order and
the precinct spelling/order conventions are carried over from the
pre-existing file so the diff is limited to corrected values.

Run:
    uv run --with pdfplumber python src/parse_general_2018_sutter.py
"""

import csv
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PDF = Path.home() / ("code/openelections-sources-ca/2018/"
                            "Sutter CA Statement_of_the_vote_2018-11-06.pdf")
OUT_PATH = REPO_ROOT / "2018/counties/20181106__ca__general__sutter__precinct.csv"

HEADERS = ["county", "precinct", "office", "district", "party", "candidate",
           "votes", "election_day", "mail"]

# Rotated office-label text, un-mirrored -> (canonical office, district).
OFFICE_LABELS = {
    "GOVERNOR": ("Governor", ""),
    "LIEUTENANT GOVERNOR": ("Lieutenant Governor", ""),
    "SECRETARY OF STATE": ("Secretary of State", ""),
    "STATE CONTROLLER": ("Controller", ""),
    "STATE TREASURER": ("Treasurer", ""),
    "ATTORNEY GENERAL": ("Attorney General", ""),
    "INSURANCE COMMISSIONER": ("Insurance Commissioner", ""),
}
# Canonical order in which the previous file lists offices.
OFFICE_ORDER = ["Governor", "Lieutenant Governor", "Secretary of State",
                "Controller", "Treasurer", "Attorney General",
                "Insurance Commissioner", "U.S. Senate",
                "Superintendent of Public Instruction", "U.S. House",
                "State Senate", "State Assembly"]

# "NON-PARTISAN ..." title lines (below the page footer) for single-contest
# pages that print no rotated office label.
TITLE_OFFICES = {
    "NON-PARTISAN U.S. SENATOR": ("U.S. Senate", ""),
    "NON-PARTISAN SUP OF PUBLIC INSTRUCTION":
        ("Superintendent of Public Instruction", ""),
}
# Titles with an embedded ordinal district.
TITLE_DISTRICT_RE = {
    "NON-PARTISAN U.S. REPRESENTATIVE": "U.S. House",
    "NON-PARTISAN STATE SENATOR": "State Senate",
    "NON-PARTISAN STATE ASSEMBLY": "State Assembly",
}
ORDINAL_RE = re.compile(r"\b(\d+)(?:ST|ND|RD|TH) DISTRICT", re.I)
NUM_RE = re.compile(r"\d+|\d+\.\d\d")

# Rotated label texts whose page holds only excluded contests (propositions,
# judges, local offices).
PAGE_SKIP_RE = re.compile(r"^(?:PROPOSITION|BONDS|MEASURE|JUSTICE|MEMBER|"
                          r"CORRIGAN|KRUGER|YES|NO)$", re.I)
# Vertical rollup rows at the end of each contest group.
ROLLUP_ROWS = {
    "precinct totals", "vote-by-mail ballot totals", "all-mail-ballot totals",
    "sutter county", "unincorporated",
}


def norm_key(name):
    """Uppercase, drop punctuation and one-letter initials."""
    toks = re.sub(r"[^\w\s]", " ", name.upper()).split()
    return " ".join(t for t in toks if len(t) > 1)


def compact_key(name):
    return norm_key(name).replace(" ", "")


def decode_labels(page):
    """Rotated header labels as (x_center, text); text un-mirrored, each
    label column read bottom-to-top."""
    rot = [w for w in page.extract_words(extra_attrs=["upright"])
           if not w["upright"]]
    cols = defaultdict(list)
    for w in rot:
        cols[round(w["x0"])].append(w)
    out = []
    for x0 in sorted(cols):
        ws = sorted(cols[x0], key=lambda w: -w["bottom"])
        text = " ".join(w["text"][::-1] for w in ws)
        out.append(((x0 + ws[0]["x1"]) / 2, text))
    return out


def office_from_title(title):
    t = re.sub(r"\s+", " ", title.strip())
    for prefix, office in TITLE_DISTRICT_RE.items():
        if t.startswith(prefix):
            m = ORDINAL_RE.search(t)
            return (office, m.group(1) if m else "")
    return TITLE_OFFICES.get(t)


def vote_column_centers(page_words):
    """x1 right edges of the numeric data-cell columns, merged within 3pt,
    minus the first three columns (Registered / Ballots Cast / Turnout %)."""
    x1s = sorted(w["x1"] for w in page_words
                 if w["x0"] >= 126 and NUM_RE.fullmatch(w["text"]))
    clusters = []
    for x1 in x1s:
        if clusters and x1 - clusters[-1][-1] <= 3:
            clusters[-1].append(x1)
        else:
            clusters.append([x1])
    # data columns appear in every row on the page; stray numeric words in
    # headers/footers ('100003', 'Statement of Vote 56 of 102') don't
    clusters = [c for c in clusters if len(c) >= 8]
    centers = [sum(c) / len(c) for c in clusters]
    return centers[3:] if len(centers) > 3 else []


def _col_index(w, centers):
    for i, c in enumerate(centers):
        if abs(w["x1"] - c) <= 3:
            return i
    return None


def _page_contests(page):
    """Which contests this page covers, as [((office, district),
    [candidate_label, ...]), ...] in vote-column order. None when the page
    holds only excluded contests (propositions, judges, local offices)."""
    labels = decode_labels(page)
    labels = [l for l in labels if l[0] > 210
              and l[1] not in ("Registration", "Ballots Cast", "Turnout (%)")]
    if any(PAGE_SKIP_RE.match(t) for _, t in labels):
        return None

    # rotated office labels split the candidate labels into contest chunks
    contests = []
    curr = None
    for _, text in labels:
        if text in OFFICE_LABELS:
            curr = text
            contests.append([OFFICE_LABELS[text], []])
        elif curr is not None:
            contests[-1][1].append(text)
    if contests:
        return contests

    # no rotated office labels: fall back to the "NON-PARTISAN" title line
    titles = [re.sub(r"\s+", " ", l.strip())
              for l in (page.extract_text() or "").splitlines()
              if l.strip().startswith("NON-PARTISAN ")
              and not l.strip().endswith(("YES", "NO"))]
    if not titles:
        return None
    od = office_from_title(titles[-1])
    if od is None:
        return None
    return [(od, [t for _, t in labels])]


def _precinct_row(low, nums):
    """The Election-Day precinct row: label carries a 4-digit id token; a
    rollup row (SENATE, SUPERVISOR DIST 1, Precinct Totals, ...) has none."""
    toks = low.split()
    id_pos = None
    for i, t in enumerate(toks):
        if t.isdigit() and len(t) == 4:
            id_pos = i
            break
    if id_pos is None or len(nums) < 4:
        return None
    return (" ".join(toks[:id_pos]), nums)


def parse_pdf():
    """Returns (votes, county_totals) where
    votes: (office, district) -> {candidate_label: {precinct_lower:
        [election_day, vote_by_mail, all_mail]}}
    county_totals: (office, district, candidate_label) -> int
    """
    votes = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    county_totals = {}
    seen_precincts = []
    seen_precincts = []

    with pdfplumber.open(SOURCE_PDF) as pdf:
        current = None  # lower-cased name of the precinct block being read
        for page in pdf.pages:
            contests = _page_contests(page)
            if contests is None:
                current = None
                continue

            words = [w for w in page.extract_words() if w["upright"]]
            rows = defaultdict(list)
            for w in words:
                rows[round(w["top"])].append(w)
            centers = vote_column_centers(
                [w for rl in rows.values() for w in rl])

            # vote column -> (office, district, candidate_label)
            col_map = []
            for od, cands in contests:
                for c in cands:
                    col_map.append((od, c))
            if len(col_map) != len(centers):
                print(f"!! page {len(col_map)} candidate columns vs "
                      f"{len(centers)} vote columns")
                sys.exit(1)

            for top in sorted(rows):
                rl = sorted(rows[top], key=lambda w: w["x0"])
                label = " ".join(w["text"] for w in rl if w["x0"] < 126)
                low = label.lower()
                nums = [w for w in rl
                        if w["x0"] >= 126 and NUM_RE.fullmatch(w["text"])]
                if not nums or low in ROLLUP_ROWS:
                    continue
                if low.startswith("grand totals"):
                    _add_total(county_totals, col_map, nums, centers)
                elif " - vote-by-mail" in low:
                    _add_row(votes, col_map, nums, centers, 1,
                             _cont_precinct(low, current))
                elif " - all-mail-ballot" in low:
                    _add_row(votes, col_map, nums, centers, 2,
                             _cont_precinct(low, current))
                else:
                    ed = _precinct_row(low, nums)
                    if ed is None:
                        continue
                    current, nums2 = ed
                    _add_row(votes, col_map, nums2, centers, 0, current)
                    if current not in seen_precincts:
                        seen_precincts.append(current)

    return votes, county_totals, seen_precincts


def _cont_precinct(low, current):
    """Precinct name from a continuation ("<precinct> - Vote-By-Mail ...")
    row label; only usable when it matches the precinct block being read."""
    name = low.split(" - ")[0].strip()
    return name if name == current else None


def _add_total(total, col_map, nums, centers):
    """Record a ('Grand Totals') row's numeric cells as county totals."""
    for w in nums:
        i = _col_index(w, centers)
        if i is None or i >= len(col_map):
            continue
        (office, district), cand = col_map[i]
        total[(office, district, cand)] = int(w["text"].split(".")[0])


def _add_row(votes, col_map, nums, centers, slot, precinct):
    """Store one row's numeric cells, overwriting (precinct blocks repeat)."""
    if precinct is None:
        return  # continuation row whose precinct's block isn't being read
    for w in nums:
        i = _col_index(w, centers)
        if i is None or i >= len(col_map):
            continue
        (office, district), cand = col_map[i]
        votes[(office, district)][cand].setdefault(precinct, [0, 0, 0])[slot] \
            = int(w["text"].split(".")[0])


def resolve_cand(meta, label):
    """(csv_candidate, party) for a decoded PDF label, matched against the
    pre-existing file: normalized key, then without spaces, then a fuzzy
    match (PHILLIP KIM vs Philip Kim)."""
    for key in (norm_key(label), compact_key(label)):
        if key in meta:
            return meta[key]
    matches = difflib.get_close_matches(norm_key(label), list(meta), n=1,
                                        cutoff=0.75)
    if matches:
        return meta[matches[0]]
    return (None, None)


def main():
    votes, county_totals, precinct_seq = parse_pdf()

    # candidate spellings / parties and precinct spellings from the file being
    # regenerated, so the diff is limited to corrected values
    with open(OUT_PATH, newline="") as f:
        old_rows = list(csv.DictReader(f))
    cand_meta = defaultdict(dict)  # office -> {key: (csv_name, party)}
    old_precincts = {}  # norm(precinct) -> csv spelling
    for r in old_rows:
        office = r["office"].strip()
        cand_meta[office][norm_key(r["candidate"])] = (
            r["candidate"], r["party"].strip())
        cand_meta[office][compact_key(r["candidate"])] = (
            r["candidate"], r["party"].strip())
        old_precincts[re.sub(r"\s+", " ", r["precinct"].strip().upper())] = \
            r["precinct"]

    # 1. every contest: parsed precinct sums vs the PDF's Grand Totals row
    bad = 0
    for od in votes:
        for label in votes[od]:
            cand, _ = resolve_cand(cand_meta[od[0]], label)
            if cand is None:
                print(f"!! unmatched candidate label: {od[0]} / {label!r}")
                bad += 1
                continue
            s = sum(e + v + a for e, v, a in votes[od][label].values())
            t = county_totals.get((od[0], od[1], label))
            if t is None:
                print(f"!! no Grand Totals row for {od} {label}")
                bad += 1
            elif s != t:
                print(f"!! MISMATCH {od[0]} {cand}: parsed {s} "
                      f"vs Grand Totals {t}")
                bad += 1
    if bad:
        sys.exit(1)

    # 2. build the output rows: office -> candidate -> precinct, in the
    #    pre-existing file's order, with new precincts (the renamed "Mail
    #    Ballot" ones) appended in source order
    rows_out = []
    for office in OFFICE_ORDER:
        od = next((o for o in votes if o[0] == office), None)
        if od is None:
            print(f"!! office {office!r} not found in the parsed PDF")
            sys.exit(1)
        for cand_label in votes[od]:
            cand, party = resolve_cand(cand_meta[office], cand_label)
            for precinct in precinct_seq:
                e, v, a = votes[od][cand_label][precinct]
                display = old_precincts.get(precinct.upper(),
                                            precinct.title()).strip()
                rows_out.append({
                    "county": "Sutter",
                    "precinct": display,
                    "office": office,
                    "district": od[1],
                    "party": party,
                    "candidate": cand,
                    "votes": e + v + a,
                    "election_day": e,
                    "mail": v + a,
                })

    # 3. diff against the old file (match bare-digit old precinct names for
    #    the Mail Ballot ones via the "MAIL BALLOT _" suffix)
    def key_for(r):
        p = re.sub(r"\s+", " ", r["precinct"].strip().upper())
        p = p if re.search(r"[A-Z]", p) else "MAIL BALLOT " + p
        return (r["office"].strip(), r["candidate"], r["district"].strip(), p)

    old = {key_for(r): r for r in old_rows}
    diffs = defaultdict(int)
    for r in rows_out:
        o = old.get(key_for(r))
        if o is None:
            diffs["rows (new precincts)"] += 1
            continue
        for col in ("votes", "election_day", "mail"):
            if (int(o[col]) if o[col].strip() else 0) != r[col]:
                diffs[col] += 1
    print(f"diff vs previous file: {dict(diffs) or 'no changes'}")

    with open(OUT_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print(f"wrote {len(rows_out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()