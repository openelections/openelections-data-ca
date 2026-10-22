"""
Parse 2026 California June primary per-county precinct sources into OpenElections
precinct CSVs under ``2026/counties/`` named
``20260602__ca__primary__<county>__precinct.csv`` (county lowercased, spaces ->
underscores).

County sources come in many formats (clean long tables, SOVC "PrecinctCanvass"
workbooks, paginated "Page: N of M" SOVC exports, office-per-sheet exports,
messy reporting CSVs, …). Each county has a parser function below that returns a
list of row dicts with keys ``county, precinct, office, district, candidate,
party, votes``. Candidate names and parties are canonicalized against the
county-level file so output matches ``test_data``'s invariant; only statewide
offices (those present in the county-level file) are emitted.

Run:
    uv run --with openpyxl python src/parse_primary_2026_precincts.py [county ...]

Then verify:
    uv run python src/verify_primary_2026_precincts.py --all
"""

import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import openpyxl
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.parsers2026.common import (  # noqa: E402
    CountyReference, PARTY_CODE_MAP, is_summary_name, map_party, norm_name,
    parse_office,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path.home() / "code/openelections-sources-ca/2026/primary"
OUT_DIR = REPO_ROOT / "2026/counties"
HEADERS = ["county", "precinct", "office", "district", "candidate", "party", "votes"]


def slugify(name):
    return re.sub(r"\s+", "_", str(name).strip().lower())


def write_county(display_name, rows):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(display_name)
    path = OUT_DIR / f"20260602__ca__primary__{slug}__precinct.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADERS})
    return path


def _emit(ref, county, precinct, office, district, name, party_raw, votes, counter):
    od = (office, district)
    if od not in ref.contests.get(county, set()):
        return  # not a statewide office for this county (or wrong county) -> skip
    cand = ref.canonical_name(office, district, name)
    party = ref.canonical_party(office, district, name) or map_party(party_raw)
    counter.append({
        "county": county, "precinct": str(precinct), "office": office,
        "district": district, "candidate": cand, "party": party, "votes": int(votes),
    })


# ---------------------------------------------------------------------------
# Sacramento — clean long table, 'Precinct Results' sheet.
# ---------------------------------------------------------------------------

def parse_sacramento(ref):
    county = "Sacramento"
    path = SOURCE_DIR / "2026 Sacramento County, CA precinct-level results.xlsx"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Precinct Results"]
    rows_out = []
    for r in ws.iter_rows(values_only=True):
        if r[0] is None or r[0] == "Precinct":
            continue
        precinct, office_name, _contest_id, ballot_name, _choice_id, party, total = r[:7]
        if ballot_name is None or is_summary_name(ballot_name):
            continue
        od = parse_office(office_name)
        if not od:
            continue
        if total is None:
            continue
        _emit(ref, county, precinct, od[0], od[1], ballot_name, party, total, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# Humboldt — clean long CSV with per-vote-channel rows to sum per precinct.
# ---------------------------------------------------------------------------

def parse_humboldt(ref):
    county = "Humboldt"
    path = SOURCE_DIR / "2026 Humboldt County, CA precinct-level results.csv"
    sums = defaultdict(int)  # (precinct, office, district, norm_name) -> votes
    meta = {}  # (precinct, office, district, norm_name) -> raw_name
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            office_name = r["office_name"]
            district_name = r["district_name"]
            title = office_name + (f" District {district_name}" if str(district_name).isdigit() else "")
            od = parse_office(title)
            if not od:
                continue
            precinct = r["division_name"]
            cand = r["candidate_name"]
            if not cand or is_summary_name(cand):
                continue
            key = (precinct, od[0], od[1], norm_name(cand))
            sums[key] += int(r["votes"])
            meta[key] = (cand, r.get("candidate_party_name", ""))
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        raw_name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, raw_name, party_raw, votes, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# PrecinctCanvass / District Canvass SOVC workbooks (Alameda, Kings, Monterey,
# Sonoma, San Diego). One contest may span several sheets (candidate columns
# paginate); each sheet repeats all precincts with its candidate subset.
# ---------------------------------------------------------------------------

_CAND_HEADER_RE = re.compile(r"^([A-Z/]+(?:\s*\(W/I\))?)\s*-\s*(.+)$")
_CONTEST_LABEL_RE = re.compile(r"^\s*\d+\s+\S")
# A real precinct id: all digits (Kings/Monterey/Sonoma/Alameda) or a San
# Diego-style "0001-100000-NAME" code. Aggregate rollup rows in the canvass
# ("Electionwide", "16th Senatorial", "County of Kings", "City of Avenal", …)
# do not match, so they are excluded from the per-precinct sums.
#
# Named distinctly from the PDF-parser _PRECINCT_ID_RE defined further down
# (a *different* regex used by the Sierra rotated-PDF parsers) so a module-
# level redefinition there cannot silently shadow this one and break the
# canvass precinct-id filter (it clobbered San Diego's parse to 0 rows).
_CANVASS_PCT_ID_RE = re.compile(r"^\d+$|^\d+-\d+-")


def _is_precinct_id(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return isinstance(v, str) and bool(_CANVASS_PCT_ID_RE.match(v.strip()))


def _to_int(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s in ("", "***", "*****", "-"):
        return 0
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        return 0


def _parse_contest_label(label):
    """Split a canvass contest-label cell into {index: (office, district)}.

    Most sheets hold one contest: ``"1 Governor"``. Some Kings/Monterey/Sonoma
    sheets stack two contests in one cell, e.g.
    ``"1 Attorney General     2 Insurance Commissioner"``, with the candidate
    columns tagged ``1``/``2`` on the row above the header. The split keys on a
    digit marker that is either at the start of the cell or preceded by 2+
    spaces, so an embedded district number (``"1 U.S. Representative, 10th
    Congressional District"``) is NOT mistaken for a second contest.
    """
    subs = {}
    markers = list(re.finditer(r"(?:^|\s{2,})(\d+)\s+", label))
    for i, m in enumerate(markers):
        idx = m.group(1)
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(label)
        od = parse_office(label[start:end].strip())
        if od:
            subs[idx] = od
    return subs


def parse_precinctcanvass(ref, county, path, dedup=False):
    """Parse a "SOVC / Precinct Canvass by Precinct" workbook.

    Each sheet is one page of one contest (or a stacked pair); candidate
    columns are ``PARTY - NAME`` cells, data rows are ``<precinct id> | Total |
    <registered> <cast> <turnout> | <cand votes...>``. Candidates paginate
    across sheets, so votes accumulate by ``(precinct, candidate)`` across
    sheets. Set ``dedup`` when a sheet REPRINTS each precinct under several
    overlapping group headers (Congressional / Senatorial / Assembly /
    Supervisorial / BOE / countywide) with identical values -- Ventura does
    this, so summing would over-count by the number of groupings; dedup keeps
    the first occurrence per (precinct, candidate).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    # (precinct, office, district, norm_name) -> votes; accumulate across sheets
    sums = defaultdict(int)
    meta = {}
    for sn in wb.sheetnames:
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        # find the contest-label cell (e.g. "1 Governor" or a stacked
        # "1 Attorney General     2 Insurance Commissioner") in the first rows
        subs = {}
        for r in rows[:10]:
            for cell in r:
                if isinstance(cell, str) and _CONTEST_LABEL_RE.match(cell):
                    subs = _parse_contest_label(cell)
                    if subs:
                        break
            if subs:
                break
        if not subs:
            continue
        # find header row (contains "Registered Voters")
        header_idx = None
        for i, r in enumerate(rows[:12]):
            if any(isinstance(c, str) and "REGISTERED VOT" in c.upper() for c in r):
                header_idx = i
                break
        if header_idx is None:
            continue
        header = rows[header_idx]
        # tag row (immediately above header) carries the per-column contest
        # index ("1"/"2") on multi-contest sheets.
        tag_row = rows[header_idx - 1] if header_idx > 0 else None
        default_idx = next(iter(subs)) if len(subs) == 1 else None

        cand_cols = []  # (col_index, party_raw, name, (office, district))
        for c, cell in enumerate(header):
            if c < 6 or not isinstance(cell, str):
                continue
            label = cell.strip()
            if not label or is_summary_name(label):
                continue  # "Over Votes", "Under Votes", "Write-Ins", "Total Votes", …
            tag = ""
            if tag_row is not None and c < len(tag_row) and tag_row[c] is not None:
                tag = str(tag_row[c]).strip()
            if tag and tag in subs:
                od = subs[tag]
            elif tag:
                continue  # tagged for a non-statewide contest on this sheet
            elif default_idx is not None:
                od = subs[default_idx]
            else:
                continue
            m = _CAND_HEADER_RE.match(label)
            if m:
                cand_cols.append((c, m.group(1).strip(), m.group(2).strip(), od))
            else:
                # Non-partisan contest (e.g. Superintendent of Public
                # Instruction): the column header is just the candidate name.
                cand_cols.append((c, "", label, od))
        if not cand_cols:
            continue
        # data rows. Most canvasses have a "Total" sub-row per precinct; some
        # (e.g. Yuba) only carry per-channel rows (Election Day / Vote by Mail)
        # with no Total — sum those channels instead. Rollup rows
        # ("Electionwide", "County of …") are rejected by _is_precinct_id.
        data_rows = rows[header_idx + 1:]
        has_total = any(
            r and len(r) > 1 and isinstance(r[1], str) and r[1].strip().lower() == "total"
            for r in data_rows
        )
        for r in data_rows:
            if not r or len(r) < 2 or r[0] is None:
                continue
            vt = r[1]
            if not isinstance(vt, str):
                continue
            vt = vt.strip()
            if has_total:
                if vt.lower() != "total":
                    continue
            else:
                # skip the bare precinct-id header row (empty channel) and any
                # summary/Total label; accept per-channel rows.
                if not vt or vt.lower() == "total" or is_summary_name(vt):
                    continue
            if not _is_precinct_id(r[0]):
                continue
            precinct = str(r[0]).strip()
            for c, party_raw, name, od in cand_cols:
                office, district = od
                v = _to_int(r[c]) if c < len(r) else 0
                if v == 0 and name == "":
                    continue
                key = (precinct, office, district, norm_name(name))
                if dedup:
                    if key not in sums:
                        sums[key] = v
                        meta[key] = (name, party_raw)
                else:
                    sums[key] += v
                    meta[key] = (name, party_raw)
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# "Page: N of M" SOVC exports (Colusa, Contra Costa, Fresno, Imperial, Inyo,
# San Benito, San Francisco, San Luis Obispo, Santa Barbara, Siskiyou, Sutter,
# Tulare). Each sheet is one page of one contest (candidates paginate across
# sheets). Header row has col0 "Precinct"; candidate columns are cells like
# "MARGARET TROWE\n(NPP)" (count) followed by an unlabeled percent column.
# Two row layouts:
#   * single-row precincts (Colusa/Inyo/Siskiyou/Tulare): col0 = precinct id,
#     col1 = Times Cast (a number), candidate counts inline;
#   * sub-row precincts (the rest): a precinct-id row (col1 empty) followed by
#     per-channel rows ("Vote by Mail"/"Election Day"/...) and a "Total" row
#     (col1 numeric). We read the Total row when present, else sum channels.
# Aggregate rollup rows ("Electionwide", "California", "Electionwide - Total",
# "Cumulative", "County", "State", "Contra Costa County", ...) are skipped.
# ---------------------------------------------------------------------------

_PAGE_CAND_RE = re.compile(r"^(.+?)\s*\(([A-Z/\-&]+)\)\s*$", re.S)
# col0 values that mark a per-channel (or Total) sub-row, not a precinct id.
_PAGE_CHANNEL_SET = {
    "vote center", "vote centers", "vote by mail", "vote-by-mail", "mail voting",
    "election day", "polling", "poll", "polls", "mail", "vbm", "early voting",
    "provisional", "in-person", "total",
}
_PAGE_ROLLUP_RE = re.compile(
    r"\b(electionwide|california|cumulative|county|state|total|ballots?|registered|turnout|congressional|senatorial|assembly)\b"
)
# Fragments that mark a non-candidate header cell in the SPI non-partisan
# fallback (catches combined labels like "Unqualified Write-In Qualified
# Write In" that the anchored is_summary_name check misses).
_PAGE_SPI_SKIP_RE = re.compile(
    r"\b(write-?\s*in|unqualified|qualified|scattered|undervote|overvote|"
    r"total|ballots?|registered|turnout|blanks?|provisional|canvass|"
    r"electionwide|cumulative)\b", re.I
)


def _is_page_rollup(s):
    s = str(s).strip().lower()
    if not s or s in _PAGE_CHANNEL_SET:
        return False
    if is_summary_name(s):
        return True
    return bool(_PAGE_ROLLUP_RE.search(s))


def _is_data_row(vt):
    """True if col1 looks like a populated data row (Times Cast present)."""
    if vt is None:
        return False
    if isinstance(vt, (int, float)):
        return True
    return bool(str(vt).strip()) and str(vt).strip().lower() != "precinct"


def parse_pageformat(ref, county, path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sums = defaultdict(int)
    meta = {}
    for sn in wb.sheetnames:
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        # header row: col0 == "Precinct"
        header_idx = None
        for i, r in enumerate(rows[:8]):
            if r and isinstance(r[0], str) and r[0].strip().lower() == "precinct":
                header_idx = i
                break
        if header_idx is None:
            continue
        # contest title: nearest col0 string above the header that parses to a
        # statewide office (skips the "Page: N of M" row).
        contest = None
        for r in reversed(rows[:header_idx]):
            if r and isinstance(r[0], str) and r[0].strip():
                od = parse_office(r[0])
                if od:
                    contest = od
                    break
        if not contest or contest not in ref.contests.get(county, set()):
            continue
        office, district = contest
        # candidate count columns: header cells "NAME\n(PARTY)". SPI is the
        # only non-partisan statewide contest; some counties' SPI columns omit
        # the party parens ("GUS MATTAMMAL\n "), so for SPI we also accept a
        # bare candidate-name header, skipping known non-candidate labels
        # (Precinct, Blanks, %, and summary labels like Total Votes).
        is_spi = office == "Superintendent of Public Instruction"
        cand_cols = []  # (col_index, party_raw, name)
        for c, cell in enumerate(rows[header_idx]):
            if not isinstance(cell, str):
                continue
            raw = cell.strip()
            m = _PAGE_CAND_RE.match(raw)
            if m:
                cand_cols.append((c, m.group(2).strip(), m.group(1).strip()))
                continue
            if not is_spi:
                continue
            cleaned = re.sub(r"\s+", " ", raw).strip()
            cl = cleaned.lower()
            if not cleaned or cl in ("precinct", "blanks", "percent") or cl.endswith("%"):
                continue
            if is_summary_name(cleaned) or _PAGE_SPI_SKIP_RE.search(cleaned):
                continue
            cand_cols.append((c, "", cleaned))
        if not cand_cols:
            continue
        data_rows = rows[header_idx + 1:]
        has_total = any(
            r and isinstance(r[0], str) and r[0].strip().lower() == "total"
            for r in data_rows
        )
        current_precinct = None
        seen = set()  # precinct ids already read on this sheet
        for r in data_rows:
            if not r or r[0] is None:
                continue
            c0 = str(r[0]).strip()
            c0l = c0.lower()
            vt = r[1] if len(r) > 1 else None
            if _is_data_row(vt):
                # a row carrying candidate counts
                if c0l in _PAGE_CHANNEL_SET:
                    # sub-row precincts: attribute to current precinct
                    if current_precinct is None:
                        continue
                    if has_total and c0l != "total":
                        continue  # use the Total row, skip per-channel
                    if c0l == "total" and not has_total:
                        continue
                    precinct = current_precinct
                elif _is_page_rollup(c0):
                    continue
                else:
                    # single-row precinct: col0 is the precinct id. Some
                    # exports (Colusa 10x, Tulare 11x) vertically duplicate
                    # the whole precinct block in one sheet; take the first
                    # occurrence of each precinct id only.
                    if c0 in seen:
                        continue
                    seen.add(c0)
                    precinct = c0
                    current_precinct = c0
                for c, party_raw, name in cand_cols:
                    v = _to_int(r[c]) if c < len(r) else 0
                    if v == 0 and name == "":
                        continue
                    key = (precinct, office, district, norm_name(name))
                    sums[key] += v
                    meta[(precinct, office, district, norm_name(name))] = (name, party_raw)
            else:
                # col1 empty: precinct-id header row (sub-row layout) or a
                # rollup header; set current precinct unless it's a rollup.
                if _is_page_rollup(c0):
                    continue
                current_precinct = c0
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# Rotated-header SOV PDFs (Amador, Lake). Each contest page has candidate
# names in column headers rotated 90 degrees (pdfplumber flags them
# upright=False), with precinct rows below whose vote values align to the
# candidate columns by x-position. The two counties rotate in opposite
# handedness, so the reading direction (top->bottom vs bottom->top) is
# detected per file. Amador splits each candidate across 2-3 adjacent
# rotated columns (last name / first name / party code); Lake uses one
# column per candidate. We cluster adjacent columns into a candidate block,
# strip party tokens, and match the resulting token SET (order-insensitive)
# to the county-level reference, so neither the name-word order nor an
# embedded party code can break the match. Candidates paginate across
# pages (each page repeats all precincts with a candidate subset); votes
# accumulate by (precinct, office, district, candidate).
# ---------------------------------------------------------------------------

# Labels that mark a non-candidate (metadata) rotated column.
_PDF_METADATA = {
    "registration", "registered", "registered voters", "total registered",
    "ballots cast", "total ballots cast", "total ballots", "ballots",
    "blank ballots cast", "blank", "total voter turnout", "voter turnout",
    "turnout", "turnout %", "total", "voters", "total voters", "times cast",
}
_PDF_PARTY_TOKENS = {"dem", "rep", "npp", "lib", "grn", "pf", "ai", "np"}
# Boilerplate upright lines on every contest page (never a contest title).
_PDF_BOILERPLATE = re.compile(
    r"^(official canvass|statement of (the )?vote|statewide direct|"
    r"certified election|june \d|county of |cumulative totals|vote for|"
    r"\d+ of \d+ precincts|\d+\s*/\s*\d+.*page|page \d|precincts reporting|"
    r"canvass results report|official results|registered voters\s*\d)",
    re.I,
)
_PRECINCT_ID_RE = re.compile(r"^([A-Z]{1,4}\d+|\d+[A-Z]?|\d+)$")
# Summary-statistic column labels that share the rotated header band on Sierra's
# 180-degree canvass pages (VOTES / BALLOTS CAST / REGISTERED VOTERS / TURNOUT /
# UNDERVOTES / OVERVOTES / WRITE-IN / REJECTED / UNRESOLVED / PERCENTAGE / …).
# A header column matching this is a stats column, not a candidate; its values
# must be absorbed (dropped), not bucketed onto the nearest candidate.
_SIERRA_SUMMARY_RE = re.compile(
    r"\b(?:VOTES?|BALLOTS?|CAST|REGISTERED|TURNOUT|PERCENTAGE|UNDERVOTES?|"
    r"OVERVOTES?|WRITE-?\s*IN|REJECTED|UNRESOLVED|PROVISIONAL|BLANK|TIMES|"
    r"NONQUALIFIED|QUALIFIED|SCATTERED)\b",
    re.I,
)


def _pdf_rotated_cols(page):
    """Group a page's rotated (upright=False) chars into columns by x0."""
    rot = [c for c in page.chars if not c.get("upright", True)]
    clusters = []  # list of [x, [chars]]
    for c in sorted(rot, key=lambda c: c["x0"]):
        placed = False
        for cl in clusters:
            if abs(c["x0"] - cl[0]) < 5:
                cl[1].append(c)
                placed = True
                break
        if not placed:
            clusters.append([c["x0"], [c]])
    return [(x, chs) for x, chs in clusters]


def _pdf_cols_to_blocks(cols):
    """Cluster adjacent columns into one candidate/metadata block.

    Within a candidate the rotated name columns are ~9-11pt apart; between
    candidates the gap is >= 14pt (Amador) or >= 31pt (Lake). A 12pt threshold
    merges a candidate's own columns but keeps adjacent candidates separate
    (e.g. Amador's Masuda/Barkley, which sit 14pt apart).
    """
    blocks = []
    for x, chs in sorted(cols, key=lambda t: t[0]):
        if blocks and x - blocks[-1]["xmax"] < 12:
            blocks[-1]["chars"].extend(chs)
            blocks[-1]["xmax"] = max(blocks[-1]["xmax"], x)
        else:
            blocks.append({"xmin": x, "xmax": x, "chars": list(chs)})
    return blocks


def _pdf_read_block(block, direction):
    """Read a block's chars as a label string in the given direction.

    ``direction`` is 'tb' (top->bottom) or 'bt' (bottom->top). Chars are read
    column by column (x ascending) so a candidate split across several rotated
    columns concatenates its name words in left-to-right order.
    """
    chars = sorted(block["chars"], key=lambda c: (round(c["x0"] / 3), c["top"]))
    out = []
    last_x = None
    for c in chars:
        x = round(c["x0"] / 3)
        if last_x is not None and x != last_x:
            out.append(" ")
        out.append(c["text"])
        last_x = x
    s = "".join(out)
    if direction == "bt":
        # reverse each column's char run; simpler: reverse the whole string
        # only works because columns are equal-height labels — instead rebuild
        # per-column reversed below.
        return _pdf_read_block_rev(block)
    return s


def _pdf_read_block_rev(block):
    """Bottom->top read: within each x-column, reverse char order."""
    from collections import defaultdict
    byx = defaultdict(list)
    for c in block["chars"]:
        byx[round(c["x0"] / 3)].append(c)
    parts = []
    for x in sorted(byx):
        chs = sorted(byx[x], key=lambda c: c["top"])  # top->bottom
        parts.append("".join(c["text"] for c in chs)[::-1])  # reverse -> bottom->top
    return " ".join(parts)


def _pdf_name_tokens(label):
    """Token set for matching a rotated header label to a candidate name."""
    from src.parsers2026.common import match_key as _mk
    toks = set(_mk(label).split())
    toks -= _PDF_PARTY_TOKENS
    return frozenset(t for t in toks if len(t) > 1)


def _pdf_norm_label(label):
    s = re.sub(r"[^a-z0-9 ]", " ", label.lower())
    return re.sub(r"\s+", " ", s).strip()


def _pdf_detect_direction(pdf, county_token_sets):
    """Pick the rotation direction that yields more real labels."""
    best, best_score = "bt", -1
    for d in ("tb", "bt"):
        score = 0
        for pi in range(min(10, len(pdf.pages))):
            cols = _pdf_rotated_cols(pdf.pages[pi])
            for block in _pdf_cols_to_blocks(cols):
                label = _pdf_read_block(block, d)
                if _pdf_norm_label(label) in _PDF_METADATA:
                    score += 1
                toks = _pdf_name_tokens(label)
                if toks and toks in county_token_sets:
                    score += 1
        if score > best_score:
            best_score, best = score, d
    return best


def _fuzzy_token_match(block_toks, county_toks, _lev):
    """True if every *substantive* block token maps to a distinct county token.

    A rotated header can be mangled by the PDF column layout in two ways at
    once: a name token truncated at a column boundary (``ANDCOUNTR`` for
    ``ANDCOUNTRY``, ``LIVINGFORG`` for ``LIVINGFORGOD``) and a single token
    split into a real fragment plus a 1-2 char tail (``LIVINGFORG`` + ``OD``).
    So: drop block tokens of length <= 2 (split tails like ``od`` that match
    nothing), then accept a block token as matching a county token when it is
    equal, within edit distance 1, or a *prefix* of the county token (the
    column-truncation case, with a bounded length gap). The county may hold
    extra tokens (a dropped column), so this is a fuzzy *subset* match. Only
    fires after exact/subset tiers fail and gated by a unique county winner.
    """
    bt = [t for t in block_toks if len(t) > 2]
    ct = list(county_toks)
    if not bt:
        return False
    used = [False] * len(ct)
    for b in bt:
        found = False
        for i, c in enumerate(ct):
            if used[i]:
                continue
            if b == c or _lev(b, c) <= 1 or (c.startswith(b) and 0 < len(c) - len(b) <= 4):
                used[i] = True
                found = True
                break
        if not found:
            return False
    return True


def _pdf_match_candidate(toks, cand_list):
    """Match a token set to a county candidate.

    Tiers, tightest first: exact token-set, unique subset (header dropped a
    token), fuzzy per-token (header truncated a token within edit distance 1,
    e.g. ``COLLENBER`` -> ``COLLENBERG``), then best Jaccard above 0.5.
    """
    if not toks:
        return None
    exact = [disp for (t, disp) in cand_list if t == toks]
    if len(exact) == 1:
        return exact[0]
    sub = [disp for (t, disp) in cand_list if toks <= t and t != toks]
    if len(sub) == 1:
        return sub[0]
    # fuzzy per-token: recover truncated rotated-header name columns.
    from src.parsers2026.common import _levenshtein as _lev
    fz = [disp for (t, disp) in cand_list if t and _fuzzy_token_match(toks, t, _lev)]
    if len(fz) == 1:
        return fz[0]
    # best Jaccard, unique winner above 0.5
    best, best_j, tie = None, 0.5, False
    for t, disp in cand_list:
        if not t:
            continue
        j = len(toks & t) / len(toks | t)
        if j > best_j:
            best, best_j, tie = disp, j, False
        elif j == best_j:
            tie = True
    if best and not tie:
        return best
    return None


def parse_rotated_pdf(ref, county, path, blank_zero=False):
    """Parse a 90-degree-rotated-header precinct PDF (Amador/Lake/Tehama).

    Candidate names run vertically; pdfplumber yields them char-reversed.
    Candidate columns wrap across pages and every page reprints all precinct
    ids, so votes are SUMMED by (precinct, candidate) across pages. When
    ``blank_zero`` is set, zero-vote cells that the PDF leaves blank (Tehama)
    are still recorded as 0 so zero-vote candidates appear in the output;
    Amador/Lake print literal 0s and leave it False.
    """
    import pdfplumber
    # county-wide candidate token sets, for direction detection
    county_token_sets = set()
    cand_index = {}  # (office, district) -> [(frozenset, display_name)]
    for od in ref.contests.get(county, set()):
        lst = []
        for mk, disp in ref.by_key.get(od, {}).items():
            toks = frozenset(mk.split())
            lst.append((toks, disp))
            county_token_sets.add(toks)
        cand_index[od] = lst

    pdf = pdfplumber.open(path)
    direction = _pdf_detect_direction(pdf, county_token_sets)
    sums = defaultdict(int)
    meta = {}
    for p in pdf.pages:
        # contest title: first upright line that parses to a statewide office
        # for this county and isn't boilerplate.
        cand_lines = [s.strip() for s in (p.extract_text() or "").splitlines()
                     if s.strip() and not _PDF_BOILERPLATE.match(s.strip())]
        contest = None
        match_idx = None
        for idx, s in enumerate(cand_lines):
            od = parse_office(s)
            if od and od in ref.contests.get(county, set()):
                contest = od
                match_idx = idx
                break
        if contest is None:
            # Wrapped title (Tehama: "MEMBER OF THE STATE ASSEMBLY, 3RD" then
            # "DISTRICT" on the next line) -- try joining consecutive lines.
            for i in range(len(cand_lines) - 1):
                od = parse_office(cand_lines[i] + " " + cand_lines[i + 1])
                if od and od in ref.contests.get(county, set()):
                    contest = od
                    match_idx = i
                    break
        if not contest:
            continue  # cover / TOC / statistics page
        # A partial/unexpired-term special election (Tehama CD1 "PARTIAL/
        # UNEXPIRED TERM") parses to the same (office, district) as the full
        # term but is a distinct contest the county file does not carry
        # separately; summing it would double-count. Skip these pages.
        title_text = " ".join(cand_lines[match_idx:match_idx + 2]).upper()
        if "PARTIAL" in title_text or "UNEXPIRED" in title_text:
            continue
        office, district = contest
        cand_list = cand_index.get(contest, [])
        # rotated header blocks -> columns with (xmin, kind, name)
        cols = _pdf_rotated_cols(p)
        blocks = _pdf_cols_to_blocks(cols)
        columns = []  # (xmin, kind, name)  kind: 'meta'/'cand'/'other'
        for block in blocks:
            label = _pdf_read_block(block, direction)
            if _pdf_norm_label(label) in _PDF_METADATA:
                columns.append((block["xmin"], "meta", None))
                continue
            disp = _pdf_match_candidate(_pdf_name_tokens(label), cand_list)
            if disp:
                columns.append((block["xmin"], "cand", disp))
            else:
                columns.append((block["xmin"], "other", None))
        cand_cols = [c for c in columns if c[1] == "cand"]
        if not cand_cols:
            continue
        columns.sort(key=lambda c: c[0])
        left_edge = columns[0][0] - 10
        # data rows
        rows = {}
        for w in p.extract_words():
            k = round(w["top"] / 3) * 3
            rows.setdefault(k, []).append(w)
        for k in sorted(rows):
            line = sorted(rows[k], key=lambda w: w["x0"])
            pct_words = [w for w in line if w["x0"] < left_edge]
            if not pct_words:
                continue
            first = pct_words[0]["text"]
            if not _PRECINCT_ID_RE.match(first):
                continue
            precinct = " ".join(w["text"] for w in pct_words)
            seen = set()  # candidate-column xmins that got a value this row
            for w in line:
                if w["x0"] < left_edge:
                    continue
                s = w["text"].replace(",", "").rstrip("%")
                if "." in s:
                    continue
                try:
                    v = int(s)
                except ValueError:
                    continue
                wx = (w["x0"] + w["x1"]) / 2
                # assign to the block whose left edge is at or just left of
                # the value (values sit at a column's visual center, ~half a
                # column-width right of its left edge, so left-edge bucketing
                # is unambiguous where nearest-center would be a toss-up).
                owner = None
                for xmin, kind, name in columns:
                    if xmin <= wx + 5:
                        owner = (xmin, kind, name)
                    else:
                        break
                if owner is None or owner[1] != "cand":
                    continue
                seen.add(owner[0])
                disp = owner[2]
                key = (precinct, office, district, norm_name(disp))
                sums[key] += v
                meta[(precinct, office, district, norm_name(disp))] = (disp, "")
            # Tehama leaves zero-vote cells blank instead of printing 0; record
            # a 0 for any matched candidate column that had no value this row.
            if blank_zero:
                for xmin, kind, name in cand_cols:
                    if xmin in seen:
                        continue
                    key = (precinct, office, district, norm_name(name))
                    if key not in sums:
                        sums[key] = 0
                        meta[key] = (name, "")
    pdf.close()
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_rotated180_pdf(ref, county, path, start_page=0):
    """Parse a 180-degree-rotated "Canvass Results Report" precinct PDF.

    Sierra County's SOV PDF prints candidate names upside down: pdfplumber
    normalizes the glyphs upright, but the text stream is left
    character-reversed (``EWORT`` for ``TROWE``) and the name reads
    bottom-to-top. The layout, per contest page:

    * an upright contest title at the top (``GOVERNOR - ... Vote for One``);
    * candidate names in a header band below it, one per 36pt column, each
      column's words reversed and ordered top->bottom = name bottom->top;
    * precinct labels upright at the far left (multi-word, ``x0 < 110``);
    * integer vote values one per column, each ~16pt right of its column's
      left edge (``value_x0 ≈ col_x0 + 15``).

    A contest spans several pages (Governor has 43 candidates); the precinct
    rows repeat on each page with a different slice of candidate columns, so
    votes accumulate across pages by (precinct, candidate).

    ``start_page`` (0-indexed) skips leading front-matter pages. Butte's PDF
    prepends a 10-page Election Summary / Measures report before the SOVC,
    whose summary pages mention contest names ("Governor") without precinct
    columns; starting at the SOVC avoids mis-detecting them as contest pages.
    """
    import pdfplumber
    # (office, district) -> [(token_set, display_name)]
    cand_index = {}
    for od in ref.contests.get(county, set()):
        cand_index[od] = [(frozenset(mk.split()), disp)
                          for mk, disp in ref.by_key.get(od, {}).items()]

    def _reverse(s):
        return s[::-1]

    pdf = pdfplumber.open(path)
    sums = defaultdict(int)
    meta = {}
    for p in pdf.pages[start_page:]:
        words = p.extract_words(use_text_flow=False)
        lines = defaultdict(list)
        for w in words:
            lines[round(w["top"])].append(w)

        # contest title: first upright line parsing to a statewide office
        # for this county and isn't boilerplate.
        contest = None
        office_top = None
        for y in sorted(lines):
            txt = " ".join(w["text"] for w in sorted(lines[y], key=lambda w: w["x0"]))
            s = txt.strip()
            if not s or _PDF_BOILERPLATE.match(s):
                continue
            od = parse_office(s)
            if od and od in ref.contests.get(county, set()):
                contest = od
                office_top = y
                break
        if not contest:
            continue  # cover / statistics / summary page
        office, district = contest
        cand_list = cand_index.get(contest, [])

        # data_top = top of the left-edge "Precinct" column header; candidate
        # name words live strictly above it, data rows at and below it.
        data_top = None
        for y in sorted(lines):
            if y <= office_top:
                continue
            txt = " ".join(w["text"] for w in sorted(lines[y], key=lambda w: w["x0"]))
            if txt.strip().lower() == "precinct":
                data_top = y
                break
        if data_top is None:
            data_top = office_top + 140

        # header columns: candidate names AND summary-statistic labels share
        # the rotated header band, interleaved on the same 36pt grid. Cluster
        # band words by x0 within 12pt (a candidate can span two ~9pt-apart
        # x-columns, e.g. "LIVINGFORGOD ANDCOUNTRY" + "DEMOTT"). Read each
        # column bottom-to-top (top descending) and reverse each word's chars
        # (the 180-degree layout). Classify each as a candidate ('cand') or a
        # stats column ('meta'); stats columns are kept so their values bucket
        # to them and are dropped, rather than bleeding onto the last candidate.
        band = [w for w in words
                if w["x0"] > 100 and office_top + 8 < w["top"] < data_top]
        groups = defaultdict(list)
        for w in band:
            groups[round(w["x0"])].append(w)
        raw_cols = []  # [col_x0, [words]]
        for x in sorted(groups):
            g = groups[x]
            gx = min(w["x0"] for w in g)
            if raw_cols and gx - raw_cols[-1][0] < 12:
                raw_cols[-1][1].extend(g)
            else:
                raw_cols.append([gx, list(g)])
        columns = []  # (col_x0, kind, disp)  kind: 'cand' / 'meta'
        for cx, g in raw_cols:
            name = " ".join(_reverse(w["text"]) for w in sorted(g, key=lambda w: -w["top"]))
            if _SIERRA_SUMMARY_RE.search(name):
                columns.append((cx, "meta", None))
                continue
            disp = _pdf_match_candidate(_pdf_name_tokens(name), cand_list)
            columns.append((cx, "cand" if disp else "meta", disp))
        if not any(c[1] == "cand" for c in columns):
            continue  # summary-only page (Ballots Cast / Registered / Turnout)
        columns.sort(key=lambda c: c[0])

        # data rows: precinct label from the far-left words, integer values
        # assigned to the column (candidate or stats) whose left edge is
        # at/left of the value; only candidate owners are emitted. Values sit
        # ~16pt right of their column's left edge. Stop at the "Totals" row —
        # everything at and below it is county summary, not precinct data.
        for y in sorted(lines):
            if y <= data_top:
                continue
            line = sorted(lines[y], key=lambda w: w["x0"])
            pct_words = [w for w in line if w["x0"] < 110]
            if not pct_words:
                continue
            precinct = " ".join(w["text"] for w in pct_words).strip()
            if precinct.lower() == "precinct":
                continue
            if is_summary_name(precinct):
                break  # Totals row -> rest of the page is summary statistics
            for w in line:
                if w["x0"] < 110:
                    continue
                s = w["text"].replace(",", "").rstrip("%")
                if "." in s:
                    continue
                try:
                    v = int(s)
                except ValueError:
                    continue
                owner = None
                for col_x0, kind, disp in columns:
                    if col_x0 <= w["x0"] + 5:
                        owner = (kind, disp)
                    else:
                        break
                if owner is None or owner[0] != "cand":
                    continue
                disp = owner[1]
                key = (precinct, office, district, norm_name(disp))
                sums[key] += v
                meta[key] = (disp, "")
    pdf.close()
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_butte_pdf(ref, county, path, start_page=10):
    """Parse Butte County's 180-degree-rotated SOVC precinct PDF.

    Same rotated layout as Sierra (``parse_rotated180_pdf``) -- candidate names
    printed upside-down, character-reversed (``TERAGRAM`` = ``MARGARET``), read
    bottom-to-top; precinct id upright at ``x0 < 110``; integer vote values
    ~11pt right of each column's left edge -- but with two twists that rule out
    reusing ``parse_rotated180_pdf`` directly:

    * The PDF prepends a 10-page Election Summary / Measures report. The SOVC
      begins at ``start_page`` (0-indexed 10); those front-matter pages mention
      contest names ("Governor") in countywide summary tables and would be
      mis-detected as contest pages.

    * A contest spans many pages (Governor alone ~340 pp: ~17 candidate slices
      repeated across ~10 precinct batches) and **only the first page of each
      contest carries the contest title**. Continuation pages just have
      "Precinct" + the rotated candidate slice. So instead of detecting the
      contest from a title line (which would miss every continuation page), the
      contest is inferred per page from the candidate names themselves: each
      page's rotated header columns are matched against every county contest and
      the contest with the most matched columns wins. Roster (turnout) pages
      have no rotated candidate columns and are skipped.

    * **Each contest is reprinted under several overlapping group headers**
      ("Cumulative" = all precincts, then "1st Congressional District",
      "1st Senate District", "3rd Assembly District", "State Board of
      Equalization"), each listing its member precincts with identical values,
      plus "Electionwide" / "Total" / "<group> - Total" subtotal rows. So a
      given (precinct, candidate) appears on many pages but always with the same
      value. Real precinct ids are 4-digit numerics; every other left-edge label
      is a group header or subtotal and is skipped. Votes are deduplicated by
      (precinct, candidate) -- the first occurrence is kept -- rather than
      summed, so the group reprints don't multiply the totals.
    """
    import pdfplumber
    # (office, district) -> [(token_set, display_name)]
    cand_index = {}
    for od in ref.contests.get(county, set()):
        cand_index[od] = [(frozenset(mk.split()), disp)
                          for mk, disp in ref.by_key.get(od, {}).items()]
    contests = list(cand_index.keys())

    pdf = pdfplumber.open(path)
    values = {}  # (precinct, office, district, norm_name) -> votes (deduped)
    meta = {}
    conflicts = []
    for p in pdf.pages[start_page:]:
        words = p.extract_words(use_text_flow=False)
        lines = defaultdict(list)
        for w in words:
            lines[round(w["top"])].append(w)
        # data_top = the upright "Precinct" column header row. A contest's first
        # page prints two precinct columns ("Precinct Precinct" -- id + name),
        # so match the first token rather than the whole line. Roster (turnout)
        # pages wrap it as "Precinct Voters Cast % Turnout" but have no rotated
        # candidate columns, so they're skipped by the empty-band check below.
        data_top = None
        for y in sorted(lines):
            txt = " ".join(w["text"] for w in sorted(lines[y], key=lambda w: w["x0"])).strip()
            first = txt.split(" ", 1)[0].lower() if txt else ""
            if first == "precinct":
                data_top = y
                break
        if data_top is None:
            continue

        # rotated candidate columns (the header band sits above data_top).
        blocks = _pdf_cols_to_blocks(_pdf_rotated_cols(p))
        band = [b for b in blocks if min(c["top"] for c in b["chars"]) < data_top]
        if not band:
            continue

        # Match each column against every contest; the contest claiming the
        # most columns is this page's contest. Summary columns ("Total Votes",
        # "Qualified Write In", registered/voters stats) are recorded with
        # toks=None so they OCCUPY their x-slot in `columns` as a None owner --
        # their values then map to None and are dropped, instead of falling
        # through to the preceding candidate column (the bug that let "Total
        # Votes" inflate the prior candidate by the precinct's total ballots).
        col_label = {}  # xmin -> (name, toks or None)
        od_votes = defaultdict(int)
        is_measure = False  # YES/NO ballot-measure page -- not a candidate contest
        for b in band:
            name = _pdf_read_block(b, "bt")
            up = name.strip().upper()
            if up in ("YES", "NO"):
                is_measure = True
            if _SIERRA_SUMMARY_RE.search(name):  # Total Votes / stats / write-ins
                col_label[b["xmin"]] = (name, None)
                continue
            toks = _pdf_name_tokens(name)
            col_label[b["xmin"]] = (name, toks)
            for od in contests:
                if _pdf_match_candidate(toks, cand_index[od]):
                    od_votes[od] += 1
        if is_measure or not od_votes:
            continue
        contest = max(od_votes, key=lambda od: od_votes[od])
        office, district = contest
        cand_list = cand_index[contest]

        # final per-column candidate within the chosen contest
        columns = []  # (xmin, disp or None)
        for xmin, (name, toks) in col_label.items():
            disp = _pdf_match_candidate(toks, cand_list) if toks else None
            columns.append((xmin, disp))
        if not any(d for _, d in columns):
            continue
        columns.sort(key=lambda c: c[0])
        # Value-to-column boundaries = midpoints between adjacent label xmins.
        # A value maps to the last column whose left boundary is <= its x0. This
        # is robust to the "Total Votes" column, which right-aligns its values:
        # a 5-digit precinct total starts ~10pt LEFT of the label, so the old
        # `cx <= x0+5` rule (value must sit at/Right of label-5) let it fall
        # through to the preceding candidate. Midpoint boundaries keep such a
        # value on its own (None) column so it is dropped.
        bounds = []  # (left_boundary, xmin, disp)
        for i, (cx, disp) in enumerate(columns):
            left = cx - 60 if i == 0 else (columns[i - 1][0] + cx) / 2
            bounds.append((left, cx, disp))

        # data rows: precinct label from far-left words; integer values assigned
        # to the column whose [left_boundary, next_boundary) range holds the
        # value's x0. Only 4-digit numeric precinct-id rows are emitted; group
        # headers and subtotals are skipped (precincts appear after them within
        # the same page, so we continue rather than break).
        for y in sorted(lines):
            if y <= data_top:
                continue
            line = sorted(lines[y], key=lambda w: w["x0"])
            pct_words = [w for w in line if w["x0"] < 110]
            if not pct_words:
                continue
            precinct = " ".join(w["text"] for w in pct_words).strip()
            # Real precinct ids are 4-digit numerics. Every other left-edge label
            # is a group header ("Cumulative", "1st Congressional District",
            # "State Board of Equalization", ...) or a subtotal ("Electionwide",
            # "Total", "<group> - Total"). Skip them without breaking -- precinct
            # rows appear after group-total rows within the same page.
            if not re.match(r"^\d{3,}$", precinct):
                continue
            for w in line:
                if w["x0"] < 110:
                    continue
                s = w["text"].replace(",", "").rstrip("%")
                if "." in s:
                    continue
                try:
                    v = int(s)
                except ValueError:
                    continue
                owner = None
                owner_xmin = None
                for left, cx, disp in bounds:
                    if left <= w["x0"]:
                        owner = disp
                        owner_xmin = cx
                    else:
                        break
                if not owner:
                    continue
                # Candidate vote values are left-aligned at ~xmin+16, so a real
                # value sits at/right of its column's label. A contest's first
                # page has a second upright precinct-id column (no rotated label)
                # whose 4-digit ids land in the gap left of the first candidate
                # column -- reject those (x0 well left of the candidate label).
                if owner_xmin is not None and w["x0"] < owner_xmin - 12:
                    continue
                key = (precinct, office, district, norm_name(owner))
                # The contest is reprinted under each group header with identical
                # values, so (precinct, candidate) recurs on many pages. Keep the
                # first occurrence; flag a genuine value conflict if one appears.
                if key not in values:
                    values[key] = v
                    meta[key] = (owner, "")
                elif values[key] != v:
                    conflicts.append((precinct, office, district, owner,
                                      values[key], v))
    pdf.close()

    if conflicts:
        print(f"  [butte] {len(conflicts)} value conflicts (kept first):")
        for c in conflicts[:10]:
            print(f"    {c}")

    rows_out = []
    for (precinct, office, district, _nn), votes in values.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_clarity_xml(ref, county, path):
    """Parse a Clarity-style ``ElectionResult`` XML precinct dump.

    Structure (Marin's 2026 primary export)::

        <ElectionResult>
          <VoterTurnout> <Precinct name=... /> ... </VoterTurnout>
          <Contest key text voteFor isQuestion>
            <VoteType name="Undervotes" votes=...> <Precinct .../> </VoteType>  # contest-level
            <VoteType name="Overvotes" ...>
            <Choice key text party totalVotes>
              <VoteType name="Vote Center" votes=...> <Precinct name votes/> ... </VoteType>
              <VoteType name="Vote By Mail"  votes=...> <Precinct name votes/> ... </VoteType>
              ...
            </Choice>
          </Contest>

    Contest-level Undervotes/Overvotes are direct children of ``<Contest>``
    (not ``<Choice>``) and are skipped. Each choice's votes per precinct are
    the sum across its vote types (Vote Center + Vote By Mail + Provisional,
    mutually exclusive), which equals ``totalVotes``. Only statewide contests
    for this county (per ``parse_office`` + the county reference) are emitted.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    sums = defaultdict(int)  # (precinct, office, district, norm_name) -> votes
    meta = {}                # (precinct, office, district, norm_name) -> (raw_name, party_raw)
    for contest in root.iter("Contest"):
        od = parse_office(contest.get("text", ""))
        if od is None or od not in ref.contests.get(county, set()):
            continue
        office, district = od
        for choice in contest.findall("Choice"):
            cand = choice.get("text", "")
            party_raw = choice.get("party", "") or ""
            # Merced prefixes each candidate name with its party code
            # ("NPP MARGARET TROWE", party="NPP"). Marin has no prefix, so the
            # guard is a no-op there. SPI/write-ins carry an empty party and no
            # prefix, so they are left untouched.
            if party_raw and cand.startswith(party_raw + " "):
                cand = cand[len(party_raw) + 1:]
            if not cand or is_summary_name(cand):
                continue
            nn = norm_name(cand)
            for vt in choice.findall("VoteType"):
                for pre in vt.findall("Precinct"):
                    s = pre.get("votes", "0").replace(",", "")
                    try:
                        v = int(s)
                    except ValueError:
                        continue
                    key = (pre.get("name", ""), office, district, nn)
                    sums[key] += v
                    meta[key] = (cand, party_raw)
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_trinity_csv(ref, county, path):
    """Parse Trinity's garbled SQL Server Reporting Services CSV export.

    The export has no precinct column. It is **precinct-major**: the file is a
    sequence of 9 precinct blocks, each block listing every contest's candidates
    in a fixed order (Governor, Lieutenant Governor, ..., county offices). A new
    block begins wherever the Governor contest reappears after a non-Governor
    row. The PDF ("9 of 9" precincts) names these blocks "CONSOLIDATION 1".."9";
    CSV block 1 matches PDF Consolidation 1 (Thurmond ED=0/VBM=1/Canvass=5/Total=6),
    so block index == consolidation number.

    Column layout (64 cols, BOM/utf-8-sig, header row where col6 == "ChoiceName"):
      col0 = contest title, col6 = candidate name, col7 = party (always empty),
      col8/10/12/14/16 = ID1..ID5 vote-type votes (Election Day / Vote by Mail /
      Canvass / Early Voting / <unused>), col18 = Textbox46 = candidate total
      for that precinct (== sum of ID1..ID4; verified 0 mismatches). Some
      candidates carry a trailing ``(W)`` write-in marker that is not in the
      county file's spelling -> stripped before canonicalization. Party is
      resolved from the county reference via ``_emit``.
    """
    rows_out = []
    precinct_num = 0
    prev_was_gov = False
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 19:
                continue
            contest = row[0]
            name = row[6]
            if not contest or not name or name == "ChoiceName":
                continue
            upper = contest.upper()
            is_gov = "GOVERNOR" in upper and "LIEUTENANT" not in upper
            if is_gov and not prev_was_gov:
                precinct_num += 1
            prev_was_gov = is_gov
            od = parse_office(contest)
            if od is None:
                continue
            office, district = od
            m = re.match(r"^(.*?)\s*\(W\)\s*$", name)
            if m:
                name = m.group(1)
            try:
                votes = int(row[18].replace(",", ""))
            except ValueError:
                continue
            _emit(ref, county, f"Consolidation {precinct_num}",
                  office, district, name, "", votes, rows_out)
    return rows_out


def parse_los_angeles(ref, county, dir_path):
    """Parse Los Angeles County's per-contest ``.xls`` precinct exports.

    LA publishes one BIFF ``.xls`` per contest (statewide and local) in a
    directory. Each workbook has: row 0 = election header, row 1 = contest
    title (``GOVERNOR``, ``26TH CONGRESS DIST``, ``STATE BD EQUALIZATION D3``,
    ``SUPERINTENDENT PUBLIC INST``), row 2 = column headers (LOCATION,
    PRECINCT, SERIAL, BALLOT GROUP, VOTE BY MAIL ONLY, REGISTRATION, TYPE,
    BALLOTS CAST, then one column per candidate), and 3 data rows per precinct
    (TYPE = ``POLLING PLACE`` / ``VBM PORTION`` / ``TOTAL``). We emit the
    ``TOTAL`` row. Candidate columns are every header col >= 8 with a non-empty
    name; write-ins are not broken out by precinct (a soft shortfall). LA
    abbreviates some leading name tokens to initials (``L A DEMOTT`` ->
    ``LivingForGod AndCountry DeMott``), handled by ``canonical_name``'s
    suffix-match tier. Only statewide contests for this county (per
    ``parse_office`` + the county reference) are emitted; the many local
    offices/measures/judges yield ``parse_office`` ``None`` and are skipped.
    """
    rows_out = []
    for path in sorted(Path(dir_path).glob("*.xls")):
        wb = xlrd.open_workbook(str(path))
        sh = wb.sheet_by_index(0)
        if sh.nrows < 3:
            continue
        od = parse_office(str(sh.cell_value(1, 0)).strip())
        if od is None or od not in ref.contests.get(county, set()):
            continue
        office, district = od
        header = [str(sh.cell_value(2, c)).strip() for c in range(sh.ncols)]
        cand_cols = [c for c in range(8, sh.ncols) if header[c]]
        for r in range(3, sh.nrows):
            if str(sh.cell_value(r, 6)).strip() != "TOTAL":
                continue
            precinct = str(sh.cell_value(r, 1)).strip()
            if not precinct:
                continue
            for c in cand_cols:
                name = header[c]
                if is_summary_name(name):
                    continue
                try:
                    votes = int(sh.cell_value(r, c))
                except (ValueError, TypeError):
                    votes = 0
                _emit(ref, county, precinct, office, district, name, "", votes, rows_out)
    return rows_out


def parse_placer_pdf(ref, county, path):
    """Parse Placer County's upright "Statement of Votes Cast by Precinct" PDF.

    Each contest spans several pages (Governor alone is 89 pages). Page layout:

    * A two-line report header at ``top`` 21 and 42 ("Placer County Statement of
      Votes Cast by Precinct" / "2026 Statewide Direct Primary June 2, 2026"),
      then the **contest title** alone on a third line at ``top`` ~67-77
      (``GOVERNOR``, ``MEMBER OF STATE ASSEMBLY 5TH DISTRICT``, …). The header
      line contains "County", which would trip ``_LOCAL_RE`` in ``parse_office``,
      so the contest title is taken from the band ``55 < top < 110`` only.

    * A column header band at ``top`` ~125-200. Five metadata columns
      (Precinct / Counting Group / Registered Voters / Voters Cast / Turnout(%))
      sit at ``x0`` 114-285; each candidate occupies a ~28.8pt column to the
      right (``x0`` >= 300), its name left-aligned at the column's left edge and
      the "Votes cast for PARTY -" stack 8pt to the right of the name.

    * Three data rows per precinct: ``Vote Center``, ``Vote by Mail`` and
      ``Total`` (the counting-group label at ``x0`` ~147-172). Only the
      ``Total`` row is emitted (it already sums the other two). Precinct id is
      the leftmost word (``x0`` ~20); candidate vote values are left-aligned at
      ``name_x0 + ~12``.

    Candidate columns **wrap across pages**: a given precinct reappears on
    later pages with a different slice of candidate columns, so each
    (precinct, candidate) pair lands on exactly one page. We accumulate by
    (precinct, candidate) across all pages, so wrapping is handled naturally.

    Header name words are clustered by ``x0`` (after dropping the "Votes cast
    for -" boilerplate and party codes, which would otherwise bridge adjacent
    candidates) and matched to county candidates via ``_pdf_match_candidate``.
    """
    import pdfplumber

    # (office, district) -> [(token_set, display_name)]
    cand_index = {}
    for od in ref.contests.get(county, set()):
        cand_index[od] = [
            (frozenset(mk.split()), disp)
            for mk, disp in ref.by_key.get(od, {}).items()
        ]

    name_drop = {"votes", "cast", "for", "-"}
    # Extra tokens to strip from a gathered column label before matching.
    # "Redact"/"ed" come from a "Redacted" overlay on privacy-suppressed
    # precinct pages (the overlay text sits in the header band and in the
    # value cells); "pfp" is a Peace & Freedom party code not in the shared
    # party-token set. None of these are candidate-name tokens.
    label_drop = {"redact", "redacted", "ed", "pfp"}
    # Summary (non-candidate) column labels that share the candidate header
    # band on write-in pages: "Write-ins", "Total", "NOT QUALIFIED WRITE-IN",
    # "Scattered", over/under votes, etc. A column whose gathered label matches
    # is treated as non-candidate and its values are dropped.
    summary_label_re = re.compile(
        r"\b(?:write-?\s*ins?|qualified|unqualified|nonqualified|unresolved|"
        r"scattered|over\s*votes?|under\s*votes?|total|times\s*cast|"
        r"times\s*tallied|registered|ballots?)\b",
        re.I,
    )

    def _is_int(s):
        s = s.replace(",", "").rstrip("%")
        if "." in s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    sums = defaultdict(int)
    meta = {}
    pdf = pdfplumber.open(path)
    for p in pdf.pages:
        ws = p.extract_words()
        # contest title: the line below the two-line report header
        title_words = [w for w in ws if 55 < w["top"] < 110]
        title_words.sort(key=lambda w: (round(w["top"] / 12), w["x0"]))
        contest = parse_office(" ".join(w["text"] for w in title_words))
        if not contest or contest not in cand_index:
            continue
        office, district = contest
        cand_list = cand_index[contest]

        # data rows: group words by top (3pt bins), keep only "Total" rows
        # (the counting-group label "Total" sits at x0 ~170; "Vote Center" /
        # "Vote by Mail" rows are the components already summed into Total).
        rows = {}
        for w in ws:
            if w["top"] > 195:
                rows.setdefault(round(w["top"] / 3) * 3, []).append(w)
        total_rows = []
        for k in sorted(rows):
            line = sorted(rows[k], key=lambda w: w["x0"])
            cg = " ".join(w["text"] for w in line if 140 < w["x0"] < 205).strip()
            if cg.lower() != "total":
                continue
            pct_words = [w for w in line if w["x0"] < 60]
            if not pct_words or not _PRECINCT_ID_RE.match(pct_words[0]["text"]):
                continue
            total_rows.append((pct_words, line))
        if not total_rows:
            continue

        # Column anchors from the Total rows' own value positions. Values are
        # left-aligned, one per column at ~28.8pt spacing; every column (incl.
        # summary columns) shows a "0" even when empty, so the set of value
        # x0s is the reliable list of columns. Anchoring on values (and only on
        # Total-row values, which share one geometry) means a value always maps
        # to its OWN column, so a summary column's votes can never leak left
        # onto a candidate -- and the last column on a page isn't lost to a
        # Vote-Center/VBM-row value sitting a few points left of its anchor.
        val_x0s = sorted({
            w["x0"] for _, line in total_rows for w in line
            if w["x0"] > 300 and _is_int(w["text"]) is not None
        })
        anchors = []  # cluster value x0s (<10pt jitter) into column anchors
        for x in val_x0s:
            if anchors and x - anchors[-1] < 10:
                continue
            anchors.append(x)
        if not anchors:
            continue

        # Map each anchor to a candidate: gather the header name words whose
        # x0 sits just left of the value (name_x0 ~ value_x0 - 12). A 22pt
        # window is narrower than the 28.8pt column pitch, so it never reaches
        # an adjacent candidate's name.
        header_words = [
            w for w in ws
            if 120 < w["top"] < 205 and w["x0"] > 300
            and w["text"].lower() not in name_drop
            and w["text"].upper() not in _PDF_PARTY_TOKENS
            and not re.fullmatch(r"[\d,.-]+", w["text"])  # value bled into header
        ]
        col_cand = {}  # anchor_x0 -> display_name or None
        for ax in anchors:
            label = " ".join(
                w["text"] for w in header_words if ax - 18 < w["x0"] <= ax + 4
                and w["text"].lower() not in label_drop
            )
            if not label or summary_label_re.search(label):
                col_cand[ax] = None
                continue
            col_cand[ax] = _pdf_match_candidate(_pdf_name_tokens(label), cand_list)
        if not any(col_cand.values()):
            continue

        for pct_words, line in total_rows:
            precinct = " ".join(w["text"] for w in pct_words)
            for w in line:
                v = _is_int(w["text"])
                if v is None or w["x0"] <= 300:
                    continue
                # nearest value-column anchor (values sit exactly at an anchor)
                ax = None
                for a in anchors:
                    if abs(a - w["x0"]) <= 6:
                        ax = a
                        break
                if ax is None:
                    continue
                disp = col_cand.get(ax)
                if not disp:
                    continue
                key = (precinct, office, district, norm_name(disp))
                sums[key] += v
                meta[key] = (disp, "")
    pdf.close()

    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_mendocino_pdf(ref, county, path):
    """Parse Mendocino County's upright precinct-major SOV PDF.

    Layout: a running header (page X, registered-voters/precincts-reporting
    totals) then, for each precinct, a ``<id> <name>  N of M registered voters``
    header followed by every contest on that precinct's ballot. Each contest is
    a title line (``GOVERNOR`` or ``UNITED STATES REPRESENTATIVE 1st
    Congressional District`` -- office + district on one line, parsed by
    ``parse_office``), a ``Choice Party Absentee Voting Election Day Voting
    Total`` column header, then one row per candidate::

        RICHARD T. MINNER   NPP   0 0.00%  0 0.00%  0 0.00%
        Michael A Petrelis (W) 0 0.00%  0 0.00%  0 0.00%

    i.e. ``[name...] [party | (W)] [abs abs% ed ed% total total%]``. The token
    before the six trailing numerics is the party code (or ``(W)`` for a
    write-in); the 5th trailing numeric is the Total. A contest for one
    precinct spans pages -- the precinct header and contest title are reprinted
    on each continuation page -- so state (current precinct / contest) is
    carried across pages and a precinct header simply refreshes it.

    Summary rows (``Cast Votes:``, ``Undervotes:``, ``Overvotes:``,
    ``Un-Qualified Write-Ins:``) are skipped: either they have fewer than six
    trailing numerics or the token before them is not a party code / ``(W)``.
    Only the ``votes`` (Total) column is emitted (the county-level file has no
    vote-type breakdowns).
    """
    import pdfplumber
    mset = ref.contests.get(county, set())
    # Precinct header: "<6+ digit id> <name ...>  N of M registered voters = T%"
    precinct_re = re.compile(
        r"^(\d{3,}\s+\S.*?)\s+\d+\s+of\s+\d+\s+registered\s+voters", re.I)
    num_re = re.compile(r"^[\d,]+(?:\.\d+)?%?$")

    pdf = pdfplumber.open(path)
    rows_out = []
    cur_precinct = None
    cur_od = None
    prev_t = ""  # the line immediately preceding the current one
    for p in pdf.pages:
        words = p.extract_words(use_text_flow=False)
        lines = defaultdict(list)
        for w in words:
            lines[round(w["top"])].append(w)
        for y in sorted(lines):
            toks = [w["text"] for w in sorted(lines[y], key=lambda w: w["x0"])]
            t = " ".join(toks).strip()
            if not t:
                continue
            m = precinct_re.match(t)
            if m:
                cur_precinct = m.group(1).strip()
                cur_od = None
                prev_t = ""
                continue
            # The "Choice Party Absentee Voting ... Total" column header marks
            # the start of a contest's candidate rows; the line just above it is
            # the contest title. A precinct's ballot carries local contests and
            # measures AFTER the statewide ones -- their titles don't resolve to
            # a statewide (office, district), so cur_od is set to None and their
            # rows (incl. measure YES/NO) are dropped instead of leaking into the
            # prior statewide contest.
            if t.startswith("Choice"):
                od = parse_office(prev_t)
                cur_od = od if (od and od in mset) else None
                prev_t = ""
                continue
            if cur_precinct is not None and cur_od is not None and len(toks) >= 7:
                # Candidate row: the last six tokens are [abs abs% ed ed% total
                # total%]. The token at -7 is the party code (or "(W)" for a
                # write-in) -- EXCEPT for non-partisan contests (Superintendent
                # of Public Instruction), whose rows have no party column:
                #   "AL MURATSUCHI  18 7.86%  0 0.00%  18 7.73%"
                # so the name is toks[:-6] and party is blank. Summary rows
                # ("Cast Votes:", "Undervotes:", ...) are dropped by the ':'
                # filter (no candidate name contains a colon) or by having too
                # few trailing numerics.
                tail = toks[-6:]
                if all(num_re.match(x) for x in tail):
                    pcode = toks[-7] if len(toks) >= 7 else None
                    if pcode == "(W)":
                        party_raw = ""
                        name = " ".join(toks[:-7]).strip()
                        # Skip write-ins that aren't a county-file candidate
                        # (0-vote / unqualified write-ins would otherwise be
                        # EXTRA).
                        county_names = set(ref.by_key.get(cur_od, {}).values())
                        if ref.canonical_name(cur_od[0], cur_od[1], name) in county_names:
                            total = int(tail[4].replace(",", "").rstrip("%"))
                            _emit(ref, county, cur_precinct, cur_od[0], cur_od[1],
                                  name, party_raw, total, rows_out)
                    elif pcode is not None and pcode.upper() in PARTY_CODE_MAP:
                        name = " ".join(toks[:-7]).strip()
                        if name and ":" not in name:
                            total = int(tail[4].replace(",", "").rstrip("%"))
                            _emit(ref, county, cur_precinct, cur_od[0], cur_od[1],
                                  name, pcode, total, rows_out)
                    else:
                        name = " ".join(toks[:-6]).strip()
                        if name and ":" not in name:
                            total = int(tail[4].replace(",", "").rstrip("%"))
                            _emit(ref, county, cur_precinct, cur_od[0], cur_od[1],
                                  name, "", total, rows_out)
            prev_t = t
    pdf.close()
    return rows_out


# ---------------------------------------------------------------------------
# Modoc — upright precinct-major "Summary Results Report" PDF.
# ---------------------------------------------------------------------------

def _modoc_resolve(ref, county, mset, title):
    """Resolve a Modoc contest title to a (office, district) in the county set.

    Two statewide titles omit the district ("MEMBER, STATE BOARD OF
    EQUALIZATION", "MEMBER OF THE STATE ASSEMBLY"); ``parse_office`` returns
    None for those, so the district is inferred from the single matching
    contest in the county reference. Titles that resolve to a contest NOT in
    this county's set (e.g. the extraneous "U.S. REPRESENTATIVE, DISTRICT 1"
    Modoc prints for every precinct even though the county file only carries
    CD2) return None so their rows are dropped.
    """
    od = parse_office(title)
    if od:
        return od if od in mset else None
    t = title.upper()
    for pat, office in ((r"BOARD\s+OF\s+EQUAL", "Board of Equalization"),
                       (r"STATE\s+ASSEMBLY|\bASSEMBLY\b", "State Assembly")):
        if re.search(pat, t):
            ds = [d for (o, d) in mset if o == office]
            if len(ds) == 1:
                return (office, ds[0])
    return None


def parse_modoc_pdf(ref, county, path):
    """Parse Modoc County's upright precinct-major "Summary Results Report" PDF.

    Layout (189 pp): each page carries a running header ("Summary Results
    Report ... June 2, 2026 <county> County") then the **precinct name** alone
    at top ~89 -- a bare name line with no id and no "registered voters"
    suffix, reprinted on every page of the precinct. Each contest is a title
    line ("GOVERNOR", "UNITED STATES REPRESENTATIVE, DISTRICT 1", "MEMBER,
    STATE BOARD OF EQUALIZATION", "MEMBER OF THE STATE ASSEMBLY", ...) followed
    by "Vote For 1", a stacked column header ("TOTAL VOTE % Mail Provisional"
    / "Election Vote by" / "Day Mail") and one row per candidate::

        MARGARET TROWE 0 0.00% 0 0 0 0
        TONY K. THURMOND 1 1.39% 0 1 0 0

    i.e. ``[name...] [total total% ed mail vbm provisional]`` -- six trailing
    numerics with the **Total first** (tail[0]), and **no party token** (party is
    resolved from the county reference via ``canonical_party``). A precinct's
    contests span pages; the precinct name and contest title are reprinted on
    each continuation page, so state is carried across pages and a precinct
    line simply refreshes it (and clears the contest, since the title always
    reprints below it).

    The contest is read from the line immediately above each "Vote For N"
    (tracked via ``prev_t``). Modoc's SOV lists BOTH congressional districts
    (CD1 Gallagher and CD2 Huffman) for every precinct even though the county
    file only carries CD2; CD1 resolves to ("U.S. House","1"), which is not in
    this county's contest set, so ``_modoc_resolve`` returns None and its rows
    are dropped. "Write-In Totals" rows are skipped (not real candidates);
    local offices/measures (Judge of the Superior Court, County
    Superintendent, Supervisor, Assessor/Recorder, ...) fail resolution and
    are skipped.
    """
    import pdfplumber
    mset = ref.contests.get(county, set())
    header_re = re.compile(rf"\b{re.escape(county)}\s+County\b")
    votefor_re = re.compile(r"^Vote\s+For\s+\d+$", re.I)
    num_re = re.compile(r"^[\d,]+(?:\.\d+)?%?$")
    pdf = pdfplumber.open(path)
    rows_out = []
    cur_precinct = None
    cur_od = None
    prev_t = ""
    expect_precinct = False
    for p in pdf.pages:
        words = p.extract_words(use_text_flow=False)
        lines = defaultdict(list)
        for w in words:
            lines[round(w["top"])].append(w)
        for y in sorted(lines):
            toks = [w["text"] for w in sorted(lines[y], key=lambda w: w["x0"])]
            t = " ".join(toks).strip()
            if not t:
                continue
            # Precinct: the line right after the "<county> County" page header.
            if expect_precinct:
                cur_precinct = t
                cur_od = None
                expect_precinct = False
                prev_t = ""
                continue
            if header_re.search(t):
                expect_precinct = True
                continue
            # Contest title: the line immediately above "Vote For N".
            if votefor_re.match(t):
                cur_od = _modoc_resolve(ref, county, mset, prev_t)
                prev_t = ""
                continue
            # Candidate row: six trailing numerics; the first is the Total.
            if cur_precinct is not None and cur_od is not None and len(toks) >= 7:
                tail = toks[-6:]
                if all(num_re.match(x) for x in tail):
                    name = " ".join(toks[:-6]).strip()
                    if (name and ":" not in name
                            and "write-in" not in name.lower()
                            and not is_summary_name(name)):
                        total = int(tail[0].replace(",", "").rstrip("%"))
                        _emit(ref, county, cur_precinct, cur_od[0], cur_od[1],
                              name, "", total, rows_out)
            prev_t = t
    pdf.close()
    return rows_out


# ---------------------------------------------------------------------------
# Yolo — 180-degree-rotated "District Results Report" PDF (Butte-family layout).
# ---------------------------------------------------------------------------

def parse_yolo_pdf(ref, county, path, start_page=18):
    """Parse Yolo County's 180-degree-rotated precinct SOV PDF.

    Same rotated family as Butte/Sierra (candidate names upside-down,
    character-reversed, read bottom-to-top; precinct id upright at ``x0<110``;
    integer vote values) and shares Butte's structure -- a 18-page countywide
    "Cumulative Results Report" front matter, then "Cumulative Totals" with the
    contest **reprinted under overlapping group headers** (Congressional /
    Senate / Assembly / Supervisorial / City districts), each re-listing its
    member precincts with identical values, plus subtotal rows. So votes are
    **deduplicated** by (precinct, office, district, norm_name) -- first
    occurrence kept -- rather than summed, and non-numeric left-edge labels
    (group headers, subtotals) are skipped.

    Two ways Yolo is SIMPLER than Butte, so it does not reuse ``parse_butte_pdf``
    directly:

    * The **contest title is reprinted on every page** (top ~49, "Governor",
      "United States Representative 4th District", ...). The contest is read
      straight from the title via ``parse_office`` -- no per-page inference from
      candidate names. A page whose title does not resolve to a statewide
      contest in this county's set (local offices, ballot measures, the
      trailing "1% Manual Tally" report, or "*** End of report ***") is skipped,
      and "*** End of report ***" stops processing.

    * **No right-aligned "Total Votes" column and no stray second precinct-id
      column.** Candidate vote values sit a fixed ~23pt RIGHT of their rotated
      label's xmin, so a value maps to the column with the largest label xmin <=
      its x0 (offset ~23pt, well under the ~49pt column pitch). The Butte
      parser's midpoint-boundary + ``owner_xmin-12`` guard (built for Butte's
      right-aligned Total Votes and stray ids) misassigns the first column on
      continuation pages where adjacent columns are <~46pt apart; the simple
      nearest-left rule avoids that.

    * **Accent-glyph columns.** A candidate whose name has an accented glyph
      (Gretha Solórzano) has NO extractable rotated header anywhere in the
      document -- the column's data values exist but its label doesn't. So a
      two-pass parse is used: pass 1 collects every candidate display name whose
      rotated header IS extracted, per contest; the county-file candidates never
      detected are the "missing" ones (exactly one for Yolo -- Solórzano). Pass 2
      maps each value to the largest label xmin <= its x0; if the value sits
      >~42pt right of that label (i.e. one full column past it, where a
      missing-header column lives) it is an orphan and is assigned to the one
      missing candidate. (The orphan would otherwise fold onto the prior
      candidate and surface as a dedup conflict.)
    """
    import pdfplumber
    contests = ref.contests.get(county, set())
    cand_index = {od: [(frozenset(mk.split()), disp)
                      for mk, disp in ref.by_key.get(od, {}).items()]
                  for od in contests}

    def _page_state(p):
        """Return (lines, title, od, data_top, band) for an SOV contest page,
        or None for pages to skip (and the sentinel 'END' when done)."""
        words = p.extract_words(use_text_flow=False)
        lines = defaultdict(list)
        for w in words:
            lines[round(w["top"])].append(w)
        title = None
        for y in sorted(lines):
            if y <= 30:
                continue
            if y > 100:
                break
            t = " ".join(w["text"] for w in sorted(lines[y], key=lambda w: w["x0"])).strip()
            if t:
                title = t
                break
        if not title:
            return None
        if "end of report" in title.lower():
            return "END"
        od = parse_office(title)
        if od is None or od not in cand_index:
            return None  # local office / measure / 1% manual tally page
        data_top = None
        for y in sorted(lines):
            txt = " ".join(w["text"] for w in sorted(lines[y], key=lambda w: w["x0"])).strip()
            if txt.split(" ", 1)[0].lower() == "precinct":
                data_top = y
                break
        if data_top is None:
            return None
        blocks = _pdf_cols_to_blocks(_pdf_rotated_cols(p))
        band = [b for b in blocks if min(c["top"] for c in b["chars"]) < data_top]
        return lines, title, od, data_top, band

    pdf = pdfplumber.open(path)
    pages = pdf.pages[start_page:]

    # Pass 1: collect detected candidate display names per contest, to find
    # the candidate(s) whose rotated header is never extracted (accent glyph).
    detected = {od: set() for od in contests}
    for p in pages:
        st = _page_state(p)
        if st == "END":
            break
        if st is None:
            continue
        lines, _title, od, _data_top, band = st
        for b in band:
            name = _pdf_read_block(b, "bt")
            if _SIERRA_SUMMARY_RE.search(name):
                continue
            toks = _pdf_name_tokens(name)
            disp = _pdf_match_candidate(toks, cand_index[od]) if toks else None
            if disp:
                detected[od].add(norm_name(disp))
    missing = {od: [disp for (_mk, disp) in cand_index[od]
                    if norm_name(disp) not in detected[od]]
               for od in contests}

    # Pass 2: assign votes, mapping orphan columns to the missing candidate.
    values = {}   # (precinct, office, district, norm_name) -> votes (deduped)
    meta = {}     # key -> display name
    conflicts = []
    for p in pages:
        st = _page_state(p)
        if st == "END":
            break
        if st is None:
            continue
        lines, _title, od, data_top, band = st
        office, district = od
        cand_list = cand_index[od]
        miss = missing[od][0] if len(missing[od]) == 1 else None
        cols = []  # (xmin, disp or None)
        for b in band:
            name = _pdf_read_block(b, "bt")
            if _SIERRA_SUMMARY_RE.search(name):
                cols.append((b["xmin"], None))
                continue
            toks = _pdf_name_tokens(name)
            cols.append((b["xmin"], _pdf_match_candidate(toks, cand_list) if toks else None))
        cols.sort(key=lambda c: c[0])
        if not any(d for _, d in cols):
            continue
        for y in sorted(lines):
            if y <= data_top:
                continue
            line = sorted(lines[y], key=lambda w: w["x0"])
            pct_words = [w for w in line if w["x0"] < 110]
            if not pct_words:
                continue
            precinct = " ".join(w["text"] for w in pct_words).strip()
            if not re.match(r"^\d{3,}$", precinct):
                continue
            for w in line:
                if w["x0"] < 110:
                    continue
                s = w["text"].replace(",", "").rstrip("%")
                if "." in s:
                    continue
                try:
                    v = int(s)
                except ValueError:
                    continue
                # Nearest label to the LEFT of the value (values sit ~23pt right
                # of their label). If the value is >42pt past that label it is
                # an orphan column whose header was never extracted.
                owner = None
                owner_xmin = None
                for xmin, disp in cols:
                    if xmin <= w["x0"]:
                        owner = disp
                        owner_xmin = xmin
                    else:
                        break
                if owner is None:
                    continue
                if owner is not None and owner_xmin is not None \
                        and w["x0"] - owner_xmin > 42 and miss:
                    owner = miss  # missing-header (accent glyph) column
                if not owner:
                    continue
                key = (precinct, office, district, norm_name(owner))
                if key not in values:
                    values[key] = v
                    meta[key] = owner
                elif values[key] != v:
                    conflicts.append((precinct, office, district, owner,
                                      values[key], v))
    pdf.close()

    if conflicts:
        print(f"  [{county.lower()}] {len(conflicts)} value conflicts (kept first):")
        for c in conflicts[:10]:
            print(f"    {c}")

    rows_out = []
    for (precinct, office, district, _nn), votes in values.items():
        _emit(ref, county, precinct, office, district,
              meta[(precinct, office, district, _nn)], "", votes, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# Stanislaus — one precinct per sheet, "Precinct Results Report" workbook.
# ---------------------------------------------------------------------------

def parse_stanislaus_xlsx(ref):
    """Stanislaus exports one worksheet per precinct (Sheet2..Sheet96, after the
    'Disclaimer' and 'Document map' sheets). Each sheet stacks its contests;
    candidate rows are sparse (merged-cell gaps): name in col 0, party in col 5
    (always blank -- party comes from the county ref), Total in col 15 (located
    dynamically from the 'Choice' header row). Vote-type columns (Vote Center /
    Vote by Mail) are ignored. Contests vary per precinct (different CD/AD).
    """
    county = "Stanislaus"
    path = SOURCE_DIR / "2026 Stanislaus County Precinct Results-6-25-2026 10-08-24 AM.xlsx"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_out = []
    for name in wb.sheetnames[2:]:  # skip 'Disclaimer', 'Document map'
        ws = wb[name]
        precinct = None
        cur_od = None
        total_col = None
        for row in ws.iter_rows(values_only=True):
            c0 = row[0]
            if c0 is None:
                continue
            c0s = str(c0).strip()
            # precinct id row: 6-digit id in col 0, "registered voters" in col 13
            if (re.match(r"^\d{6}$", c0s) and len(row) > 13
                    and row[13] and "registered voters" in str(row[13])):
                precinct = c0s
                cur_od = None
                continue
            # contest title row
            if "Vote for ONE" in c0s:
                cur_od = parse_office(c0s)
                total_col = None
                continue
            # column header row -- locate the Total column
            if c0s == "Choice":
                for j, v in enumerate(row):
                    if v == "Total":
                        total_col = j
                        break
                continue
            # candidate row
            if cur_od and precinct and total_col is not None:
                if c0s.endswith(":") or "write-in" in c0s.lower() or is_summary_name(c0s):
                    continue
                total = row[total_col]
                if total is None:
                    continue
                party = row[5] if len(row) > 5 else ""
                _emit(ref, county, precinct, cur_od[0], cur_od[1],
                      c0s, party or "", total, rows_out)
    return rows_out


# ---------------------------------------------------------------------------
# San Mateo — clean long CSV (one row per precinct x candidate).
# ---------------------------------------------------------------------------

def parse_san_mateo_csv(ref):
    """San Mateo exports a flat CSV: one row per precinct x candidate with
    columns Precinct_name, Contest_title, candidate_name, Candidate_Type
    ('C' candidate / 'W' write-in), Party_Code, total_votes. Contest_title uses
    a comma style ('Member, State Board of Equalization, District 2',
    'U.S. Representative, District 15') that ``parse_office`` handles. The
    'Write-in' aggregate row duplicates the named write-ins' total and is
    dropped via ``is_summary_name``; named write-ins are emitted. Split_name
    is always empty, so Precinct_name alone is the precinct id.
    """
    county = "San Mateo"
    path = SOURCE_DIR / "2026 San Mateo County 51_ElectionResults_FINAL.csv"
    rows_out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("candidate_name") or "").strip()
            if not name or is_summary_name(name):
                continue
            od = parse_office(row.get("Contest_title", ""))
            if od is None or od not in ref.contests.get(county, set()):
                continue
            try:
                votes = int(row.get("total_votes") or 0)
            except ValueError:
                continue
            precinct = (row.get("Precinct_name") or "").strip()
            if not precinct:
                continue
            party = row.get("Party_Code", "") or ""
            _emit(ref, county, precinct, od[0], od[1], name, party, votes, rows_out)
    return rows_out


# Solano "Precinct Results Report" PDF (upright, precinct-major, contest-major
# within a page). 160 precincts; each precinct runs through ~16 contests (11
# statewide). A single page often holds a whole contest plus the start of the
# next, so the parse is line-driven, not page-driven.
_SOLANO_PCT_RE = re.compile(r"^(\d+)\s+\d+\s+of\s+[\d,]+\s+registered voters")
_SOLANO_CONT_RE = re.compile(r"^(.+?)\s*-\s*Vote for ONE")
_SOLANO_INT_RE = re.compile(r"^\d+$")
# Per-contest summary rows ("Cast Votes:", "Undervotes:", "Overvotes:",
# "Unresolved write-in votes:") carry four integer columns like a candidate
# row; is_summary_name does not catch them, so skip them explicitly.
_SOLANO_SUMMARY_LABELS = {
    "CAST VOTES", "UNDERVOTES", "OVERVOTES", "UNRESOLVED WRITE-IN VOTES",
    "RESOLVED WRITE-IN VOTES", "WRITE-INS", "WRITE-IN",
}


def parse_solano_pdf(ref, county, path):
    """Solano's upright precinct-major "Precinct Results Report" PDF.

    Layout: per-precinct, per-contest tables. Each candidate row is
    ``NAME [party] <in-person> <%> <vbm> <%> <provisional> <%> <total> <%>`` --
    exactly four integer vote counts, of which the last is the Total (the only
    column emitted; the 2026 county file has no vote-type breakdowns). A page
    may contain a full contest followed by the start of the next, and a
    precinct's contests span many pages, so we walk every line in order:
    a ``<id> N of M registered voters`` line sets the sticky precinct, a
    ``<title> - Vote for ONE`` line sets the current contest (via
    ``parse_office``; non-statewide -> skipped), and candidate rows accumulate
    into ``(precinct, contest, candidate)``. Write-ins are suffixed ``(W)``,
    which is stripped before canonicalization. Contest summary rows are
    dropped via ``is_summary_name`` plus ``_SOLANO_SUMMARY_LABELS``.
    """
    import pdfplumber

    pdf = pdfplumber.open(path)
    sums = defaultdict(int)
    meta = {}
    precinct = None
    contest = None  # (office, district) or None (skip candidate rows)
    for page in pdf.pages:
        text = page.extract_text(use_text_flow=False) or ""
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                continue
            m = _SOLANO_PCT_RE.match(s)
            if m:
                precinct = m.group(1)
                continue
            m = _SOLANO_CONT_RE.match(s)
            if m:
                od = parse_office(m.group(1).strip())
                contest = od if (od and od in ref.contests.get(county, set())) else None
                continue
            if "Choice" in s and "Total" in s:
                continue  # column header row
            if contest is None:
                continue
            toks = s.split()
            ints = [t for t in toks if _SOLANO_INT_RE.match(t)]
            if len(ints) < 4:
                continue  # not a candidate row (boilerplate / wrapped title)
            name_toks = []
            for t in toks:
                if _SOLANO_INT_RE.match(t):
                    break
                name_toks.append(t)
            name = " ".join(name_toks).strip()
            if not name:
                continue
            name = re.sub(r"\s*\(W(?:/I)?\)\s*$", "", name).strip()
            label = name.rstrip(":").strip().upper()
            if is_summary_name(name) or label in _SOLANO_SUMMARY_LABELS:
                continue
            total = int(ints[-1])
            office, district = contest
            key = (precinct, office, district, norm_name(name))
            sums[key] += total
            meta[key] = (name, "")
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


# Shasta upright precinct-major "Final Official Precinct Results" PDF. Each
# candidate row is ``NAME <vbm> <vbm%> <election-day> <ed%> <total> <total%>``
# -- three integer vote counts (Vote By Mail / Election Day Voting / Total),
# of which the last is Total (the only column emitted). A precinct's contests
# span many pages and the precinct line is reprinted atop every page, so the
# parse is line-driven: a ``<code> - <split> <cast> of <registered> registered
# voters`` line sets the sticky precinct, a ``<title> - Vote for One`` line
# sets the current contest (non-statewide -> skipped), and candidate rows
# accumulate. Write-ins are suffixed ``(W)``; party is not printed in the
# precinct detail (resolved from the county reference).
_SHASTA_PCT_RE = re.compile(r"^(.+?)\s+\d[\d,]*\s+of\s+[\d,]+\s+registered voters")
_SHASTA_CONT_RE = re.compile(r"^(.+?)\s+-\s+Vote for One\s*$", re.I)
_SHASTA_VOTE_RE = re.compile(r"^[\d,]+$")
_SHASTA_SUMMARY_LABELS = {
    "CAST VOTES", "UNDERVOTES", "OVERVOTES", "TIMES CAST", "BALLOTS CAST",
    "UNRESOLVED WRITE-IN VOTES", "RESOLVED WRITE-IN VOTES", "WRITE-INS", "WRITE-IN",
}


def parse_shasta_pdf(ref, county, path):
    """Shasta's upright precinct-major ``Final Official Precinct Results`` PDF."""
    import pdfplumber

    pdf = pdfplumber.open(path)
    sums = defaultdict(int)
    meta = {}
    precinct = None
    contest = None  # (office, district) or None (skip candidate rows)
    for page in pdf.pages:
        text = page.extract_text(use_text_flow=False) or ""
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                continue
            m = _SHASTA_PCT_RE.match(s)
            if m:
                precinct = m.group(1).strip()
                continue
            m = _SHASTA_CONT_RE.match(s)
            if m:
                od = parse_office(m.group(1).strip())
                contest = od if (od and od in ref.contests.get(county, set())) else None
                continue
            if "Choice" in s and "Total" in s:
                continue  # column header row
            if contest is None or precinct is None:
                continue
            # The page footer ("Page N of 1195") is printed at the same y as the
            # last candidate row on a page and overlaps a percentage column, so
            # pdfplumber merges it into that candidate line (e.g. "MAX FOMIN 0
            # P0a.0g0e% 19 of 1195 0 0.00% 0 0.00%"). Strip the "N of N" footer
            # fragment -- the garbled percentage token it leaves behind is not a
            # pure-digit vote, so the three real vote counts parse cleanly. No
            # candidate row legitimately contains "N of N" (precinct lines, the
            # only "of"-bearing rows, are matched and skipped above).
            s = re.sub(r"\s+\d+\s+of\s+\d+\s*", " ", s)
            toks = s.split()
            votes = [t for t in toks if _SHASTA_VOTE_RE.match(t)]
            if len(votes) != 3:
                continue  # not a candidate row (boilerplate / wrapped title)
            name_toks = []
            for t in toks:
                if _SHASTA_VOTE_RE.match(t):
                    break
                name_toks.append(t)
            name = " ".join(name_toks).strip()
            if not name:
                continue
            name = re.sub(r"\s*\(W(?:/I)?\)\s*$", "", name).strip()
            label = name.rstrip(":").strip().upper()
            if is_summary_name(name) or label in _SHASTA_SUMMARY_LABELS:
                continue
            total = int(votes[-1].replace(",", ""))
            office, district = contest
            key = (precinct, office, district, norm_name(name))
            sums[key] += total
            meta[key] = (name, "")
    rows_out = []
    for (precinct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(precinct, office, district, _nn)]
        _emit(ref, county, precinct, office, district, name, party_raw, votes, rows_out)
    return rows_out


# Calaveras "Official Precinct Results" xlsx. One sheet per precinct (plus a
# "Document map" index). Each sheet is a precinct-major table: a precinct line
# ``<id> ... <cast> of <registered> registered voters`` (id at col0, the
# registered-voter note at col17), then for each contest an all-caps title row,
# a ``Choice / Party / ... / Total`` header row, candidate rows (name col0,
# party code col3, Total vote col17), and ``Cast Votes:``/``Undervotes:``/
# ``Overvotes:`` summary rows. Candidate rows are identified by col3 being a
# string (a party code, "" for the non-partisan SPI) AND col17 being a number --
# title/summary rows have col3 None, and the header has col17 == "Total" (str).
# Party is not emitted directly (canonicalized from the county reference).
def parse_calaveras_xlsx(ref, county, path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_out = []
    for sn in wb.sheetnames:
        if sn == "Document map":
            continue
        ws = wb[sn]
        precinct = None
        contest = None  # (office, district) or None (skip candidate rows)
        for r in ws.iter_rows(values_only=True):
            c0 = r[0] if r else None
            c3 = r[3] if len(r) > 3 else None
            c17 = r[17] if len(r) > 17 else None
            # Precinct line: col17 carries "N of M registered voters".
            if isinstance(c17, str) and "registered voters" in c17.lower():
                if isinstance(c0, str) and c0.strip():
                    precinct = c0.strip()
                    contest = None
                continue
            # Contest title / summary rows: col3 is None. An all-caps col0 is a
            # contest title (parse_office -> statewide or skip); summary labels
            # ("Cast Votes:", "Undervotes:", "Overvotes:") are not all-caps and
            # leave the current contest unchanged.
            if c3 is None:
                if isinstance(c0, str):
                    s = c0.strip()
                    if s and s.isupper() and s != "CHOICE":
                        od = parse_office(s)
                        contest = od if (od and od in ref.contests.get(county, set())) else None
                continue
            # Candidate row: col3 is a string (party code, "" for SPI) and col17
            # is a numeric Total. The header row has col17 == "Total" (str), so
            # it is excluded here.
            if not isinstance(c17, (int, float)) or isinstance(c17, bool):
                continue
            if contest is None or precinct is None:
                continue
            if not isinstance(c0, str):
                continue
            name = re.sub(r"\s*\(W(?:/I)?\)\s*$", "", c0.strip()).strip()
            if not name or is_summary_name(name):
                continue
            _emit(ref, county, precinct, contest[0], contest[1], name,
                  str(c3).strip(), int(c17), rows_out)
    return rows_out


# per-precinct "Cumulative Totals" sheet plus four per-district sheets (Vote by
# Mail / In Person / Provisional / Grand Totals). Governor and Lieutenant
# Governor also get a per-precinct "Write-in Tally" sheet. Only per-precinct
# rows are wanted; per-district rows are filtered by the precinct-id regex.
_NEVADA_PCT_RE = re.compile(r"^CP\d+-")
_NEVADA_META_HEADERS = {
    "CUMULATIVE TOTALS", "WRITE-IN TALLY", "REGISTRATION", "BALLOTS CAST",
    "TURNOUT (%)", "TURNOUT",
}


def parse_nevada_xlsx(ref, county, path):
    """Nevada County "District Results" workbook.

    123 sheets, grouped five-per-contest (the per-precinct "Cumulative
    Totals" sheet first, then Vote by Mail / In Person / Provisional / Grand
    Totals per-district sheets). The contest title sits at row 2; the column
    header row (containing ``Registration`` and ``Ballots Cast`` plus candidate
    names) is found dynamically (row 5 on cumulative sheets, row 4 on write-in
    sheets). Candidate columns are those with a non-None string header that is
    not a metadata label; the vote for a candidate lives in the SAME column of
    each data row (interleaved percent columns have None headers and are
    skipped). Data rows whose col0 is a precinct id (``CP\\d+-``) are summed
    per ``(precinct, contest, candidate)``; per-district summary rows (``Nevada
    County``, ``Supervisorial District N``, ``Grand Totals`` ...) do not match
    and are dropped. The Governor / Lieutenant Governor "Write-in Tally"
    sheets (qualified write-ins like Butch Ware / Che Ahn) are picked up too --
    their candidates are distinct from the main sheet's, so no double-count.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sums = defaultdict(int)
    meta = {}
    for sn in wb.sheetnames:
        ws = wb[sn]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) <= 2 or not rows[2] or not rows[2][0]:
            continue
        od = parse_office(str(rows[2][0]))
        if od is None or od not in ref.contests.get(county, set()):
            continue  # statewide-only; local offices / measures skipped
        # header row = first row in the top 10 carrying "Registration"
        hdr_idx = None
        for i in range(min(10, len(rows))):
            r = rows[i]
            if r and any(isinstance(c, str) and c.strip().upper() == "REGISTRATION" for c in r):
                hdr_idx = i
                break
        if hdr_idx is None:
            continue
        hdr = rows[hdr_idx]
        cand_cols = []  # (col_index, name)
        for c, val in enumerate(hdr):
            if not isinstance(val, str):
                continue
            label = val.strip()
            if not label or label.upper() in _NEVADA_META_HEADERS:
                continue
            cand_cols.append((c, label))
        if not cand_cols:
            continue
        office, district = od
        for r in rows[hdr_idx + 1:]:
            if not r or r[0] is None:
                continue
            pct = str(r[0]).strip()
            if not _NEVADA_PCT_RE.match(pct):
                continue
            for c, name in cand_cols:
                v = r[c] if c < len(r) else None
                if v is None:
                    continue
                try:
                    votes = int(v)
                except (ValueError, TypeError):
                    continue
                if is_summary_name(name):
                    continue
                key = (pct, office, district, norm_name(name))
                sums[key] += votes
                meta[key] = (name, "")
    rows_out = []
    for (pct, office, district, _nn), votes in sums.items():
        name, party_raw = meta[(pct, office, district, _nn)]
        _emit(ref, county, pct, office, district, name, party_raw, votes, rows_out)
    return rows_out


def parse_orange_txt(ref, county, path):
    """Orange County SOVC tab-delimited flat export (one row per precinct x
    candidate). Columns used: Precinct (0), Contest Title (6), Choice Name1
    (9), Choice Party (11), Total Votes (12). Contest titles use the all-caps
    Orange form ("UNITED STATES REPRESENTATIVE 46th District",
    "MEMBER OF THE STATE ASSEMBLY 68th District", "STATE SENATOR 34th
    District", "Member, State Board of Equalization 4th District") that
    ``parse_office`` resolves. Qualified write-ins (BUTCH WARE, CHE AHN, TONY
    S CASTRO, ...) appear as named candidate rows (Choice ID 0) and are
    emitted; the "Rejected write-ins" / "Unassigned write-ins" summary rows
    are dropped. Only ``Total Votes`` is emitted (the county file has no
    vote-type breakdowns). The leading header row (".Precinct" / "Contest
    Title") is skipped.
    """
    rows_out = []
    with open(path, newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 13:
                continue
            if row[6] == "Contest Title":  # header row
                continue
            precinct = row[0].strip()
            if not precinct:
                continue
            name = row[9].strip()
            if not name or is_summary_name(name) or "write-in" in name.lower():
                continue
            od = parse_office(row[6].strip())
            if od is None or od not in ref.contests.get(county, set()):
                continue
            try:
                votes = int(row[12])
            except ValueError:
                continue
            party = row[11].strip() if len(row) > 11 else ""
            _emit(ref, county, precinct, od[0], od[1], name, party, votes, rows_out)
    return rows_out


PARSERS = {
    "sacramento": parse_sacramento,
    "humboldt": parse_humboldt,
    "alameda": lambda ref: parse_precinctcanvass(ref, "Alameda", SOURCE_DIR / "2026 Alameda County, CA precinct-level results/Alameda-2026-Primary-PrecinctCanvass.xlsx"),
    "kings": lambda ref: parse_precinctcanvass(ref, "Kings", SOURCE_DIR / "2026 Kings County, CA precinct-level results/Kings-2026-Primary-SOVC-by-precinct.xlsx"),
    "monterey": lambda ref: parse_precinctcanvass(ref, "Monterey", SOURCE_DIR / "2026 Monterey County, CA precinct-level results.xlsx"),
    "sonoma": lambda ref: parse_precinctcanvass(ref, "Sonoma", SOURCE_DIR / "2026 Sonoma County, CA precinct-level results/Sonoma-2026-Primary-SOVC-by-precinct.xlsx"),
    "san_diego": lambda ref: parse_precinctcanvass(ref, "San Diego", Path("/tmp/sd2026/Statement of Votes Cast 202606/Statement of Votes Cast 202606.xlsx")),
    "madera": lambda ref: parse_precinctcanvass(ref, "Madera", SOURCE_DIR / "2026 Madera County, CA precinct-level results/Madera-2026-Primary-SOVC-by-precinct.xlsx"),
    "yuba": lambda ref: parse_precinctcanvass(ref, "Yuba", SOURCE_DIR / "2026 Yuba County, CA precinct-level results/Yuba-2026-Primary-SOV-by-precinct.xlsx"),
    "ventura": lambda ref: parse_precinctcanvass(ref, "Ventura", SOURCE_DIR / "2026 Ventura County District-Canvass-by-Precinct.xlsx", dedup=True),
    # Page-format ("Page: N of M") SOVC exports
    "colusa": lambda ref: parse_pageformat(ref, "Colusa", SOURCE_DIR / "2026 Colusa County, CA precinct-level results/Colusa-2026-Primary-SOVC.xlsx"),
    "fresno": lambda ref: parse_pageformat(ref, "Fresno", SOURCE_DIR / "2026 Fresno County, CA precinct-level results/Fresno-2026-Primary-SOVC-by-precinct.xlsx"),
    "inyo": lambda ref: parse_pageformat(ref, "Inyo", SOURCE_DIR / "2026 Inyo County, CA precinct-level results/Inyo-2026-Primary-SOVC.xlsx"),
    "san_francisco": lambda ref: parse_pageformat(ref, "San Francisco", SOURCE_DIR / "2026 San Francisco County, CA precinct-level results/SanFrancisco-2026-Primary-SOV-by-precinct.xlsx"),
    "san_luis_obispo": lambda ref: parse_pageformat(ref, "San Luis Obispo", SOURCE_DIR / "2026 San Luis Obispo County, CA precinct-level results/SanLuisObispo-2026-Primary-SOVC-by-precinct.xlsx"),
    "tulare": lambda ref: parse_pageformat(ref, "Tulare", SOURCE_DIR / "2026 Tulare County, CA precinct-level results/Tulare-2026-Primary-SOVC-by-precinct.xlsx"),
    "sutter": lambda ref: parse_pageformat(ref, "Sutter", SOURCE_DIR / "2026 Sutter County, CA precinct-level results/Sutter-2026-Primary-SOV-by-Precinct.xlsx"),
    "santa_barbara": lambda ref: parse_pageformat(ref, "Santa Barbara", SOURCE_DIR / "2026 Santa Barbara County, CA precinct-level results/SantaBarbara-2026-Primary-Certified-SOVC-by-Precinct.xlsx"),
    "contra_costa": lambda ref: parse_pageformat(ref, "Contra Costa", SOURCE_DIR / "2026 Contra Costa County, CA precinct-level results.xlsx"),
    "imperial": lambda ref: parse_pageformat(ref, "Imperial", SOURCE_DIR / "2026 Imperial County, CA precinct-level results.xlsx"),
    "siskiyou": lambda ref: parse_pageformat(ref, "Siskiyou", SOURCE_DIR / "2026 Siskiyou County, CA precinct-level results.xlsx"),
    "san_benito": lambda ref: parse_pageformat(ref, "San Benito", SOURCE_DIR / "2026 San Benito County, CA precinct-level results.xlsx"),
    "el_dorado": lambda ref: parse_pageformat(ref, "El Dorado", SOURCE_DIR / "2026 El Dorado County statementofvotescastrpt-prec.xlsx"),
    # Mono SOVC xlsx has an extra turnout-only Sheet1 (no candidate columns,
    # skipped) and a doubled Precinct/Times-Cast stats block in the header of
    # each contest sheet; parse_pageformat handles both.
    "mono": lambda ref: parse_pageformat(ref, "Mono", SOURCE_DIR / "Mono CA StatementOfVotesCastRPT by Precinct - 10.21.26.xlsx"),
    "riverside": lambda ref: parse_precinctcanvass(ref, "Riverside", SOURCE_DIR / "2026 Riverside County COUNTY SOV PRIVACY__20260626171607643.xlsx", dedup=True),
    "shasta": lambda ref: parse_shasta_pdf(ref, "Shasta", SOURCE_DIR / "2026 Shasta County, CA precinct-level results.pdf"),
    "calaveras": lambda ref: parse_calaveras_xlsx(ref, "Calaveras", SOURCE_DIR / "2026 Calaveras County Official Precinct Results-7-2-2026 12-47-50 PM.xlsx"),
    # Rotated-header SOV PDFs
    "amador": lambda ref: parse_rotated_pdf(ref, "Amador", SOURCE_DIR / "2026 Amador County, CA precinct-level results.pdf"),
    "lake": lambda ref: parse_rotated_pdf(ref, "Lake", SOURCE_DIR / "2026 Lake County, CA precinct-level results.pdf"),
    # 180-degree-rotated "Canvass Results Report" PDF
    "sierra": lambda ref: parse_rotated180_pdf(ref, "Sierra", SOURCE_DIR / "2026 Sierra County, CA precinct-level results.pdf"),
    # Clarity-style ElectionResult XML
    "marin": lambda ref: parse_clarity_xml(ref, "Marin", SOURCE_DIR / "2026 Marin County, CA precinct-level results.xml"),
    "merced": lambda ref: parse_clarity_xml(ref, "Merced", SOURCE_DIR / "2026 Merced County, CA precinct-level results.xml"),
    "santa_clara": lambda ref: parse_clarity_xml(ref, "Santa Clara", SOURCE_DIR / "2026 Santa Clara County, CA precinct-level results.xml"),
    # Trinity garbled Reporting Services CSV (precinct-major, no precinct column)
    "trinity": lambda ref: parse_trinity_csv(ref, "Trinity", SOURCE_DIR / "2026 Trinity County, CA precinct-level results/Trinity-2026-Primary-Precinct-Results.csv"),
    # Los Angeles per-contest .xls exports (one workbook per contest)
    "los_angeles": lambda ref: parse_los_angeles(ref, "Los Angeles", SOURCE_DIR / "2026 Los Angeles County, CA precinct-level results/4338_svc_excel_v4"),
    # Placer upright "Statement of Votes Cast by Precinct" PDF
    "placer": lambda ref: parse_placer_pdf(ref, "Placer", SOURCE_DIR / "2026 Placer County, CA precinct-level results.pdf"),
    # Butte 180-degree-rotated SOVC PDF (10-page front matter, contest inferred
    # per page from candidate names since continuation pages omit the title)
    "butte": lambda ref: parse_butte_pdf(ref, "Butte", SOURCE_DIR / "2026 Butte County, CA precinct-level results.pdf"),
    # Mendocino upright precinct-major "Statement of Votes" PDF
    "mendocino": lambda ref: parse_mendocino_pdf(ref, "Mendocino", SOURCE_DIR / "2026 Mendocino County, CA precinct-level results.pdf"),
    # Modoc upright precinct-major "Summary Results Report" PDF
    "modoc": lambda ref: parse_modoc_pdf(ref, "Modoc", SOURCE_DIR / "2026 Modoc County, CA precinct-level results.pdf"),
    # Yolo 180-degree-rotated "District Results Report" PDF (18-page front matter,
    # contest title reprinted on every page, simple nearest-left value mapping)
    "yolo": lambda ref: parse_yolo_pdf(ref, "Yolo", SOURCE_DIR / "2026 Yolo County, CA precinct-level results.pdf"),
    # Tehama 90-degree-rotated-header PDF; blanks zero-vote cells (blank_zero)
    # and wraps the Assembly title across two lines.
    "tehama": lambda ref: parse_rotated_pdf(ref, "Tehama", SOURCE_DIR / "2026 Tehama-County-06-02-2026.pdf", blank_zero=True),
    "stanislaus": parse_stanislaus_xlsx,
    "san_mateo": parse_san_mateo_csv,
    # Solano (upright precinct-major "Precinct Results Report" PDF) is currently
    # DROPPED: the precinct PDF covers only 115/160 precincts and the soft
    # shortfall is anomalously concentrated in 6 Democratic candidates. See
    # memory/ca-2026-solano-pdf-precincts.md. Re-enable by registering `solano`
    # -> parse_solano_pdf(...) here once a more complete source is available.
    # Nevada "District Results" xlsx (per-precinct cumulative sheets + write-in tally sheets)
    "nevada": lambda ref: parse_nevada_xlsx(ref, "Nevada", SOURCE_DIR / "2026 Nevada County District Results-7-23-2026 11-16-29 AM_14b4c716-358e-43ef-8edb-3c990d6f4f1e.xlsx"),
    # Orange SOVC tab-delimited flat export (one row per precinct x candidate)
    "orange": lambda ref: parse_orange_txt(ref, "Orange", SOURCE_DIR / "2026 Orange County, CA precinct-level results/Orange-2026-Primary-SOVC-results.txt"),
}

# slug -> county display name (as used in the county-level file)
COUNTY_DISPLAY = {
    "sacramento": "Sacramento",
    "humboldt": "Humboldt",
    "alameda": "Alameda",
    "kings": "Kings",
    "monterey": "Monterey",
    "sonoma": "Sonoma",
    "san_diego": "San Diego",
    "madera": "Madera",
    "yuba": "Yuba",
    "colusa": "Colusa",
    "fresno": "Fresno",
    "inyo": "Inyo",
    "san_francisco": "San Francisco",
    "san_luis_obispo": "San Luis Obispo",
    "tulare": "Tulare",
    "sutter": "Sutter",
    "santa_barbara": "Santa Barbara",
    "contra_costa": "Contra Costa",
    "imperial": "Imperial",
    "siskiyou": "Siskiyou",
    "san_benito": "San Benito",
    "el_dorado": "El Dorado",
    "mono": "Mono",
    "riverside": "Riverside",
    "shasta": "Shasta",
    "calaveras": "Calaveras",
    "amador": "Amador",
    "lake": "Lake",
    "sierra": "Sierra",
    "marin": "Marin",
    "merced": "Merced",
    "santa_clara": "Santa Clara",
    "trinity": "Trinity",
    "los_angeles": "Los Angeles",
    "placer": "Placer",
    "butte": "Butte",
    "mendocino": "Mendocino",
    "modoc": "Modoc",
    "yolo": "Yolo",
    "tehama": "Tehama",
    "stanislaus": "Stanislaus",
    "san_mateo": "San Mateo",
    "nevada": "Nevada",
    "orange": "Orange",
    "ventura": "Ventura",
}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("counties", nargs="*", help="county slugs to parse (default: all known)")
    args = ap.parse_args()
    ref = CountyReference()
    targets = args.counties if args.counties else list(PARSERS)
    for slug in targets:
        fn = PARSERS.get(slug)
        if not fn:
            print(f"!! no parser for {slug}")
            continue
        rows = fn(ref)
        path = write_county(COUNTY_DISPLAY[slug], rows)
        print(f"[{slug}] {len(rows)} rows -> {path.name}")
    print(f"\nWrote {len(targets)} county files. Verify with: "
          f"uv run python src/verify_primary_2026_precincts.py --all")


if __name__ == "__main__":
    main()