import json
import pandas as pd
import requests
import tempfile

from dbfread import DBF

COUNTIES = ["Alameda",
            "Alpine",
            "Amador",
            "Butte",
            "Calaveras",
            "Colusa",
            "Contra Costa",
            "Del Norte",
            "El Dorado",
            "Fresno",
            "Glenn",
            "Humboldt",
            "Imperial",
            "Inyo",
            "Kern",
            "Kings",
            "Lake",
            "Lassen",
            "Los Angeles",
            "Madera",
            "Marin",
            "Mariposa",
            "Mendocino",
            "Merced",
            "Modoc",
            "Mono",
            "Monterey",
            "Napa",
            "Nevada",
            "Orange",
            "Placer",
            "Plumas",
            "Riverside",
            "Sacramento",
            "San Benito",
            "San Bernardino",
            "San Diego",
            "San Francisco",
            "San Joaquin",
            "San Luis Obispo",
            "San Mateo",
            "Santa Barbara",
            "Santa Clara",
            "Santa Cruz",
            "Shasta",
            "Sierra",
            "Siskiyou",
            "Solano",
            "Sonoma",
            "Stanislaus",
            "Sutter",
            "Tehama",
            "Trinity",
            "Tulare",
            "Tuolumne",
            "Ventura",
            "Yolo",
            "Yuba",
            ]

ELECTIONS = [('P14', '2014/20140603__ca__primary__%s__precinct.csv',
              json.load(open('src/swdb/candidates/P14.json'))),
             ('G14', '2014/20141104__ca__general__%s__precinct.csv',
              json.load(open('src/swdb/candidates/G14.json'))),
             ('P16', '2016/20160607__ca__primary__%s__precinct.csv',
              json.load(open('src/swdb/candidates/P16.json'))),
             ('G16', '2016/20161108__ca__general__%s__precinct.csv',
              json.load(open('src/swdb/candidates/G16.json')))
             ]


def csv_to_dataframe(csv_fname):
    return pd.read_csv(csv_fname)


def dbf_to_dataframe(dbf_fname):
    dbf_data = requests.get(dbf_fname)
    dbf_data.raise_for_status()

    f = tempfile.NamedTemporaryFile()
    f.write(dbf_data.content)
    dbf = DBF(f.name)

    return pd.DataFrame([{key: record[key] for key in dbf.field_names}
                         for record in dbf])
