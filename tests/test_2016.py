#!/usr/bin/env python3

import glob
import pandas
import pytest


def test_primary():
    state_files = glob.glob('2016/*__ca__primary.csv')
    for state_file in state_files:
        state_data = pandas.read_csv(state_file)

        for county_file in glob.glob('2016/*__ca__primary__*__precinct.csv'):
            county_data = pandas.read_csv(county_file)

            # Each county file should only contain a single county.
            assert len(county_data.drop_duplicates(
                ['county']).county.values) == 1

            county = county_data.drop_duplicates(['county']).county.values[0]
            contest_columns = ['office', 'district']
            contests = county_data.drop_duplicates(
                contest_columns)[contest_columns].values

            for office, district in contests:
                candidates = county_data.loc[
                    county_data.office == office].candidate.unique()

                # The sum over the precincts for each county should be the same
                # as the county-level vote totals.
                county_votes = {
                    candidate: county_data.loc[
                        county_data.candidate == candidate].votes.sum()
                    for candidate in candidates}
                votes = {
                    candidate: state_data.loc[
                        (state_data.candidate == candidate) & (state_data.county == county)].votes.sum()
                    for candidate in candidates
                }

                assert votes == county_votes, "%s for %s failed" % (
                    office, county)


def test_general():
    state_files = glob.glob('2016/*__ca__general.csv')
    for state_file in state_files:
        state_data = pandas.read_csv(state_file)

        for county_file in glob.glob('2016/*__ca__general__*__precinct.csv'):
            county_data = pandas.read_csv(county_file)

            # Each county file should only contain a single county.
            assert len(county_data.drop_duplicates(
                ['county']).county.values) == 1

            county = county_data.drop_duplicates(['county']).county.values[0]
            contest_columns = ['office', 'district']
            contests = county_data.drop_duplicates(
                contest_columns)[contest_columns].values

            for office, district in contests:
                candidates = county_data.loc[
                    county_data.office == office].candidate.unique()

                # The sum over the precincts for each county should be the same
                # as the county-level vote totals.
                county_votes = {
                    candidate: county_data.loc[
                        (county_data.office == office) & (county_data.candidate == candidate)].votes.sum()
                    for candidate in candidates if candidate != 'Write-In'}
                votes = {
                    candidate: state_data.loc[
                        (state_data.office == office) & (state_data.candidate == candidate) & (state_data.county == county)].votes.sum()
                    for candidate in candidates if candidate != 'Write-In'
                }

                assert votes == county_votes, "%s for %s failed" % (
                    office, county)
