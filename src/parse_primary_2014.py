import pandas as pd
import re

from swdb.util import COUNTIES

url_prefix = 'http://elections.cdn.sos.ca.gov/sov/2014-primary/xls/'
state_level_files = [
    ('33-governor.xls', 'Governor'),
    ('42-lieutenant-governor.xls', 'Lieutenant Governor'),
    ('45-secretary-of-state.xls', 'Secretary of State'),
    ('48-controller.xls', 'Controller'),
    ('51-treasurer.xls', 'Treasurer'),
    ('54-attorney-general.xls', 'Attorney General'),
    ('57-insurance-commissioner.xls', 'Insurance Commissioner'),
    ('104-superintendent-of-public-instruction.xls',
     'Superintendent of Public Instruction')
]

district_files = [
    ('60-board-of-equalization.xls', 'Board of Equalization'),
    ('63-congress.xls', 'U.S. House'),
    ('78-state-senator.xls', 'State Senate'),
    ('84-state-assemblymember.xls', 'State Assembly'),
]

proposition_file = '107-ballot%20measures.xls'

fieldnames = ["county", "office", "district", "party", "candidate", "votes"]

candidates = {'Kevin Mc Carthy': 'Kevin McCarthy',
              'Diana Rodriguez- Suruki': 'Diana Rodriguez-Suruki'}


def parse_candidate(value):
    return ' '.join(value.strip("*").replace('\n', ' ').split())


def parse(fname, office, district):
    print(fname)
    df = pd.read_excel(
        url_prefix + fname).dropna().reset_index().rename(columns={'index': 'county'}).rename(columns=parse_candidate)
    parties = df[df.columns.tolist()[1:]].iloc[0].to_dict()
    df = df[df.county.isin(COUNTIES)]
    df = pd.melt(df, id_vars='county', value_vars=df.columns.tolist()[
                 1:], var_name='candidate', value_name='votes')
    df['party'] = df.candidate.apply(lambda x: parties[x])
    df = df.assign(office=office, district=district)
    return df[fieldnames]


def parse_sub(sub, office, district):
    sub = sub.reset_index(drop=True)

    # Special case these. Needs to be cleaned up and generalized.
    if (office, district) == ('U.S. House', '33'):
        sub = pd.concat([sub.iloc[0:4,   0:-1].reset_index(drop=True),
                         sub.iloc[5:9,   1:-1].reset_index(drop=True),
                         sub.iloc[10:14, 1:].reset_index(drop=True)], axis=1).dropna(how='all')
    elif (office, district) == ('State Assembly', '33'):
        sub = pd.concat([sub.iloc[0:4, 0:-1].reset_index(drop=True),
                         sub.iloc[5:9, 1:].reset_index(drop=True)], axis=1).dropna(how='all')
    elif (office, district) == ('U.S. House', '24'):
        sub = pd.concat([sub.iloc[0:6,  0:-1].reset_index(drop=True),
                         sub.iloc[7:13, 1:].reset_index(drop=True)], axis=1).dropna(how='all')

    sub.columns = ['county'] + \
        sub.iloc[:, 1:-1].iloc[0].fillna('').tolist() + ['office']
    sub = sub.dropna(axis=1, how='all')
    sub = sub.rename(columns=parse_candidate)
    parties = sub.iloc[:, 1:-1].iloc[1].to_dict()
    sub = sub[sub.county.isin(COUNTIES)]
    sub = pd.melt(sub, id_vars=['county', 'office'], value_vars=sub.columns.tolist()[
        1:-1], var_name='candidate', value_name='votes')
    sub['party'] = sub.candidate.apply(lambda x: parties[x])
    sub = sub.assign(office=office, district=district)
    return sub[fieldnames]


def parse_district(fname, office):
    print(fname)
    df = pd.read_excel(
        url_prefix + fname, header=None)
    df.columns = ['county'] + ['cand%d' % x for x in range(1, len(df.columns))]
    df['office'] = df.county.str.endswith('District', na=False)
    df['office'] = df[df.county.str.endswith(
        'District', na=False)]
    df.office = df.office.fillna(method='pad')
    return pd.concat([parse_sub(df[df.office == district][df.cand1.notnull()], office, re.sub("[^\d]+", "", district)) for district in df.office.unique()])


def parse_propositions(fname):
    df = pd.read_excel(url_prefix + fname,
                       header=None).fillna(axis=1, method='pad')
    df.columns = df.iloc[0].fillna(
        'county') + ',' + df.iloc[3].fillna('').str.lstrip(' ')
    df = df.rename(columns={'county,': 'county'})
    df = df[df.county.isin(COUNTIES)]
    df = pd.melt(df, id_vars=['county'], value_vars=df.columns.tolist()[
        1:], var_name='cand_office', value_name='votes')
    oc = df['cand_office'].apply(lambda x: pd.Series(x.split(',')))
    df['office'] = oc[0]
    df['candidate'] = oc[1]
    df = df.assign(party='', district='')
    return df[fieldnames]


def main():
    df = pd.concat([parse(fname, office, '')
                    for fname, office in state_level_files] +
                   [parse_district(fname, office)
                    for fname, office in district_files] +
                   [parse_propositions(proposition_file)]).replace({'candidate': candidates})
    for x in ['candidate', 'district', 'office', 'county']:
        df = df.sort_values(by=x, kind='mergesort')
    df.to_csv('2014/20140603__ca__primary.csv', index=False)

if __name__ == "__main__":
    main()
