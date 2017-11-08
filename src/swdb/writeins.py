import io
import numpy as np
import pandas as pd
import requests
import tabula
import PyPDF2

p = {'Karen Jill Bernal': 'DEM',
     'John Henry Kimack': 'NPP',
     'Joy D. Delepine':   'REP',
     'Virginia Fuller':   'AI'}


def alameda_p14(candidate_norm):
    writeins_url = 'https://www.acgov.org/rov/elections/20140603/documents/OfficialWrite-in-Tally.pdf'
    writeins_req = requests.get(writeins_url)
    writeins_req.raise_for_status()
    writeins_pdf = PyPDF2.PdfFileReader(io.BytesIO(writeins_req.content))
    cands = writeins_pdf.getPage(0).extractText().split('\n')[7::3]
    cands = [c.strip(' ') for c in cands]
    cand_split = [(c.split(' ' * 7)[0],
                   int(c.split(' ' * 7)[1].strip())) for c in cands]
    return [{'candidate': candidate_norm[c],
             'votes': v,
             'county': 'Alameda',
             'office': 'Governor',
             'party': 'DEM',
             'precinct': 'Write-In'} for
            c, v in cand_split if v != 0]


def amador_p14(_):
    return [{'candidate': 'Patrick D. Hogan',
             'county': 'Amador',
             'office': 'State Assembly',
             'district': '5',
             'party': 'LIB',
             'precinct': 'Write-In',
             'votes': 5}]


def calaveras_p14(_):
    return [{'candidate': 'Patrick D. Hogan',
             'county': 'Calaveras',
             'office': 'State Assembly',
             'district': '5',
             'party': 'LIB',
             'precinct': 'Write-In',
             'votes': 4}]


def contra_costa_p14(_):
    # TODO(charles-difazio): Grab this in a single parse and then split
    gov_df = tabula.read_pdf(
        'http://www.cocovote.us/wp-content/uploads/14Jun03_ContraCostaStatementofVote.pdf', pages=list(range(465, 483)))
    house_df = tabula.read_pdf(
        'http://www.cocovote.us/wp-content/uploads/14Jun03_ContraCostaStatementofVote.pdf', pages=list(range(483, 495)))
    assembly_df = tabula.read_pdf(
        'http://www.cocovote.us/wp-content/uploads/14Jun03_ContraCostaStatementofVote.pdf', pages=list(range(495, 501)))

    # Rename candidate columns
    gov_df.columns = ['precinct'] + \
        gov_df['Unnamed: 4'][3:6].tolist() + ['dummy']
    # Drop NA rows and total row
    gov_df = gov_df[gov_df.columns[:-1]].dropna(how='any')[:-1]

    # Tidy data
    gov_df = pd.melt(gov_df, id_vars='precinct', value_vars=gov_df.columns[1:],
                     var_name='candidate', value_name='votes')
    gov_df.votes = gov_df.votes.astype(np.int64)
    gov_df = gov_df[gov_df.votes != 0].assign(county='Contra Costa',
                                              office='Governor')
    gov_df['party'] = gov_df.candidate.apply(lambda x: p[x])
    gov_df.precinct = gov_df.precinct.apply(lambda x: x.split(' ')[1])

    house_df = house_df.rename(columns={'2014 STATEWIDE PRIMARY': 'precinct',
                                        'Unnamed: 1': 'Virginia Fuller'})
    house_df['Virginia Fuller'] = pd.to_numeric(
        house_df['Virginia Fuller'], errors='coerce')
    house_df = house_df.dropna(how='any')[:-1]
    house_df = house_df[house_df.precinct != 'CANDIDATES']

    house_df = pd.melt(house_df, id_vars='precinct', value_vars=house_df.columns[1:],
                       var_name='candidate', value_name='votes')
    house_df.votes = house_df.votes.astype(np.int64)
    house_df = house_df[house_df.votes != 0].assign(county='Contra Costa',
                                                    office='U.S. House',
                                                    district='11')
    house_df['party'] = house_df.candidate.apply(lambda x: p[x])
    house_df.precinct = house_df.precinct.apply(
        lambda x: x.split(' ')[1])

    c = assembly_df['Unnamed: 2'][3:5].tolist()
    assembly_df[c[0]], assembly_df[c[1]] = assembly_df[
        'Unnamed: 1'].str.split(' ', n=1).str
    assembly_df = assembly_df.rename(
        columns={'2014 STATEWIDE PRIMARY': 'precinct'})
    assembly_df[c[0]] = pd.to_numeric(assembly_df[c[0]], errors='coerce')
    assembly_df[c[1]] = pd.to_numeric(assembly_df[c[1]], errors='coerce')
    assembly_df = assembly_df[['precinct'] + c]
    assembly_df = assembly_df.dropna(how='any')[:-1]

    assembly_df = pd.melt(assembly_df, id_vars='precinct', value_vars=assembly_df.columns[1:],
                          var_name='candidate', value_name='votes')
    assembly_df.votes = assembly_df.votes.astype(np.int64)
    assembly_df = assembly_df[assembly_df.votes != 0].assign(county='Contra Costa',
                                                             office='State Assembly',
                                                             district='14')
    assembly_df['party'] = assembly_df.candidate.apply(lambda x: p[x])
    assembly_df.precinct = assembly_df.precinct.apply(
        lambda x: x.split(' ')[1])

    return gov_df.to_dict(orient='records') + \
        house_df.to_dict(orient='records') + \
        assembly_df.to_dict(orient='records')


def el_dorado_p14(candidate_norm):
    writeins_url = 'https://www.edcgov.us/elections/election/sov/095.write-in.pdf'
    writeins_req = requests.get(writeins_url)
    writeins_req.raise_for_status()
    writeins_pdf = PyPDF2.PdfFileReader(io.BytesIO(writeins_req.content))
    cands = writeins_pdf.getPage(0).extractText()[162:180]
    cand_split = [(cands[:-2], int(cands[-2:]))]
    return [{'candidate': candidate_norm[c],
             'county': 'El Dorado',
             'office': 'State Assembly',
             'district': '5',
             'party': 'LIB',
             'precinct': 'Write-In',
             'votes': v} for
            c, v in cand_split if v != 0]

WRITEINS = {'P14': {'Alameda':   alameda_p14,
                    'Amador':    amador_p14,
                    'Calaveras': calaveras_p14,
                    'Contra Costa': contra_costa_p14,
                    'El Dorado': el_dorado_p14}}
