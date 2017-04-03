import glob
import pandas as pd


state_files = glob.glob('20*/*__ca__*.csv')
for state_file in state_files:
    print(state_file)
    state_data = pd.read_csv(state_file, na_values='', dtype={
                             'precinct': str, 'district': str})

    for x in ['candidate', 'district', 'office', 'precinct', 'county']:
        if x in state_data.columns:
            state_data = state_data.sort_values(by=x, kind='mergesort')

    state_data.to_csv(state_file, index=False)
