import codes
import pandas as pd

from swdb import SWDBResults
from util import COUNTIES, ELECTIONS

for code, pattern, norm in ELECTIONS:
    for county in COUNTIES:
        print(county)
        try:
            results = SWDBResults(code, county, norm)
        except Exception as e:
            print(e)
            continue

        results.df.to_csv(
            pattern % (county.lower().replace(' ', '_')), index=False)
