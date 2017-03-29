import pandas as pd
import requests
import tempfile
import zipfile

candidates = {'JOHN M. W. MOORLACH': 'John M. W. Moorlach',
              'DONALD P. WAGNER': 'Donald P. Wagner',
              'NAZ NAMAZI': 'Naz Namazi'}
output_columns = ['county', 'precinct', 'office',
                  'district', 'party', 'candidate', 'votes']


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

    table[output_columns].to_csv(
        '2015/20150317__ca__special__primary__orange__precinct.csv', header=output_columns, index=False)


def main():
    parse_orange()

if __name__ == "__main__":
    main()
