'''Extrae la Vista 360 (BI) - familia foto: una fila por (asociado, periodo).'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_bi_con
from propensity.utils.utils import batch_query, find_last, guardar

KIND = 'v_360'
REZAGO = 1
PREFIJO = 'v360_'
LLAVES = ['strIdentificacion', 'strPeriodo']


def extract_v_360(
    labels: pd.DataFrame,
    engine: Engine,
    rezago: int = REZAGO,
    umbral: float = 0.95,
) -> pd.DataFrame:
    '''Vista 360 del asociado en `t - rezago`, anclada al periodo de la etiqueta.'''

    v_360 = batch_query(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        umbral=umbral,
    )

    # --- Se genera un prefijo a todo menos las llaves --- #

    return v_360.rename(
        columns=lambda c: c if c in LLAVES else f'{PREFIJO}{c}'
    )


if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    v_360 = extract_v_360(labels=labels, engine=engine)

    guardar(df=v_360, path=DATA_FEATURES, name=KIND)
