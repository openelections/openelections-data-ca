import pandas

candidates_xls = 'http://elections.cdn.sos.ca.gov/sov/2016-general/sov/csv-candidates.xls'

props_xls = 'http://elections.cdn.sos.ca.gov/sov/2016-general/sov/csv-ballot-measures.xls'

contest_names = set({'President'})

# Normalized party names for consistency
party_dict = {'Democratic': 'DEM',
              'Republican': 'REP',
              'American Independent': 'AI',
              # Donald Trump is listed for both parties
              'Republican,AmericanIndependent': 'REP',
              'Green': 'GRN',
              'Libertarian': 'LIB',
              'Peace and Freedom': 'PF',
              'No Party Preference': 'NPP',
              'Blank': 'NPP'}

# Normalized office names
office_dict = {'United States Representative': 'U.S. House',
               'State Assembly Member': 'State Assembly'}


# Columns to select
columns = ['COUNTY_NAME', 'office', 'district',
           'PARTY_NAME', 'CANDIDATE_NAME', 'VOTE_TOTAL']

general = pandas.read_excel(candidates_xls)

# Select only contests of interest and the important columns
presidential = general.loc[
    general.CONTEST_NAME.isin(contest_names)]
presidential = presidential.assign(
    office='President').assign(district='')[columns]

voter_nominated = general.loc[
    general.CONTEST_NAME.isin(contest_names) == False]

contest_split = voter_nominated['CONTEST_NAME'].str.extract(
    '(?P<office>.+) District (?P<district>\d+)$', expand=True)
contest_split.office.fillna('U.S. Senate', inplace=True)

voter_nominated = pandas.concat([voter_nominated, contest_split], axis=1)
voter_nominated = voter_nominated.replace({'office': office_dict})[columns]

props = pandas.read_excel(props_xls).rename(
    columns={'YES_COUNT': 'Yes', 'NO_COUNT': 'No', 'BALLOT_MEASURE_NAME': 'office'})
props = pandas.melt(
    props, id_vars=['COUNTY_NAME', 'office'], value_vars=['Yes', 'No'], var_name='CANDIDATE_NAME', value_name='VOTE_TOTAL')
props = props.assign(district='').assign(PARTY_NAME='')[columns]

result = pandas.concat([presidential, voter_nominated, props]
                       ).replace({'PARTY_NAME': party_dict})

output_columns = ['county', 'office',
                  'district', 'party', 'candidate', 'votes']
result[result.COUNTY_NAME != 'State Totals'].to_csv(
    '2016/20161108__ca__general.csv', header=output_columns, index=False)
