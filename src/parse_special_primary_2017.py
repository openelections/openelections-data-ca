import pandas as pd

output_columns = ['county', 'office',
                  'district', 'party', 'candidate', 'votes']


def parse_sos():
    df = pd.read_excel(
        'http://elections.cdn.sos.ca.gov/special-elections/2017-cd34/primary-official-canvas.xls', header=None)
    df = pd.concat([df.loc[x:x + 3, 2:8:2].reset_index(drop=True)
                    for x in [8, 14, 20, 26, 32, 38]], axis=1)
    df.columns = df.iloc[0].str.strip() + ' ' + df.iloc[1].str.rstrip(' (W/I)')
    parties = df.iloc[2].str.upper().to_dict()
    table = pd.melt(df.tail(-3), id_vars=None, value_vars=df.columns.tolist(), var_name='candidate', value_name='votes').assign(county='Los Angeles',
                                                                                                                                office='U.S. House',
                                                                                                                                district='34')
    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20170404__ca__special__primary.csv', header=output_columns, index=False)


def main():
    parse_sos()

if __name__ == "__main__":
    main()
