import csv
import pandas as pd
import numpy as np

class Table:
    ''' Class to create a table '''
    def __init__(self, list_of_rows=[]):
        ''' Initalize the table with a list of rows (optional parameter)'''
        self.list_of_rows = list_of_rows

    def add_to_table(self, row):
        ''' Add the row of data to a table '''
        self.list_of_rows.append(row)
    
    def convert_to_csv(self, name_of_csv):
        ''' Convert entire table to the desired csv format'''
        lists = []
        for row in self.list_of_rows:
            lists.append(row.row_to_list())
        # clean dataframe of missing optional columns 
        df = pd.DataFrame(lists, columns = ['precinct', 'office', 'district', 'party', 'candidate', 'votes', 'early_voting', 'election_day', 'provisional', 'absentee', 'federal','county'])
        col_list = ['early_voting', 'election_day', 'provisional', 'absentee', 'federal']
        v = df[col_list].notna().sum().le(2)
        df.drop(v.index[v], axis=1, inplace=True)
        df.to_csv(name_of_csv)

class Row:
    '''Class to create a row for a table using headers indicated at: https://github.com/openelections/openelections-data-ny/issues/59'''

    def __init__(self, precinct, office, district, party, candidate, votes, early_voting=None, election_day=None, provisional=None, absentee=None, federal=None, county=None):
        '''Initialize a row with 6 mandatory headers (precinct ... votes) and 5 optional headers (early_voting ... federal)'''
        self.precinct = precinct
        self.office = office
        self.district = district
        self.party = party
        self.candidate = candidate
        self.votes = votes
        self.early_voting = early_voting
        self.election_day = election_day
        self.provisional = provisional
        self.absentee = absentee
        self.federal = federal
        self.county = county

    def row_to_list(self):
        ''' Convert the row object to a list'''
        return [self.precinct, self.office, self.district, self.party, self.candidate, self.votes, self.early_voting, self.election_day, self.provisional, self.absentee, self.federal, self.county]
