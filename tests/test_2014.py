#!/usr/bin/env python3

import glob
import pandas
import pytest


columns = ['candidate', 'county', 'district', 'office', 'votes']


def test_general():
    state_files = glob.glob('2014/*__ca__general.csv')
    for state_file in state_files:
        state_data = pandas.read_csv(state_file, na_values='').fillna('')
        state_data = state_data[state_data.votes != 0]

        for county_file in glob.glob('2014/*__ca__general__*__precinct.csv'):
            county_data = pandas.read_csv(county_file, na_values='').fillna('')

            # Each county file should only contain a single county.
            assert len(county_data.drop_duplicates(
                ['county']).county.values) == 1

            county = county_data.drop_duplicates(['county']).county.values[0]
            county_data = county_data[columns].groupby(
                columns[:-1]).sum()
            state_cmp = state_data[state_data.county == county][
                columns].groupby(columns[:-1]).sum()

            assert state_cmp.to_dict()['votes'] == county_data.to_dict()[
                'votes'], '%s failed' % county
