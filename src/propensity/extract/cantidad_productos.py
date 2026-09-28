'''Extrae la cantidad de productos (BI) - familia foto.'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_bi_con
from propensity.utils.utils import batch_query, find_last, guardar

KIND = 'cantidad_productos'
REZAGO = 1
PREFIJO = 'prod_'
LLAVES = ['strIdentificacion', 'strPeriodo']


def extract_cantidad_productos(
    labels: pd.DataFrame,
    engine: Engine,
    rezago: int = REZAGO,
    umbral: float = 0.3,
) -> pd.DataFrame:
    '''Conteo de productos distintos en `t - rezago`, anclado a la etiqueta.'''

    productos = batch_query(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        umbral=umbral,
    )

    return productos.rename(
        columns=lambda c: c if c in LLAVES else f'{PREFIJO}{c}'
    )


if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    productos = extract_cantidad_productos(labels=labels, engine=engine)

    guardar(df=productos, path=DATA_FEATURES, name=KIND)
