import io
import pandas as pd
import requests
import tempfile
import zipfile
import PyPDF2

candidates = {'JOHN M. W. MOORLACH': 'John M. W. Moorlach',
              'DONALD P. WAGNER': 'Donald P. Wagner',
              'NAZ NAMAZI': 'Naz Namazi',
              'SHARON RUNNER': 'Sharon Runner',
              'JOSHUA C. CHANDLER': 'Joshua C. Chandler',
              'JOSHUA CONAWAY': 'Joshua Conaway',
              'STEVE HILL': 'Steve Hill',
              'JERRY J. LAWS': 'Jerry J. Laws',
              'RICHARD E. MACIAS': 'Richard E. Macias',
              'JASON ZINK': 'Jason Zink'}
output_columns = ['county', 'precinct', 'office',
                  'district', 'party', 'candidate', 'votes']

p = {'Sharon Runner':      'REP',
     'Terry Kremin':       'DEM',
     'Susan Bonilla':      'DEM',
     'Joan Buchanan':      'DEM',
     'Michaela M. Hertle': 'REP',
     'Steve Glazer':       'DEM'}


def prepare_output(df, county, cand):
    df.columns = ['precinct'] + cand
    df = pd.melt(df, id_vars='precinct',
                 value_vars=cand, var_name='candidate', value_name='votes').dropna()
    df['party'] = df.candidate.apply(lambda x: p[x])

    df = df.assign(county=county,
                   office='State Senate',
                   district=7)
    df.votes = df.votes.astype(int)

    df = df.groupby(
        output_columns[:-1]).sum().reset_index()[output_columns]
    return df


def parse_alameda():
    sovc_xls = 'https://www.acgov.org/rov/elections/20150317/documents/sovc.xls'
    primary = pd.read_excel(sovc_xls, sheetname='Sheet1')

    # Select only contests of interest and the important columns
    primary = primary.loc[(primary.index > 3) & (primary.index < 385)][
        ['Alameda County', 'Unnamed: 7', 'Unnamed: 8', 'Unnamed: 10', 'Unnamed: 11', 'Unnamed: 12']]

    table = prepare_output(primary, 'Alameda',
                           ['Terry Kremin', 'Susan Bonilla', 'Joan Buchanan', 'Michaela M. Hertle', 'Steve Glazer'])
    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table.to_csv(
        '2015/20150317__ca__special__primary__alameda__precinct.csv', header=output_columns, index=False)


def parse_orange():
    sovc_zip_url = 'http://www.ocvote.com/fileadmin/live/37sd2015/media.zip'
    sovc_zip = requests.get(sovc_zip_url)
    if sovc_zip.status_code != 200:
        return
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    table = pd.read_csv(sovc_zf.open('contest_table.txt'))
    table['votes'] = table[
        ['Absentee_votes', 'Early_votes', 'Election_Votes']].sum(axis=1)
    table.Choice_party.fillna('W/I', inplace=True)

    table = table.rename(
        columns={'Precinct_Name': 'precinct',
                 'Candidate_name': 'candidate',
                 'Choice_party': 'party'}).assign(county='Orange',
                                                  office='State Senate',
                                                  district='37').replace(
                     {'candidate': candidates})

    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2015/20150317__ca__special__primary__orange__precinct.csv', header=output_columns, index=False)


def los_angeles_sovc():
    sovc_zip_url = 'https://www.lavote.net/documents/SVC/960_SVC_Excel.zip'
    sovc_zip = requests.get(sovc_zip_url)
    sovc_zip.raise_for_status()
    f = tempfile.NamedTemporaryFile()
    f.write(sovc_zip.content)
    sovc_zf = zipfile.ZipFile(f.name)
    df = pd.read_excel(sovc_zf.open(
        '21ST_STATE_SENATE_U-T_03-17-15_Voter_Nominated_by_Precinct_960-3760.xls'))

    df.columns = df.loc[1]
    df = df[df.TYPE == 'TOTAL']
    return pd.melt(df, id_vars=['PRECINCT'], value_vars=df.columns.tolist()[
        8:-1], var_name='candidate', value_name='votes')


def los_angeles_writeins():
    writeins_url = 'https://www.lavote.net/Documents/Election_Info/03172015_Certificate-of-Write-in-Votes_FINAL.pdf'
    writeins_req = requests.get(writeins_url)
    writeins_req.raise_for_status()
    writeins_pdf = PyPDF2.PdfFileReader(io.BytesIO(writeins_req.content))
    cands = writeins_pdf.getPage(0).extractText().split('\n')[58:82:2]
    return [{'candidate': c, 'votes': int(v), 'PRECINCT': 'Write-In'} for
            c, v in zip(cands[::2], cands[1::2])]


def parse_los_angeles():
    output_columns = ['county', 'precinct', 'office',
                      'district', 'party', 'candidate', 'votes']

    table = los_angeles_sovc().append(los_angeles_writeins())
    table = table.assign(county='Los Angeles', office='State Senate', district='21').rename(
        columns={'PRECINCT': 'precinct'}).replace({'candidate': candidates})

    parties = {k: 'W/I' for k in candidates.values()}
    parties.update(p)

    table['party'] = table.candidate.apply(lambda x: parties[x])
    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        table = table.sort_values(by=x, kind='mergesort')
    table[output_columns].to_csv(
        '2015/20150317__ca__special__primary__los_angeles__precinct.csv', index=False)


def main():
    parse_alameda()
    parse_orange()
    parse_los_angeles()

if __name__ == "__main__":
    main()
