import pandas

sovc_xls = 'https://www.acgov.org/rov/elections/20150519/documents/sovc.xls'
general = pandas.read_excel(sovc_xls, sheetname='Sheet1')

candidates = ['Susan Bonilla', 'Steve Glazer']
parties = {'Susan Bonilla': 'DEM',
           'Steve Glazer': 'DEM'}

# Select only contests of interest and the important columns
general = general.loc[(general.index > 5) & (general.index < 386)][
    ['Alameda County', 'Unnamed: 7', 'Unnamed: 8']]
general.columns = ['precinct', 'Susan Bonilla', 'Steve Glazer']
general = pandas.melt(general, id_vars='precinct',
                      value_vars=candidates, var_name='candidate', value_name='votes').dropna()
general['party'] = general.candidate.apply(lambda x: parties[x])

general = general.assign(county='Alameda',
                         office='State Senate',
                         district=7)
general.votes = general.votes.astype(int)

output_columns = ['county', 'precinct', 'office',
                  'district', 'party', 'candidate', 'votes']
general = general.groupby(
    output_columns[:-1]).sum().reset_index()[output_columns]

general.to_csv(
    '2015/20150519__ca__special__general__alameda__precinct.csv', header=output_columns, index=False)
