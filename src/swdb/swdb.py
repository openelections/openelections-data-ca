import codes
import numpy as np
import pandas as pd

from util import dbf_to_dataframe, csv_to_dataframe, COUNTIES

# Output column names for OpenElections format
fieldnames = ['county', 'precinct', 'office',
              'district', 'party', 'candidate', 'votes']

# Non-candidate columns in the SWDB format
skip = ['svprec', 'addist', 'cddist', 'sddist', 'bedist']

county_dict = {county: '%03d' % code for (
    county, code) in zip(COUNTIES, range(1, 116, 2))}


def drop_column(x):
    return x.endswith('REG') or x.endswith('VOTE') or x.startswith('PR_')


def drop_row(x):
    return not x.startswith('SOV') and not x.endswith('TOT')

url_prefix = 'http://statewidedatabase.org/pub/data/{}/'
codes_fmt = 'c{0}/{0}.codes'
svprec_fmt = 'c{0}/c{0}_{1}_sov_data_by_{1}_svprec'


def codes_fname(election, county):
    return url_prefix.format(election) + codes_fmt.format(county_dict[county])


def dbf_fname(election, county):
    return url_prefix.format(election) + svprec_fmt.format(county_dict[county], election.lower()) + '.dbf'


def csv_fname(election, county):
    return url_prefix.format(election) + svprec_fmt.format(county_dict[county], election.lower()) + '.csv'


class SWDBResults(object):

    def __init__(self, election, county, candidate_norm):
        self.county = county
        self.election = election
        self.codes = codes.Codes(codes_fname(election, county), candidate_norm)
        self.df = self.__load_dataframe()

    def __load_dataframe(self):
        try:
            df = csv_to_dataframe(csv_fname(self.election, self.county))
        except:
            df = dbf_to_dataframe(dbf_fname(self.election, self.county))

        # Drop registration, total vote, and proposition columns
        df = df.drop(
            [x for x in df.columns if drop_column(x)], axis=1)
        drop_rows = [x for x in df.svprec.values if drop_row(x)]
        df = df[df.svprec.isin(drop_rows)]

        # All counties aside from Humboldt and Los Angeles have absentee
        # ballots for precincts coded with a trailing 'A'.
        if self.county != 'Humboldt' and self.county != 'Los Angeles':
            df.svprec = df.svprec.apply(lambda x: x.rstrip('A'))

        result = pd.DataFrame(columns=fieldnames)

        for column in df.columns:
            result = pd.concat([result, self.__process_column(df, column)])

        result.votes = result.votes.astype(np.int32)
        result = result.groupby(
            fieldnames[:-1]).sum().reset_index()[fieldnames]
        for x in ['candidate', 'district', 'office', 'precinct']:
            result = result.sort_values(by=x, kind='mergesort')
        return result

    def __process_column(self, df, column):
        if column in skip:
            return None

        id_var = None
        if column.startswith('ASS'):
            id_var = 'addist'
        elif column.startswith('CNG'):
            id_var = 'cddist'
        elif column.startswith('SEN'):
            id_var = 'sddist'
        elif column.startswith('BOE'):
            id_var = 'bedist'

        candidate = pd.melt(
            df, id_vars=['svprec', id_var],
            value_vars=[column],
            var_name='candidate',
            value_name='votes').rename(
            columns={id_var:   'district',
                     'svprec': 'precinct'}).assign(
                county=self.county,
                office=self.codes.office(column),
                party=self.codes.party(column))
        candidate = candidate[candidate.votes != 0]

        if id_var:
            candidate.district = candidate.district.astype(np.int32)
            candidate.candidate = candidate.district.apply(
                lambda x: self.codes.lookup(column, x).candidate)
            candidate.district = candidate.district.astype(str)
        else:
            candidate = candidate.assign(
                candidate=self.codes.lookup(column).candidate).fillna('')

        return candidate
