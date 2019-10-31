'''
Description: A generic parser for pdfs in similar formats to the Modoc, Plumas and Sonoma counties. Please see readme for more documentation. 
County & Year: Modoc 2018, Plumas 2018, Sonoma 2018
Author: Tiffany Xiao
Date Last Edited: 10/28/2019 
'''
from tabula import wrapper
import pandas as pd
import math
import csv
from table import Table, Row
from utils import csv_to_dict, standardize_office_name, rotate_pdf_90, bool_accepted_office, clean_string

def pdf_to_text(pdf_name, columns_vertical_bool, tables_area, offices_area, column_names_area):
    '''Function to read text from pdf using tabula library into three separate lists (list of tables, list of offices and list of column headers)'''
    # get all tables (area of row only = (171.743,0.383,790.628,611.618))
    list_of_tables = wrapper.read_pdf(pdf_name, stream=True, multiple_tables=True, pages='all', area=(tables_area[0], tables_area[1], tables_area[2], tables_area[3]), guess=False)
    
    # get all office names
    list_of_offices = wrapper.read_pdf(pdf_name, stream=True, multiple_tables=True, pages='all', area=(offices_area[0], offices_area[1], offices_area[2], offices_area[3]), guess=False)
    
    # get all column names 
    # if there are vertical columns, run the helper function (vertical_column_names)
    if columns_vertical_bool == "y":    
        list_of_column_names = vertical_column_names(pdf_name, column_names_area)
    # if there aren't vertical columns, extract normally
    elif columns_vertical_bool == "n":  
        list_of_column_names = wrapper.read_pdf(pdf_name, stream=True, multiple_tables=True, pages='all', area=(column_names_area[0], column_names_area[1], column_names_area[2], column_names_area[3]), guess=False)

    return list_of_tables, list_of_offices, list_of_column_names

def vertical_column_names(pdf_name, column_names_area):
    ''' Function to extract vertical column names by rotating the file and using tabula '''
    rotated_pdf_name = rotate_pdf_90(pdf_name)
    list_of_column_names = wrapper.read_pdf(rotated_pdf_name, stream=True, multiple_tables=True, pages='all', area=(column_names_area[0], column_names_area[1], column_names_area[2], column_names_area[3]), guess=False)

    return list_of_column_names

def clean_list(list_of_tables, list_of_offices, list_of_column_names, multiple_tables_bool, num_fixed_columns, multiple_rows_bool, num_rows, num_precinct_start_index, votes_dict, columns_vertical_bool, multiple_offices_bool, last_row_title, num_precinct_end_index, percentages_bool, num_start_rows):
    ''' Function to clean the list up before conversion into the CSV '''
    # clean office names
    cleaned_offices = []
    for i in range(len(list_of_offices)):
        sample_df = pd.DataFrame(list_of_offices[i])
        cleaned_offices.append(sample_df.iat[0,0])

    # clean column names - some columns names span 2 rows in the non vertical-column names 
    # (this code will append them together). cleaned_columns_full is for cleaning the vertical 
    # columns of the Sonoma file where multiple rows belong to one column (properly appending
    # the names for vertical columns will be dealt with later)
    cleaned_columns_full = []
    cleaned_columns = []
    for i in range(len(list_of_column_names)):
        sample_df = pd.DataFrame(list_of_column_names[i])
        sample_cleaned_columns = []
        sample_cleaned_columns_full = []
        for j in range(len(sample_df.columns)):
            column_name = ""
            for k in range(len(sample_df.index)):
                if columns_vertical_bool == "y":
                    column_name = sample_df.iat[k,0]
                    sample_cleaned_columns_full.append(str(column_name))
                try:
                    float_n = float(sample_df.iat[k,j])
                except ValueError:
                    column_name += str(sample_df.iat[k,j])
                    if columns_vertical_bool == "y":
                        sample_cleaned_columns.append(str(column_name))
            if columns_vertical_bool == "n":
                sample_cleaned_columns.append(column_name)
        cleaned_columns_full.append(sample_cleaned_columns_full)
        cleaned_columns.append(sample_cleaned_columns)
    
    # merge multiple tables together if there are any (the pdf reader registers each page 
    # as an indiviudal table, so we need to append the ones for the same offices together)
    new_list_of_tables = []
    new_list_of_columns = []
    new_list_of_columns_full = []
    new_list_of_offices = []
    if (multiple_tables_bool == "y"):
        current_columns = cleaned_columns[0]
        current_columns_full = cleaned_columns_full[0]
        current_office = cleaned_offices[0]
        current_table = pd.DataFrame(list_of_tables[0])
        if (multiple_offices_bool == "y"):
            current_table = current_table.dropna(axis='columns', how='all')
        for i in range(len(cleaned_offices)):
            if (bool_accepted_office(cleaned_offices[i])) and ("measure" not in clean_string(cleaned_offices[i])):
                sample_df = pd.DataFrame(list_of_tables[i])
                if (multiple_offices_bool == "y"):
                    sample_df = sample_df.dropna(axis='columns', how='all')
                    sample_df.columns = range(sample_df.shape[1])
                if (cleaned_offices[i] != current_office):
                    if ((not current_office == cleaned_offices[0]) or (multiple_offices_bool == "y")):
                        new_list_of_tables.append(current_table)
                        new_list_of_columns.append(current_columns)
                        new_list_of_columns_full.append(current_columns_full)
                        new_list_of_offices.append(current_office)
                    current_office = cleaned_offices[i]
                    current_columns = cleaned_columns[i]
                    current_columns_full = cleaned_columns_full[i]
                    current_table = sample_df
                elif ((cleaned_offices[i] == current_office) and (i!=0)):
                    current_table = current_table.append(sample_df)
        # add the last table 
        new_list_of_tables.append(current_table)
        new_list_of_columns.append(current_columns)
        new_list_of_columns_full.append(current_columns_full)
        new_list_of_offices.append(current_office)
    else: 
        current_columns = None
        current_office = None
        current_table = None
        for i in range(len(cleaned_offices)):
            if bool_accepted_office(cleaned_offices[i]):
                current_office = cleaned_offices[i]
                current_columns = cleaned_columns[i]
                current_table = pd.DataFrame(list_of_tables[i])
                new_list_of_tables.append(current_table)
                new_list_of_columns.append(current_columns)
                new_list_of_offices.append(current_office)

    # if there are multiple offices in one table, split the dataframe into separate dataframes by office
    if (multiple_offices_bool == "y"):
        # split the dataframe, first identify the starting indexes of the columns 
        office_indexes = []
        split_offices = []
        # split the office name 
        for offices in new_list_of_offices:
            split_offices.append(offices.split(" - "))
        # find the starting indexes for each office's data
        for i in range(len(split_offices)):
            col_pos = 4     # value w/o NANs and office names for Sonoma PDF
            col_full_pos = 3    # value with NANs and office names for Sonoma PDF
            saved_col_pos = 3   # value with NANs and office names for Sonoma PDF
            sub_office_indexes = []
            for office_name in split_offices[i]:
                # there is an edge case where if the office name has a comma, it will register
                # two different columns in the column names, so add 2 to the index to track that
                if "," in office_name:
                    col_full_pos+=2 
                else: 
                    col_full_pos+=1
                saved_col_pos = col_pos
                candidates = [office_name]
                # find index of the last column for this office's table
                while(new_list_of_columns_full[i][col_full_pos] != "nan"):
                    candidates.append(new_list_of_columns_full[i][col_full_pos])
                    if (col_full_pos+1 == len(new_list_of_columns_full[i])):
                        break
                    col_pos+=1
                    col_full_pos+=1
                sub_office_indexes.append([office_name,saved_col_pos, candidates])
                col_full_pos+=1
            office_indexes.append(sub_office_indexes)

        # now, split the dataframe according to the indexes
        split_tables = []
        new_list_of_offices = []
        new_list_of_columns = []
        for i in range(len(office_indexes)):
            for j in range(len(office_indexes[i])):
                # edge case: the office is the last office in the table
                if (j+1 != len(office_indexes[i])):
                    office_df = new_list_of_tables[i].iloc[:,office_indexes[i][j][1]:office_indexes[i][j+1][1]]
                else:
                    office_df = new_list_of_tables[i].iloc[:,office_indexes[i][j][1]:]
                # only add it to our master list of offices if it's an accepted office 
                if (bool_accepted_office(office_indexes[i][j][0])):
                    # get first column and insert it 
                    office_df.insert(loc=0,column=None,value=new_list_of_tables[i].iloc[:,0:1])
                    # add headers
                    # edge case: a table with no indicators for multiple line office names
                    temp_office_columns = []
                    try:
                        office_df.columns = office_indexes[i][j][2]
                        temp_office_columns = office_indexes[i][j][2]
                    except ValueError:
                        # add the first two into temp_office_columns 
                        temp_office_columns.append(office_indexes[i][j][2][0]+" "+office_indexes[i][j][2][1])
                        for k in range(2, len(office_indexes[i][j][2])):
                            temp_office_columns.append(office_indexes[i][j][2][k])
                        office_df.columns = temp_office_columns
                    new_list_of_offices.append(office_indexes[i][j][0])
                    new_list_of_columns.append(temp_office_columns[1:])
                    split_tables.append(office_df)
        # save split_tables to new_list_of_tables for future use
        new_list_of_tables = split_tables
    
    # go through every table and create rows 
    all_row_info = []
    all_tables = []
    row_info = {}
    column_position = num_fixed_columns
    for i in range(len(new_list_of_tables)):
        sample_df = new_list_of_tables[i]
        # clean the dataframe 
        sample_df = sample_df.dropna(axis=1, how='all')
        sample_df = sample_df.dropna(axis='rows', how='all') 
        for j in range(len(sample_df.index)):
            # add row info for this table into master list of info for rows (skip non-precinct rows)
            if ((sample_df.iat[j,0]==last_row_title) and (((j-num_start_rows)%num_rows == 0) or multiple_rows_bool=="n")):
                if (i == len(new_list_of_tables)-1):
                    all_row_info.append(row_info)
                break
            for k in range(len(sample_df.columns)):
                # start after "Jurisdiction Wide" row (irrelevant info row at beginning of table)
                if (sample_df.iat[j,0]!="Jurisdiction Wide"):
                    # get the precinct 
                    if ((((j-num_start_rows)%num_rows == 0) or (multiple_rows_bool=="n") or ("PCT" in str(sample_df.iat[j,0]))) and (k==0)): 
                        if (bool(row_info)):
                            all_row_info.append(row_info)
                        row_info = {}
                        if num_precinct_end_index == -1: 
                            row_info['precinct'] = str(sample_df.iat[j,k])[num_precinct_start_index:]
                        else: 
                            row_info['precinct'] = str(sample_df.iat[j,k])[num_precinct_start_index:num_precinct_end_index]
                    # iterate through votes dict and extract the column's information
                    for votes_key, votes_value in votes_dict.items():
                        k, column_position, row_info = extract_row(votes_key, votes_value, sample_df, row_info, new_list_of_offices, new_list_of_columns, column_position, i, j, k, num_fixed_columns, num_rows, percentages_bool)
                    # append row information to row at the end of total 
                    if ((column_position==len(new_list_of_columns[i]))): 
                        column_position = num_fixed_columns
        all_tables.append(all_row_info)
        all_row_info = []
    return all_tables

def extract_row(keyword, column_name, sample_df, row_info, new_list_of_offices, new_list_of_columns, column_position, i, j, k, num_fixed_columns, num_rows, percentages_bool):    
    ''' Function to extract information from each row of table'''
    # add the office and column name to the row
    if (((keyword in str(sample_df.iat[j,0])) or (num_rows==1)) and (k==0)):
        row_info[column_name] = []
        row_info['office'] = new_list_of_offices[i]
    # add the number associated to the column to the row
    if (((keyword in str(sample_df.iat[j,0])) or (num_rows==1)) and (k not in range(0,num_fixed_columns+1))):
        # check if it has a percentage, if not then extract the information and add it to row info
        try: 
            float_n = float(sample_df.iat[j,k])
            if (math.isnan(float_n)):
                return k, column_position, row_info
            else: 
                numbers = str(sample_df.iat[j,k]).split()
                if (not str(sample_df.iat[j,k]).endswith("%")):
                    row_info[column_name].append([new_list_of_columns[i][column_position],numbers[0]])
                    k += 1
                    if (percentages_bool == "n"):
                        column_position += 1
                else: 
                    column_position += 1
        # if it has a percentage, only include the number (the first part of the string)
        except ValueError:
            numbers = str(sample_df.iat[j,k]).split()
            if (len(numbers) == 2):
                row_info[column_name].append([new_list_of_columns[i][column_position],numbers[0]])
                column_position += 1
            else:
                column_position += 1
    return k, column_position, row_info

def list_to_csv(all_tables, county, state, election_day, total_list):
    '''Function to convert all rows into table and row classes (and convert to CSV)'''
    # use the table class included in the utilities package
    current_table = Table()
    for table in all_tables: 
        # create rows from each row 
        for row in table:
            # do for number of candidates 
            for i in range(len(row[total_list[0]])):
                # create total key from other keys if it does not already exists
                if (total_list[0] != "total"):
                    row['total'] = []
                    for k in range(len(row[total_list[0]])):
                        row['total'].append([0,0])
                    row['total'][i][0] = row[total_list[0]][i][0] 
                    row['total'][i][1] = 0
                    for total_key in total_list:
                        row['total'][i][1] += int(row[total_key][i][1])
                # checks to see if the key exists, otherwise it'll be NONE value 
                list_of_values = []
                list_of_csv_column_names = ['precinct', 'office', 'district', 'party', 'total', 'total', 'early_voting','election_day','provisional','absentee', 'federal', 'county']
                for key in list_of_csv_column_names:
                    if key in row:
                        list_of_values.append(row[key])
                    else:
                        list_of_values.append(None)
                # create the row
                current_row = Row(list_of_values[0],standardize_office_name(list_of_values[1]),list_of_values[2],list_of_values[3], checkValue(list_of_values, 4, i, 0), checkValue(list_of_values, 5, i, 1), checkValue(list_of_values, 6, i, 1), checkValue(list_of_values, 7, i, 1), checkValue(list_of_values, 8, i, 1), checkValue(list_of_values, 9, i, 1), checkValue(list_of_values, 10, i, 1), county)
                current_table.add_to_table(current_row)
    # final conversion to csv
    current_table.convert_to_csv(str(election_day)+"__"+state+"__"+"general"+"__"+county+"__precinct.csv")

def checkValue(list_of_values, first_index, second_index, third_index):
    ''' Function to check if the list item is subscriptable - used for list to csv conversion to check if a column's key exists in the row info'''
    if list_of_values[first_index] is None: 
        return None 
    else: 
        return list_of_values[first_index][second_index][third_index]

def main():
    ''' Main function gets user input and calls the three other main functions of the program''' 
    print("-----------QUESTIONS ABOUT PDF-----------")
    county = str(input("Name of County: ")).lower()
    state = str(input("State initials (\"ca\" for California): ")).lower()
    election_day = int(input("Election day (YYYYMMDD format): "))
    name_of_pdf_file = str(input("Input name of PDF:")).replace('\xa0',' ')
    print("-----------QUESTIONS ABOUT PDF FORMAT-----------")
    while True:
        try:
            columns_vertical_bool = input("Are the columns vertical text? (\"y\" for yes or \"n\" for no): ")
            if not(columns_vertical_bool == "y" or columns_vertical_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    while True:
        try:
            multiple_tables_bool = input("Are there multiple pages for a single table (\"y\" for yes or \"n\" for no): ")
            if not(multiple_tables_bool == "y" or multiple_tables_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    while True:
        try:
            multiple_rows_bool = input("Are there multiple rows for a precinct's results (\"y\" for yes or \"n\" for no): ")
            if not(multiple_rows_bool == "y" or multiple_rows_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    if (multiple_rows_bool == "y"):
        num_rows = int(input("How many rows for each precinct? "))
    else: 
        num_rows = 1
    while True:
        try:
            multiple_offices_bool = input("Are there multiple offices per table (\"y\" for yes or \"n\" for no): ")
            if not(multiple_offices_bool == "y" or multiple_offices_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    print("-----------QUESTIONS ABOUT PDF DETAILS-----------")
    last_row_title = str(input("What is the first non-precinct row on the PDF called (example: Total)? "))
    num_fixed_columns = int(input("How many columns come before the first candidate's name? (not including the first column [the one without a column name]): "))
    num_precinct_start_index = int(input("What index does the precinct name START at in a cell? "))
    num_precinct_end_index = int(input("What index does the precinct name END at in a cell? (Put -1 if the entire string is the precinct name) "))
    while True:
        try:
            percentages_bool = input("Are there cells with percentages following every number of votes (\"y\" for yes or \"n\" for no)?: ")
            if not(percentages_bool == "y" or percentages_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    while True:
        try:
            total_bool = input("Is there a row representing total votes for the precinct for the candidate (\"y\" for yes or \"n\" for no)? (if not, then the script will use all other values to calculate the total): ")
            if not(total_bool == "y" or total_bool == "n"):
                raise NameError
            else:
                break
        except NameError:
            print("Not a valid entry, you can only enter \"y\" or \"n\"")
    num_start_rows = int(input("How many non-precinct related rows (rows such as \"Jurisdiction Wide\" for Modoc county files at the top of each table) are at the beginning of each table?"))
    votes_list = str(input("Input a list of all the available vote types: ")).split(",")
    # turn votes_list into a dictionary, also if total_bool is "n" then add it to total list 
    votes_dict = {}
    total_list = []
    votes_key = votes_list[0]
    votes_value = votes_list[1]
    for i in range(len(votes_list)):
        if i%2 == 0:
            votes_key = votes_list[i]
        elif i%2 == 1: 
            if (total_bool == "n"):
                total_list.append(votes_list[i]) 
            votes_value = votes_list[i]
            votes_dict[votes_key] = votes_value
    if (total_bool == "y"):
        total_list.append("total")
    print("Now, enter the areas for each region (tables [without column names], offices and column names). It should look like: \"103.658,0.383,133.493,612.383\" (without quotes)")
    tables_area = list(str(input("Input coordinates of the area of the tables (without the column names):")).split(","))
    offices_area = list(str(input("Input coordinates of the area of the office names:")).split(","))
    column_names_area = list(str(input("Input coordinates of the area of the tables:")).split(","))

    # function calls
    list_of_tables, list_of_offices, list_of_column_names = pdf_to_text(name_of_pdf_file, columns_vertical_bool, tables_area, offices_area, column_names_area)
    list_of_tables_cleaned = clean_list(list_of_tables, list_of_offices, list_of_column_names, multiple_tables_bool, num_fixed_columns, multiple_rows_bool, num_rows, num_precinct_start_index, votes_dict, columns_vertical_bool, multiple_offices_bool, last_row_title, num_precinct_end_index, percentages_bool, num_start_rows)
    list_to_csv(list_of_tables_cleaned, county, state, election_day, total_list)

if __name__ == "__main__":
    main()