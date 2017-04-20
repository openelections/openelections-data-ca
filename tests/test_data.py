#!/usr/bin/env python3

import glob
import pandas
import pytest


columns = ['candidate', 'county', 'district', 'office', 'votes']


@pytest.mark.parametrize("year,date,election_type", [
    ("2014", "0603", "primary"),
    ("2014", "1104", "general"),
    ("2015", "0317", "special__primary"),
    ("2015", "0519", "special__general"),
    ("2016", "0405", "special__primary"),
    ("2016", "0607", "primary"),
    ("2016", "1108", "general"),
    ("2017", "0404", "special__primary"),
])
def test_data(year, date, election_type):
    state_file = '{0}/{0}{1}__ca__{2}.csv'.format(
        year, date, election_type)
    state_data = pandas.read_csv(state_file, na_values='').fillna('')
    state_data = state_data[state_data.votes != 0]

    for county_file in glob.glob('{0}/{0}{1}__ca__{2}__*__precinct.csv'.format(year, date, election_type)):
        county_data = pandas.read_csv(county_file, na_values='').fillna('')

        # Each county file should only contain a single county.
        assert len(county_data.drop_duplicates(
            ['county']).county.values) == 1

        county = county_data.drop_duplicates(['county']).county.values[0]
        county_data = county_data[columns].groupby(
            columns[:-1]).sum()
        state_cmp = state_data[state_data.county == county][
            columns].groupby(columns[: -1]).sum()

        assert state_cmp.to_dict()['votes'] == county_data.to_dict()[
            'votes'], '%s failed' % county
