import pandas as pd
import re

from swdb.util import COUNTIES

url_prefix = 'http://elections.cdn.sos.ca.gov/sov/2014-general/xls/'
state_level_files = [
    ('19-governor.xls', 'Governor'),
    ('22-lieutenant-governor.xls', 'Lieutenant Governor'),
    ('25-secretary-of-state.xls', 'Secretary of State'),
    ('28-controller.xls', 'Controller'),
    ('31-treasurer.xls', 'Treasurer'),
    ('34-attorney-general.xls', 'Attorney General'),
    ('37-insurance-commissioner.xls', 'Insurance Commissioner'),
    ('85-superintendent-of-public-instruction.xls',
     'Superintendent of Public Instruction')
]

district_files = [
    ('40-board-of-equalization.xls', 'Board of Equalization'),
    ('43-congress.xls', 'U.S. House'),
    ('58-state-senator.xls', 'State Senate'),
    ('64-state-assemblymember.xls', 'State Assembly'),
]

proposition_file = '88-ballot-measures.xls'


fieldnames = ["county", "office", "district", "party", "candidate", "votes"]


def parse_candidate(value):
    return ' '.join(value.strip("*").replace('\n', ' ').split())


def parse(fname, office, district):
    df = pd.read_excel(
        url_prefix + fname).dropna().reset_index().rename(columns={'index': 'county'}).rename(columns=parse_candidate)
    parties = df[[1, 2]].iloc[0].to_dict()
    df = df[df.county.isin(COUNTIES)]
    df = pd.melt(df, id_vars='county', value_vars=df.columns.tolist()[
                 1:], var_name='candidate', value_name='votes')
    df['party'] = df.candidate.apply(lambda x: parties[x])
    df = df.assign(office=office, district=district)
    return df[fieldnames]


def parse_sub(sub, office, district):
    sub.columns = ['county'] + sub[[1, 2]].iloc[0].tolist() + ['office']
    sub = sub.dropna(axis=1, how='all')
    sub = sub.rename(columns=parse_candidate)
    parties = sub[[1, 2]].iloc[1].to_dict()
    sub = sub[sub.county.isin(COUNTIES)]
    sub = pd.melt(sub, id_vars=['county', 'office'], value_vars=sub.columns.tolist()[
        1:-1], var_name='candidate', value_name='votes')
    sub['party'] = sub.candidate.apply(lambda x: parties[x])
    sub = sub.assign(office=office, district=district)
    return sub[fieldnames]


def parse_district(fname, office):
    df = pd.read_excel(
        url_prefix + fname, header=None, names=['county', 'cand1', 'cand2'])
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
                   [parse_propositions(proposition_file)])
    for x in ['candidate', 'district', 'office', 'county']:
        df = df.sort_values(by=x, kind='mergesort')
    df.to_csv('2014/20141104__ca__general.csv', index=False)

if __name__ == "__main__":
    main()
