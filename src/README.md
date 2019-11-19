# openelections
This parser was created as part of a capstone project for a Smith College senior capstone course. Below is a description of the parser, including explanations of the choices made and the various inputs that will be asked for.

# Author 
Tiffany Xiao

# About the Parser
## General Information
This parser has been tested successfully on the Modoc, Plumas, Sonoma (all 2018) Statement of Votes General Election pdf files. It can be used for pdf files that are formatted such that: 
- precinct names are in the first column 
- each column represents a number of votes (along with their candidate name or category as the header of the column) 
- there is an area that indicates the office(s) included in the page. 
- this includes columns with vertical text for headers

## Description of the Code
The code first begins by splitting the pdf into three parts (table area, office names area and column headers area). Then, it cleans each part. First, it cleans the office names, next the column names (concatenating names if necessary) and finally the table information (dealing with the numbers and any edge cases [like with percentages]). It uses a couple of functions from the utilities package to clean the table information (checking if the office is an "accepted" office [if its an office we're interested in including in the csv], cleaning strings, etc.). Also, it uses the table package to create the final csv. 

## Terms & Definitions
Table (pdf use definition)- a table when describing the pdf is the entire table containing all the voting information of the precincts for an office. Some pdfs have tables that span multiple pages.

## Limitations
1) If there are multiple offices per table (table as in the pdf use definition), the current way of detecting a new office (in order to split it and isolate it from the dataframe) is to detect if there is a column of NAN values only before the office begins. If the pdf does not have this empty column, the splitting algorithm will need to be adjusted. 
2) Any non-table data must be deleted from the pdf before running the program. For example, the Sonoma 2018 elections results comes with a disclaimer on the first page. This page was removed before running the program. 

## Detailed explanations of inputs
Each section and question corresponds to the program's prompts. 
### Questions about PDF
`Name of County: ` 
This is asking for the name of the county. This field will be used when generating the name of the csv file. I chose to have this manually inputted because not all counties include the county's name in the pdf file for their votes.

`State initials: ("ca" for California): ` 
This is asking for the state initials of the state of the county. This field will be used when generating the name of the csv file. I chose to have this manually inputted because not all counties include the state's name in the pdf file for their votes.

`election_day = int(input("Election day (YYYYMMDD format): "))`
This is asking for the election date for the pdf. This field will be used when generating the name of the csv file. I chose to have this manually inputted because not all counties include the election date in the pdf file for their votes, and if they do, the work to manually input the date is much less than the work to capture the area where the election date is on each page.

### Questions about PDF Format
`Are the columns vertical text? (\"y\" for yes or \"n\" for no): `
This is asking if the column names are not horizontal, rather they are vertically positioned. See Sonoma 2018 for an example of vertical text columns. By vertical text, it means as if normal text was rotated, not that the letters are flowing in a vertical fashion downward. Saying yes to this will run code that rotates the pdf and then reads the column names. 

`Are there multiple pages for a single table (\"y\" for yes or \"n\" for no):`
See definition of Table (for pdf use). If yes, then code to merge tables according to office names will run.

`Are there multiple rows for a precinct's results (\"y\" for yes or \"n\" for no):`
If yes, then code to detect the end of information relative to a precinct will run. Responding with no will skip the following question.

`How many rows for each precinct?` 
This will only be asked if the user responds to the previous question with "y". This number should be the number of consecutive rows pertaining to a single precinct.

`Are there multiple offices per table (\"y\" for yes or \"n\" for no): `
This will run code that will split the dataframe according to the offices. It must be similarly formatted to the Sonoma pdf, where there is an area that indicates all offices included in the pdf and office results are separated by an empty colum (see limitations).

### Questions about PDF Details
`What is the first non-precinct row on the PDF called (example: Total)? ` 
This is the first row that will flag to the column that we have reached the end of the data for precincts. Please type this exactly as it appears in the table (with capitalization, spaces, etc).

`How many columns come before the first candidate's name? (not including the first column [the one without a column name]): `
This is the number of columns that would register in the column area of the table. This means not including the first column of the table (usually the column with the precinct names or precinct related information).

`What index does the precinct name START at in a cell?` 
This is used to clean the row as the program reads it in. Please indicate what index the name of the precinct begins (indexes start at 0).

`What index does the precinct name END at in a cell? (Put -1 if the entire string is the precinct name)` 
This is used to clean the row as the program reads it in. Please indicate what index the name of the precinct ends (indexes start at 0, enter -1 if the entire cell represents the row).

`Are there cells with percentages following every number of votes (\"y\" for yes or \"n\" for no)?`
The format of the PDFs require the pdf to be read in streaming mode, but that means the columns are differentiated using spacing. This can cause problems when two columns are close together, which is the case for percentage values (next to numeric values) in the Modoc and Plumas pdf files. If there are percentages, code to skip the percentages will run. 

`Is there a row representing total votes for the precinct for the candidate (\"y\" for yes or \"n\" for no)? (if not, then the script will use all other values to calculate the total):`
This is asking if there are any row that represents the total votes for that office's election in the particular precinct. Modoc has a "Total" row and Plumas only has rows that represent the total votes (modoc also has absentee and other voting types).

`How many non-precinct related rows (rows such as \"Jurisdiction Wide\" for Modoc county files at the top of each table) are at the beginning of each table?`
The code is built to start with the precinct data and terminate as soon as it finds any data unrelated to a precinct. This is asking for the number of non-precinct specific data that may be at the beginning of a table. 

`Input a list of all the available vote types:` 
This should be a string, with each entry separated by commas. Every two items in this string represents a column, with the first item being the actual name (or a keyword) of the row that indicates the start of the column's information (i.e. "Total" or "Mail") and the second item being the actual column's name in the csv (i.e. "total", "early_voting"). These items must be typed exactly as they appear, with commas separating items. 
The possible columns are: 
`precinct', 'office', 'district', 'party', 'candidate', 'votes', 'early_voting', 'election_day', 'provisional', 'absentee', 'federal','county'
An example entry would be: Total,total,Mail,absentee

### Areas for each region 
As explained above, the code works by dividing each page of a pdf into three separate sections. The areas can be extract using the Tabula application:
1) Select the region that contains the section you want (on every page). Make sure the preview looks correct (and that you have the streaming option selected)!
2) Download the script. 
3) Copy and paste the area coordinates from the script as inputs for this program.

## Example inputs for certain PDF files 
Below are what you would enter for some of the PDF files that have worked: 

### Modoc
modoc

ca

20181126

Modoc 2018 General Full.pdf (varies depending on what you named the general pdf)

n

y

y

6

n

Total

3

0

-1

y

y

1

Absentee,absentee,Provisional,provisional,Total,total

1

172.935,0.0,777.958,611.003

103.658,0.383,133.493,612.383

124.313,1.913,174.803,612.383

### Plumas
plumas

ca

20181126

Plumas 2018 FULL.pdf (varies depending on what you named the general pdf)

n

n

n

n 

Total

2

4

-1

y

y

0

Total Votes,total

1

189.338,-0.383,563.423,609.323

119.723,2.678,150.323,610.853

146.498,1.148,190.103,610.088

### Sonoma
sonoma

ca

20181126

Sonoma FULL.pdf (varies depending on what you named the general pdf)

y

y

y

2

y

Precinct Totals

0

0

4 

n

n

0

PCT,election_day,Mail,mail

-1

186.519,-1.824,790.31,611.088

47.107,115.591,69.276,611.208

8.709,607.576,606.039,724.378
