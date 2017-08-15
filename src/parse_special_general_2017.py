import pandas as pd
import requests
import tempfile
import zipfile

candidates = {'JIMMY GOMEZ': 'Jimmy Gomez',
              'ROBERT LEE AHN': 'Robert Lee Ahn'}


def parse_sos():
    output_columns = ['county', 'office',
                      'district', 'party', 'candidate', 'votes']

    df = pd.read_excel(
        'http://elections.cdn.sos.ca.gov/special-elections/2017-cd34/cd34-general-official-canvass.xls', header=None)
    df = pd.concat([df.loc[x:x + 3, 2:4:2].reset_index(drop=True)
                    for x in [8]], axis=1)
    df.columns = df.iloc[0].str.strip() + ' ' + df.iloc[1].str.rstrip(' (W/I)')
    parties = df.iloc[2].str.upper().to_dict()
    table = pd.melt(df.tail(-3), id_vars=None, value_vars=df.columns.tolist(), var_name='candidate', value_name='votes').assign(county='Los Angeles',
                                                                                                                                office='U.S. House',
                                                                                                                                district='34')
    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20170606__ca__special__general.csv', header=output_columns, index=False)


def parse_los_angeles():
    output_columns = ['county', 'precinct', 'office',
                      'district', 'party', 'candidate', 'votes']

    sovc_zip_url = 'https://www.lavote.net/documents/SVC/3744_SVC_Excel.zip'
    sovc_zip = requests.get(sovc_zip_url)
    if sovc_zip.status_code != 200:
        return
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    df = pd.read_excel(sovc_zf.open(
        '34TH_CONGRESS_DIST_U-T_06-06-17_Voter_Nominated_by_Precinct_3744-5055.xls'))

    df.columns = df.loc[1]
    df = df[df.TYPE == 'TOTAL']
    table = pd.melt(df, id_vars=['PRECINCT'], value_vars=df.columns.tolist()[
        8:-1], var_name='candidate', value_name='votes').assign(county='Los Angeles', office='U.S. House', district='34').rename(columns={'PRECINCT': 'precinct'}).replace({'candidate': candidates})
    parties = {k: 'DEM' for k in candidates.values()}

    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20170606__ca__special__general__los_angeles__precinct.csv', index=False)


def main():
    parse_sos()
    parse_los_angeles()

if __name__ == "__main__":
    main()
