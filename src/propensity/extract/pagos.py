'''Extrae recaudo por empresa del grupo (BI) - familia historia.

Una misma consulta sirve para varias empresas: el marcador {empresa} del
.sql se reemplaza por la que se pida, y cada una se persiste aparte.
'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_bi_con
from propensity.utils.utils import batch_query_hist, find_last, guardar

KIND = 'pagos_bi'
REZAGO = 1
VENTANA_EXTRA = 12
EMPRESAS = ['BANCOOMEVA', 'MEDICINA PREPAGADA']


def extract_pagos(
    labels: pd.DataFrame,
    engine: Engine,
    empresa: str,
    rezago: int = REZAGO,
    ventana_extra: int = VENTANA_EXTRA,
) -> pd.DataFrame:
    '''Historia mensual de recaudo del asociado en una empresa del grupo.

    Raises:
        ValueError: Si `empresa` no esta en EMPRESAS.
    '''
    if empresa not in EMPRESAS:
        raise ValueError(f'Empresa no valida: {empresa} - posibles: {EMPRESAS}')

    return batch_query_hist(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        ventana_extra=ventana_extra,
        sustituciones={'empresa': empresa},
    )


if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    for empresa in EMPRESAS:
        pagos = extract_pagos(labels=labels, engine=engine, empresa=empresa)
        nombre = f'pagos_{empresa.lower().replace(" ", "_")}'
        guardar(df=pagos, path=DATA_FEATURES, name=nombre)
