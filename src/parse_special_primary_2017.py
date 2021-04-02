import pandas as pd
import requests
import tempfile
import zipfile

candidates = {'ADRIENNE N EDWARDS': 'Adrienne Nicole Edwards',
              'A CAMPOVERDI': 'Alejandra Campoverdi',
              'ANGELA E MCARDLE': 'Angela E. McArdle',
              'A SOTOMAYOR': 'Armando Sotomayor',
              'ARTURO CARMONA': 'Arturo Carmona',
              'JIMMY GOMEZ': 'Jimmy Gomez',
              'KENNETH MEJIA': 'Kenneth Mejia',
              'MARIA CABILDO': 'Maria Cabildo',
              'MARK E PADILLA': 'Mark Edward Padilla',
              'MELISSA GARZA': 'Melissa "Sharkie" Garza',
              'RAYMOND MEZA': 'Raymond Meza',
              'R DE LA FUENTE': 'Ricardo "Ricky" De La Fuente',
              'RICHARD J SULLIVAN': 'Richard Joseph Sullivan',
              'ROBERT LEE AHN': 'Robert Lee Ahn',
              'SANDRA MENDOZA': 'Sandra Mendoza',
              'SARA HERNANDEZ': 'Sara Hernandez',
              'STEVEN MAC': 'Steven Mac',
              'TENAYA WALLACE': 'Tenaya Wallace',
              'TRACY VAN HOUTEN': 'Tracy Van Houten',
              'VANESSA L ARAMAYO': 'Vanessa L. Aramayo',
              'WENDY CARRILLO': 'Wendy Carrillo',
              'WILLIAM MORRISON': 'William "Rodriguez" Morrison',
              'YOLIE FLORES': 'Yolie Flores',
              'ALEX DE OCAMPO': 'Alex De Ocampo',
              'ANDREW S AGUERO': 'Andrew S. Aguero',
              'BARBARA TORRES': 'Barbara Torres',
              'DAVID VELA': 'David Vela',
              'GABRIEL SANDOVAL': 'Gabriel Sandoval',
              'JOHN PRYSNER': 'John Prysner',
              'LUIS LOPEZ': 'Luis López',
              'MARIO OLMOS': 'Mario Olmos',
              'MARK VARGAS': 'Mark Vargas',
              'MIKE FONG': 'Mike Fong',
              'PATRICK KOPPULA': 'Patrick Koppula',
              'RON BIRNBAUM': 'Ron Birnbaum'}

p = {'Kenneth Mejia': 'GRN',
     'Angela E. McArdle': 'LIB',
     'Mark Edward Padilla': 'NPP',
     'William "Rodriguez" Morrison': 'REP',
     'Andrew S. Aguero': 'LIB',
     'John Prysner': 'PF',
     'Patrick Koppula': 'NPP'}


def parse_sos_ca34():
    output_columns = ['county', 'office',
                      'district', 'party', 'candidate', 'votes']

    df = pd.read_excel(
        'http://elections.cdn.sos.ca.gov/special-elections/2017-cd34/cd34-primary-official-canvass.xls', header=None)
    df = pd.concat([df.loc[x:x + 3, 2:8:2].reset_index(drop=True)
                    for x in [8, 14, 20, 26, 32, 38]], axis=1)
    df.columns = df.iloc[0].str.strip() + ' ' + df.iloc[1].str.rstrip(' (W/I)')
    parties = df.iloc[2].str.upper().to_dict()
    parties.update(p)
    table = pd.melt(df.tail(-3), id_vars=None, value_vars=df.columns.tolist(), var_name='candidate', value_name='votes').assign(county='Los Angeles',
                                                                                                                                office='U.S. House',
                                                                                                                                district='34')
    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20170404__ca__special__primary.csv', header=output_columns, index=False)


def parse_sos_ad51():
    output_columns = ['county', 'office',
                      'district', 'party', 'candidate', 'votes']

    df = pd.read_excel(
        'http://elections.cdn.sos.ca.gov/special-elections/2017-ad51/ad51-primary-official-canvass.xls', header=None)
    df = pd.concat([df.loc[x:x + 3, 2:8:2].reset_index(drop=True)
                    for x in [8, 14, 20, 26]], axis=1)
    df.columns = df.iloc[0].str.strip() + ' ' + df.iloc[1].str.rstrip(' (W/I)')
    parties = df.iloc[2].str.upper().to_dict()
    parties.update(p)
    table = pd.melt(df.tail(-3), id_vars=None, value_vars=df.columns.tolist(), var_name='candidate', value_name='votes').assign(county='Los Angeles',
                                                                                                                                office='State Assembly',
                                                                                                                                district='51').dropna()
    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20171003__ca__special__primary.csv', header=output_columns, index=False)


def parse_los_angeles_ca34():
    output_columns = ['county', 'precinct', 'office',
                      'district', 'party', 'candidate', 'votes']

    sovc_zip_url = 'https://www.lavote.net/documents/SVC/3685_SVC_Excel.zip'
    sovc_zip = requests.get(sovc_zip_url)
    if sovc_zip.status_code != 200:
        return
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    df = pd.read_excel(sovc_zf.open(
        '34TH_CONGRESS_DIST_U-T_04-04-17_Voter_Nominated_by_Precinct_3685-5049.xls'))

    df.columns = df.loc[1]
    df = df[df.TYPE == 'TOTAL']
    table = pd.melt(df, id_vars=['PRECINCT'], value_vars=df.columns.tolist()[
        8:-1], var_name='candidate', value_name='votes').assign(county='Los Angeles', office='U.S. House', district='34').rename(columns={'PRECINCT': 'precinct'}).replace({'candidate': candidates})
    parties = {k: 'DEM' for k in candidates.values()}
    parties.update(p)

    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20170404__ca__special__primary__los_angeles__precinct.csv', index=False)


def parse_los_angeles_ad51():
    output_columns = ['county', 'precinct', 'office',
                      'district', 'party', 'candidate', 'votes']

    sovc_zip_url = 'https://www.lavote.net/docs/rrcc/svc/3758_excel_final_svc.zip'
    sovc_zip = requests.get(sovc_zip_url)
    if sovc_zip.status_code != 200:
        return
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    df = pd.read_excel(sovc_zf.open(
        '51ST_ASSEMBLY_DIST_U-T_10-03-17_Voter_Nominated_by_Precinct_3758-5110.xls'))

    df.columns = df.loc[1]
    df = df[df.TYPE == 'TOTAL']
    table = pd.melt(df, id_vars=['PRECINCT'], value_vars=df.columns.tolist()[
        8:-1], var_name='candidate', value_name='votes').assign(county='Los Angeles', office='State Assembly', district='51').rename(columns={'PRECINCT': 'precinct'}).replace({'candidate': candidates})
    parties = {k: 'DEM' for k in candidates.values()}
    parties.update(p)

    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2017/20171003__ca__special__primary__los_angeles__precinct.csv', index=False)


def main():
    parse_sos_ca34()
    parse_sos_ad51()
    parse_los_angeles_ca34()
    parse_los_angeles_ad51()

if __name__ == "__main__":
    main()
