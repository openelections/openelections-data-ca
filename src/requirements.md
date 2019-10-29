# Parser for California 
## Modoc, Plumas, Sonoma and similar formats 
This parser has been tested successfully on the Modoc, Plumas, Sonoma (all 2018) Statement of Votes General Election pdf files. It can be used for pdf files that are formatted such that: 
- precinct names are in the first column 
- each column represents a number of votes (along with their candidate name or category as the header of the column) 
- this includes columns with vertical text for headers

## Requirements 
1. Table package (included in folder)
2. Utilities package (included in folder)
3. tabular package (https://pypi.org/project/tabula-py/)
4. pandas library (https://pypi.org/project/pandas/)
5. math library (https://docs.python.org/3/library/math.html)
6. csv library (https://docs.python.org/3/library/csv.html)

Install either custom package by typing  `pip install .` in your terminal (make sure you are in the directory with both folders and the setup.py file).

## Author
Tiffany Xiao

### Currently Working for ...
Below is a list of the files that this parser works for currently: 
-Modoc 2018 General 
-Plumas 2018 General
-Sonoma 2018 General