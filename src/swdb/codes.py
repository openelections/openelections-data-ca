import requests


office_dict = {'PRS': 'President',
               'USS': 'U.S. Senate',
               'GOV': 'Governor',
               'LTG': 'Lieutenant Governor',
               'SOS': 'Secretary of State',
               'CON': 'Controller',
               'TRS': 'Treasurer',
               'ATG': 'Attorney General',
               'INS': 'Insurance Commissioner',
               'SPI': 'Superintendent of Public Instruction',
               'BOE': 'Board of Equalization',
               'CNG': 'U.S. House',
               'SEN': 'State Senate',
               'ASS': 'State Assembly'}

prop_dict = {'Y': 'Yes',
             'N': 'No'}


class Entry(object):

    def __init__(self, split):
        self.candidate = ' '.join(split[1:-1]).strip('*')
        self.__process(split[0])

    def __process(self, code):
        if code[0:3] == 'PR_':
            self.office = 'Proposition ' + code.split('_')[1]
            self.candidate = prop_dict[code[-1]]
        else:
            self.office = office_dict[code[0:3]]

        if len(code) < 8:
            self.district = ''
            self.party = ''
        elif len(code) == 8:
            self.district = ''
            self.party = code[3:6]
        else:
            self.district = int(code[3:5])
            self.party = code[5:8]

    def __repr__(self):
        d = {'candidate': self.candidate,
             'office':    self.office,
             'party':     self.party}
        if self.district:
            d['district'] = self.district

        return repr(d)


class Codes(object):

    def __init__(self, fname, candidate_lookup):
        self.data = requests.get(fname)
        self.data.raise_for_status()

        self.candidate_lookup = candidate_lookup
        self.__parse()

    def __parse(self):
        self.code_dict = {}
        for line in self.data.iter_lines():
            split = str(line, self.data.apparent_encoding).strip().split()
            if split[0] == 'TOTREG' or split[0] == 'TOTVOTE':
                continue
            entry = Entry(split)
            if entry.candidate in self.candidate_lookup:
                entry.candidate = self.candidate_lookup[entry.candidate]
            self.code_dict[split[0]] = entry

    def office(self, column):
        if column.startswith('PR_'):
            return 'Proposition ' + column.split('_')[1]

        return office_dict[column[0:3]]

    def party(self, column):
        if column.startswith('PR_'):
            return ''

        return column[-5:-2]

    def lookup(self, column, district=None):
        key = None
        if district:
            key = (column[0:3] + '%02d' + column[3:]) % district
        else:
            key = column
        return self.code_dict[key]
