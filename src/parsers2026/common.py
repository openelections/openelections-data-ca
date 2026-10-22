"""Shared helpers for the 2026 primary county precinct parsers.

Three concerns, each shared across the very-different county source formats:

* ``parse_office`` — map a contest title/label (which varies wildly by county
  reporting system: ``"1 U.S. Representative, 10th Congressional District"``,
  ``"US REP CONGRESS DIST 4 (Vote for 1)"``, ``"State Assembly Member District 8"``,
  …) to an OpenElections ``(office, district)`` tuple, or ``None`` for non-
  statewide contests (local offices, measures, judges) that we skip.

* ``map_party`` — map a source party code (``DEM``, ``NPP``, …) or already-full
  name to the canonical full party name used in the county-level file.

* ``CountyReference`` — loads ``20260602__ca__primary__county.csv`` and exposes,
  per county, the set of expected ``(office, district)`` contests and a way to
  canonicalize a candidate name to exactly the spelling used in the county file
  (so precinct output matches the county file and the ``test_data`` invariant).
"""

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COUNTY_FILE = REPO_ROOT / "2026/20260602__ca__primary__county.csv"

PARTY_CODE_MAP = {
    "DEM": "Democratic",
    "REP": "Republican",
    "GRN": "Green",
    "LIB": "Libertarian",
    "PF": "Peace and Freedom",
    "AI": "American Independent",
    "NPP": "No Party Preference",
    "NP": "Non-Partisan",
    "REP/W/I": "Republican",
    "DEM/W/I": "Democratic",
    "GRN/W/I": "Green",
    "LIB/W/I": "Libertarian",
    "NPP/W/I": "No Party Preference",
    "PF/W/I": "Peace and Freedom",
    "AI/W/I": "American Independent",
}


def map_party(raw):
    """Map a source party code or full name to the canonical party name."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # Already-full names from clean sources (Sacramento/Humboldt exports).
    full = {
        "Democratic", "Republican", "Green", "Libertarian",
        "American Independent", "Peace and Freedom",
        "No Party Preference", "Non-Partisan",
    }
    if s in full:
        return s
    # "DEM (W/I)" style.
    m = re.match(r"^([A-Z/]+)\s*\(W/I\)\s*$", s)
    if m and m.group(1) in PARTY_CODE_MAP:
        return PARTY_CODE_MAP[m.group(1)]
    up = s.upper()
    if up in PARTY_CODE_MAP:
        return PARTY_CODE_MAP[up]
    return s  # fallback: leave as-is


def norm_name(name):
    if name is None:
        return ""
    s = str(name).lower()
    s = s.replace(".", " ").replace(",", " ")
    s = s.replace('"', " ").replace("'", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def match_key(name):
    """Aggressive match key: lowercase, strip accents, drop periods/quotes/commas,
    drop single-letter middle initials, keep alphanumerics only. Reconciles source
    spelling differences (case, accents, middle initials, encoding artifacts)."""
    if name is None:
        return ""
    s = _strip_accents(str(name).lower())
    s = s.replace(".", " ").replace(",", " ").replace('"', " ").replace("'", " ")
    s = s.replace("-", " ")
    # drop single-letter tokens (middle initials)
    s = " ".join(t for t in s.split() if len(t) > 1)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_SUMMARY_RE = re.compile(
    r"^(ballots?\s*cast|over\s*votes?|under\s*votes?|registered\s*voters|times\s*cast|"
    r"times\s+tallied|turnout|write-?\s*ins?|scattered|non-?qualified\s*write-?ins?|unresolved\s*write-?ins?|"
    r"qualified\s*write-?\s*ins?|unqualified\s*write-?\s*ins?|"
    r"total\s+ballots?|total\s+votes?|total\s+ballots?\s*cast|total\s+votes?\s*cast|"
    r"electionwide|california|totals?|polls?|provisional|canvass|ballots\s+tallied)$",
    re.I,
)


def is_summary_name(name):
    """True for non-candidate ballot/choice labels (over/under votes, write-in totals, …)."""
    if name is None:
        return True
    return bool(_SUMMARY_RE.match(str(name).strip()))


def _clean_title(title):
    if title is None:
        return ""
    t = str(title)
    t = t.replace("\n", " ")
    # drop a leading contest id like "1 " or "13 "
    t = re.sub(r"^\s*\d+\s+", " ", t)
    # drop "(Vote for N)" and "**** -" cruft
    t = re.sub(r"\(vote for[^)]*\)", " ", t, flags=re.I)
    t = re.sub(r"\*+", " ", t)
    t = re.sub(r"\s*-\s*$", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.upper()


def _extract_district(text):
    """Pull a district number out of a cleaned title."""
    patterns = [
        r"(\d+)(?:ST|ND|RD|TH)\s+(?:CONGRESSIONAL\s+)?DISTRICT",
        r"DIST(?:RICT)?\s*(\d+)",
        r"(\d+)(?:ST|ND|RD|TH)\s+DIST",
        # "5th Congress", "12th State Senate", "8th Assembly" — the district
        # is the ordinal prefix with no "District" word (Fresno SOVC style).
        r"(\d+)(?:ST|ND|RD|TH)\s+(?:CONGRESS|STATE\s+SENATE|STATE\s+ASSEMBLY|ASSEMBLY|SENATE)",
        # Los Angeles BOE abbreviation: "STATE BD EQUALIZATION D3".
        r"EQUAL(?:IZATION)?\s+D?(\d+)",
        # Riverside BOE: "Board of Equalization, 4th" — ordinal after the
        # Equalization word, with a comma and no "District"/"D" prefix.
        r"EQUAL(?:IZATION)?\s*,?\s*(\d+)(?:ST|ND|RD|TH)\b",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return str(int(m.group(1)))
    return ""


# (regex on cleaned title, office label, needs_district)
OFFICE_RULES = [
    (r"LIEUTENANT\s+GOVERNOR|LT\.?\s+GOVERNOR", "Lieutenant Governor", False),
    (r"SECRETARY\s+OF\s+STATE|SEC\.?\s+OF\s+STATE", "Secretary of State", False),
    (r"ATTORNEY\s+GENERAL", "Attorney General", False),
    (r"INSURANCE\s+COMMISSIONER", "Insurance Commissioner", False),
    (r"SUPERINTENDENT\s+(?:OF\s+)?PUBLIC\s+INST(?:R(?:UCTION)?)?|"
     r"SUPT\s+(?:OF\s+)?PUBLIC\s+INST(?:R(?:UCTION)?)?|"
     r"STATE\s+(?:SUPERINTENDENT|SUPT)",
     "Superintendent of Public Instruction", False),
    (r"CONTROLLER", "Controller", False),
    (r"\bGOVERNOR\b", "Governor", False),
    (r"\bTREASURER\b", "Treasurer", False),
    (r"\b(?:BOARD|BD)\.?\s+(?:OF\s+)?EQUAL(?:IZATION)?|BOARD\s+EQUAL|"
     r"MEMBER.*BOARD\s+OF\s+EQUAL(?:IZATION)?",
     "Board of Equalization", True),
    (r"U\.?\s?S\.?\s+REPRESENTATIVE|US\s+REP\s+CONGRESS|UNITED\s+STATES\s+REPRESENTATIVE|"
     r"REPRESENTATIVE\s+IN\s+CONGRESS|CONGRESS(?:I[ON]NAL)?\s+DIST|\bCONGRESS\b|"
     r"HOUSE\s+OF\s+REPRESENTATIVES",
     "U.S. House", True),
    (r"STATE\s+SENATOR|STATE\s+SENATE|MEMBER\s+OF\s+THE\s+STATE\s+SENATE", "State Senate", True),
    (r"STATE\s+ASSEMBLY|ASSEMBLY\s+MEMBER|MEMBER\s+OF\s+THE\s+STATE\s+ASSEMBLY|"
     r"MEMBER\s+OF\s+STATE\s+ASSEMBLY|\bASSEMBLY\b",
     "State Assembly", True),
]


# County/local office keywords. A canvass contest label containing any of
# these is a local office or measure, not a statewide contest, and is skipped.
# None of these tokens appear in a statewide office name (Governor, Lieutenant
# Governor, Secretary of State, Controller, Treasurer, Attorney General,
# Insurance Commissioner, Superintendent of Public Instruction, Board of
# Equalization, U.S. Representative, State Senate, State Assembly), so this
# guard never falsely rejects a statewide contest. It catches the county
# offices that would otherwise collide with a statewide rule — notably
# "Auditor-Controller" / "Auditor/Controller" and "Treasurer-Tax Collector" /
# "Treasurer/Tax Collector", which both contain CONTROLLER/TREASURER.
_LOCAL_RE = re.compile(
    r"\b(COUNTY|AUDITOR|TAX\s+COLLECTOR|SHERIFF|ASSESSOR|CLERK|RECORDER|CORONER|"
    r"PUBLIC\s+ADMINISTRATOR|SUPERVISOR|SUPERIOR\s+COURT|JUDGE|"
    r"BOARD\s+OF\s+EDUCATION|BOARD\s+OF\s+SUPERVISORS|CITY\s+COUNCIL|CITY\s+OF|"
    r"MAYOR|COUNCIL|TRUSTEE|SUPERINTENDENT\s+OF\s+SCHOOLS|"
    r"COMMUNITY\s+COLLEGE|SCHOOL\s+DISTRICT|RETENTION|PROBATE|CONSOLIDATED|"
    r"DISTRICT\s+ATTORNEY)\b"
)


def parse_office(title):
    """Return (office, district) for a statewide contest, else None."""
    t = _clean_title(title)
    if not t:
        return None
    # Local county/city offices and measures never appear in the statewide set
    # and some would otherwise match a statewide rule (e.g. a county
    # "Auditor-Controller" or "Treasurer/Tax Collector" matching CONTROLLER /
    # TREASURER). Skip them.
    if _LOCAL_RE.search(t):
        return None
    for pattern, office, needs_district in OFFICE_RULES:
        if re.search(pattern, t):
            district = _extract_district(t) if needs_district else ""
            if needs_district and not district:
                return None
            return (office, district)
    return None


class CountyReference:
    """Reference data from the county-level file, for canonicalizing output."""

    def __init__(self, path=COUNTY_FILE):
        # county -> set of (office, district)
        self.contests = defaultdict(set)
        # (office, district, norm_name) -> display_name
        self.display_name = {}
        # (office, district, norm_name) -> party
        self.party = {}
        # county -> {(office, district, norm_name): votes}
        self.votes = defaultdict(dict)
        # (office, district) -> {match_key: display_name}
        self.by_key = defaultdict(dict)
        # (office, district) -> {first_token: set(display_name, ...)}
        self.by_first = defaultdict(lambda: defaultdict(set))
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                c = r["county"]
                od = (r["office"], r["district"])
                self.contests[c].add(od)
                nn = norm_name(r["candidate"])
                self.display_name[(r["office"], r["district"], nn)] = r["candidate"]
                self.party[(r["office"], r["district"], nn)] = r.get("party", "")
                self.votes[c][(r["office"], r["district"], nn)] = int(r["votes"])
                mk = match_key(r["candidate"])
                if mk and mk not in self.by_key[od]:
                    self.by_key[od][mk] = r["candidate"]
                first = mk.split(" ", 1)[0] if mk else ""
                if first:
                    self.by_first[od][first].add(r["candidate"])

    def county_display(self, slug):
        for c in self.contests:
            if re.sub(r"\s+", "_", c.lower()) == slug:
                return c
        return slug.replace("_", " ").title()

    def canonical_name(self, office, district, name):
        """Return the county-file spelling of a candidate.

        Tries exact normalized name, then an accent/initial-insensitive match key
        scoped to the contest, then a unique first-name match within the contest
        (to recover names corrupted in the source, e.g. ``Solã“Rzano``). Falls back
        to a tidied version of the source name.
        """
        od = (office, district)
        nn = norm_name(name)
        if (office, district, nn) in self.display_name:
            return self.display_name[(office, district, nn)]
        mk = match_key(name)
        if mk and mk in self.by_key.get(od, {}):
            return self.by_key[od][mk]
        if mk:
            first = mk.split(" ", 1)[0]
            cands = self.by_first.get(od, {}).get(first, set())
            if len(cands) == 1:
                return next(iter(cands))
        # Suffix match: some sources abbreviate leading name tokens to single
        # initials (Los Angeles SVC: "L A DEMOTT", "A VILLARAIGOSA"). match_key
        # drops single-letter tokens, so the source key becomes a contiguous
        # SUFFIX of the full county key ("demott" vs "livingforgod andcountry
        # demott"). Match when exactly one county candidate's key ends with the
        # source tokens -- the uniqueness guard prevents two same-surname
        # candidates from colliding.
        if mk:
            src_toks = mk.split(" ")
            n = len(src_toks)
            if n >= 1:
                hits = [cn for cn in self.by_key.get(od, {}).values()
                        if match_key(cn).split(" ")[-n:] == src_toks]
                if len(hits) == 1:
                    return hits[0]
        # fuzzy last resort: a UNIQUE near-match within the contest (edit
        # distance <= 2 on the match key). Recovers source spelling variants
        # like "Merrit Farren" vs "Merritt Farren" or "Adbur Rahman Sikder"
        # vs "Abdur Rahman Sikder". Only fires when exactly one candidate is
        # within the threshold, so two distinct similar-named candidates do
        # not collide.
        if mk:
            best = None
            best_d = 99
            ambiguous = False
            for cand_name in self.by_key.get(od, {}).values():
                d = _levenshtein(mk, match_key(cand_name))
                if d < best_d:
                    best_d = d
                    best = cand_name
                    ambiguous = False
                elif d == best_d:
                    ambiguous = True
            if best is not None and not ambiguous and best_d <= 2:
                return best
        return _tidy_name(name)

    def canonical_party(self, office, district, name):
        nn = norm_name(name)
        if (office, district, nn) in self.party:
            return self.party[(office, district, nn)]
        # resolve via the same contest-scoped matching, then look up party
        mk = match_key(name)
        if mk and mk in self.by_key.get((office, district), {}):
            disp = self.by_key[(office, district)][mk]
            return self.party.get((office, district, norm_name(disp)), "")
        return ""


def _tidy_name(name):
    """Light cleanup for names that aren't in the county file (e.g. write-ins)."""
    if name is None:
        return ""
    s = re.sub(r"\s+", " ", str(name)).strip()
    return s


def _levenshtein(a, b):
    """Edit distance between two strings (small strings only)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]