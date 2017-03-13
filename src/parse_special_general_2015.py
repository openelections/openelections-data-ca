import numpy as np
import pandas as pd
import requests
import tempfile
import zipfile

from bs4 import BeautifulSoup

candidates = ['Susan Bonilla', 'Steve Glazer']
parties = {'Susan Bonilla': 'DEM',
           'Steve Glazer': 'DEM'}
output_columns = ['county', 'precinct', 'office',
                  'district', 'party', 'candidate', 'votes']


def read_excel_xml(f):
    soup = BeautifulSoup(f.read(), 'xml')
    workbook = []
    for sheet in soup.findAll('Worksheet'):
        sheet_as_list = []
        for row in sheet.findAll('Row'):
            row_as_list = []
            for cell in row.findAll('Cell'):
                row_as_list.append(cell.Data.text)
            sheet_as_list.append(row_as_list)
        workbook.append(sheet_as_list)
    return workbook


def prepare_output(df, county):
    df.columns = ['precinct'] + candidates
    df = pd.melt(df, id_vars='precinct',
                 value_vars=candidates, var_name='candidate', value_name='votes').dropna()
    df['party'] = df.candidate.apply(lambda x: parties[x])

    df = df.assign(county=county,
                   office='State Senate',
                   district=7)
    df.votes = df.votes.astype(int)

    df = df.groupby(
        output_columns[:-1]).sum().reset_index()[output_columns]
    return df


def parse_alameda():
    sovc_xls = 'https://www.acgov.org/rov/elections/20150519/documents/sovc.xls'
    general = pd.read_excel(sovc_xls, sheetname='Sheet1')

    # Select only contests of interest and the important columns
    general = general.loc[(general.index > 5) & (general.index < 386)][
        ['Alameda County', 'Unnamed: 7', 'Unnamed: 8']]

    prepare_output(general, 'Alameda').to_csv(
        '2015/20150519__ca__special__general__alameda__precinct.csv', header=output_columns, index=False)


def parse_contra_costa():
    sovc_zip_url = 'http://www.cocovote.us/wp-content/uploads/051915_Detail_xls.zip'
    sovc_zip = requests.get(sovc_zip_url)
    if sovc_zip.status_code != 200:
        return
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    table = read_excel_xml(sovc_zf.open('detail.xls'))

    df = pd.DataFrame(np.array(table[2][3:-1])[:, (0, 4, 7)])

    prepare_output(df, 'Contra Costa').to_csv(
        '2015/20150519__ca__special__general__contra_costa__precinct.csv', header=output_columns, index=False)


def main():
    parse_alameda()
    parse_contra_costa()

if __name__ == "__main__":
    main()
