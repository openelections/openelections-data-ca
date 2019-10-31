"""
This python script contains commonly used functions to help with parsing in the openelections project.

Original Author: Tiffany Xiao
Date Created: 10/9/2019
"""

import csv
import PyPDF2

def csv_to_dict(csv_file_name):
    '''Function to convert a csv with two columns into a dictionary (the first column is the value and the second column is the key.'''
    # csv_dict is the dictionary the key:value pairs will be saved into
    csv_dict = {}
    # open the csv
    with open(csv_file_name) as csvfile:
        readCSV = csv.reader(csvfile, delimiter=',')
        line_num = 0
        # go through every row in the csv and create the dict key+values
        for row in readCSV:
            if (not line_num == 0):
                row_key = row[1]
                row_value = row[0]
                csv_dict[row_key] = row_value
            line_num += 1
    return csv_dict


def standardize_office_name(office):
    ''' Function to change office name into the standard office name as requested by Derek.'''
    # this list contains words that would immediately indicate it's not a state office 
    not_accepted_offices = ["city"]
    name = clean_string(office)
    lieutenant_governor_list = ["lt.","lieutenant", "lt governor"]
    if (any(clean_string(item) in name for item in lieutenant_governor_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Lieutenant Governor"
    governor_list = ["governor"]
    if (any(clean_string(item) in name for item in governor_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Governor"
    attorney_general_list = ["attorney general"]
    if (any(clean_string(item) in name for item in attorney_general_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Attorney General"
    us_senate_list = ["us senator", "united states senator", "us senate"]
    if (any(clean_string(item) in name for item in us_senate_list)  and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "US Senate"
    state_senate_list = ["state senate"]
    if (any(clean_string(item) in name for item in state_senate_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "State Senate"
    state_assembly_list = ["state assembly", "member of the state assembly", "assembly"]
    if (any(clean_string(item) in name for item in state_assembly_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Assembly"
    secretary_of_state_list = ["secretary of state"]
    if (any(clean_string(item) in name for item in secretary_of_state_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Secretary of State"
    controller_list = ["controller"]
    if (any(clean_string(item) in name for item in controller_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Controller"
    treasurer_list = ["treasurer"]
    if (any(clean_string(item) in name for item in treasurer_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Treasurer"
    insurance_commissionar_list = ["insurance commissioner"]
    if (any(clean_string(item) in name for item in insurance_commissionar_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Insurance Commissioner"
    public_instruction_list = ["public instruction"]
    if (any(clean_string(item) in name for item in public_instruction_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "Public Instruction"
    us_house_list = ["us house","u.s. house", "united state house", "us representative"]
    if (any(clean_string(item) in name for item in us_house_list) and not(any(clean_string(item) in name for item in not_accepted_offices))):
        return "US House"
    master_list = lieutenant_governor_list + governor_list + attorney_general_list + us_senate_list + state_senate_list + state_assembly_list + secretary_of_state_list + controller_list + treasurer_list + insurance_commissionar_list + public_instruction_list + us_house_list
    if (office == "master"):
        return master_list, not_accepted_offices
    return None

def bool_accepted_office(office_string):
    ''' Function to determine if any accepted office is in the inputted string'''
    accepted_offices, not_accepted_offices = standardize_office_name("master")
    if (any(clean_string(item) in clean_string(office_string) for item in accepted_offices) and not(any(clean_string(item) in clean_string(office_string) for item in not_accepted_offices))):
        return True
    else: 
        return False

def clean_string(string):
    ''' Function to clean a string'''
    # remove all whitespace
    string = string.replace(" ", "")
    # lowercase the string
    string = string.lower()
    return string

def rotate_pdf_90(pdf_file_name):
    ''' Function to rotate a pdf file 90 degrees '''
    pdf_in = open(pdf_file_name, 'rb')
    pdf_reader = PyPDF2.PdfFileReader(pdf_in)
    pdf_writer = PyPDF2.PdfFileWriter()

    for pagenum in range(pdf_reader.numPages):
        page = pdf_reader.getPage(pagenum)
        page.rotateClockwise(90)
        pdf_writer.addPage(page)

    pdf_out_name = pdf_file_name+'rotated.pdf'

    pdf_out = open(pdf_out_name, 'wb')
    pdf_writer.write(pdf_out)
    pdf_out.close()
    pdf_in.close()
    
    return pdf_out_name