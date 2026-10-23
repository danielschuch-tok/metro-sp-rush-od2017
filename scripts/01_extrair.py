"""Extrai do zip da OD 2017 (Metrô SP) as colunas de viagem usadas na análise.

Entrada: dados/brutos/OD-2017.zip (baixado de URL se não existir, ~42 MB)
Saída:   dados/processados/od2017_viagens.pkl
"""
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
from dbfread import DBF

RAIZ = Path(__file__).resolve().parent.parent
URL = 'https://transparencia.metrosp.com.br/sites/default/files/OD-2017.zip'
ZIP = RAIZ / 'dados/brutos/OD-2017.zip'
DBF_NO_ZIP = 'OD-2017/Banco de Dados-OD2017/OD_2017_v1.dbf'
SAIDA = RAIZ / 'dados/processados/od2017_viagens.pkl'

COLS = ['ZONA', 'ID_PESS', 'N_VIAG', 'FE_VIA', 'DIA_SEM',
        'MODO1', 'MODO2', 'MODO3', 'MODO4', 'MODOPRIN',
        'H_SAIDA', 'MIN_SAIDA', 'H_CHEG', 'MIN_CHEG', 'DURACAO', 'MOTIVO_D']

dbf = RAIZ / 'dados/brutos/OD_2017_v1.dbf'
if not dbf.exists() and not ZIP.exists():
    print('baixando', URL)
    urllib.request.urlretrieve(URL, ZIP)
if not dbf.exists():
    with zipfile.ZipFile(ZIP) as z:
        dbf.write_bytes(z.read(DBF_NO_ZIP))

df = pd.DataFrame([{k: r.get(k) for k in COLS} for r in DBF(dbf, load=False)])
df.to_pickle(SAIDA)
print(df.shape, '->', SAIDA)
