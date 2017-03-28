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
