import pandas

presidential_xls = 'http://elections.cdn.sos.ca.gov/sov/2016-primary/csv-presidential-candidates.xls'
voter_nominated_xls = 'http://elections.cdn.sos.ca.gov/sov/2016-primary/csv-voter-nominated-candidates.xls'

contest_names = set(['President %s' % x for x in
                     ['Democratic',
                      'Republican',
                      'American Independent',
                      'Green',
                      'Libertarian',
                      'P and F']])

# Normalized party names for consistency
party_dict = {'Democratic': 'DEM',
              'Republican': 'REP',
              'American Independent': 'AI',
              'Green': 'GRN',
              'Libertarian': 'LIB',
              'Peace and Freedom': 'PF',
              'No Party Preference': 'NPP'}

# Normalized office names
office_dict = {'United States Representative': 'U.S. House',
               'State Assembly Member': 'State Assembly'}

# Clean up candidate names
candidate_dict = {'Ron  Unz': 'Ron Unz'}

# Columns to select
columns = ['COUNTY_NAME', 'office', 'district',
           'PARTY_NAME', 'CANDIDATE_NAME', 'VOTE_TOTAL']

presidential = pandas.read_excel(presidential_xls)

# Override office name for Presidential and fill in an empty district
presidential = presidential.assign(office='President').assign(district='')

# Select only contests of interest and the important columns
presidential = presidential.loc[
    presidential.CONTEST_NAME.isin(contest_names)][columns]

voter_nominated = pandas.read_excel(voter_nominated_xls)

contest_split = voter_nominated['CONTEST_NAME'].str.extract(
    '(?P<office>.+) District (?P<district>\d+)$', expand=True)
contest_split.office.fillna('U.S. Senate', inplace=True)

voter_nominated = pandas.concat([voter_nominated, contest_split], axis=1)
voter_nominated = voter_nominated.replace({'office': office_dict})[columns]

result = pandas.concat([presidential, voter_nominated]
                       ).replace({'PARTY_NAME': party_dict,
                                  'CANDIDATE_NAME': candidate_dict})

output_columns = ['county', 'office',
                  'district', 'party', 'candidate', 'votes']
result[result.COUNTY_NAME != 'State Totals'].to_csv(
    '2016/20160607__ca__primary.csv', header=output_columns, index=False)
