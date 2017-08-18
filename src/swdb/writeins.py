import io
import requests
import PyPDF2


def alameda_p14(candidate_norm):
    writeins_url = 'https://www.acgov.org/rov/elections/20140603/documents/OfficialWrite-in-Tally.pdf'
    writeins_req = requests.get(writeins_url)
    writeins_req.raise_for_status()
    writeins_pdf = PyPDF2.PdfFileReader(io.BytesIO(writeins_req.content))
    cands = writeins_pdf.getPage(0).extractText().split('\n')[7::3]
    cands = [c.strip(' ') for c in cands]
    cand_split = [(c.split(' ' * 7)[0],
                   int(c.split(' ' * 7)[1].strip())) for c in cands]
    return [{'candidate': candidate_norm[c],
             'votes': v,
             'county': 'Alameda',
             'office': 'Governor',
             'party': 'DEM',
             'precinct': 'Write-In'} for
            c, v in cand_split if v != 0]

WRITEINS = {'P14': {'Alameda': alameda_p14}}
