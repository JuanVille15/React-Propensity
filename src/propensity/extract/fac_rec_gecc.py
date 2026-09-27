'''Extrae facturacion y recaudo GECC (BI) - familia historia.

No lleva prefijo ni anclaje: cada fila conserva su propio periodo. El
anclaje a `t-1` lo impone la ventana movil que se construya en features/.
'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_bi_con
from propensity.utils.utils import batch_query_hist, find_last, guardar

KIND = 'fac_rec_gecc'
REZAGO = 1
VENTANA_EXTRA = 12


def extract_fac_rec_gecc(
    labels: pd.DataFrame,
    engine: Engine,
    rezago: int = REZAGO,
    ventana_extra: int = VENTANA_EXTRA,
) -> pd.DataFrame:
    '''Historia mensual de facturacion y recaudo GECC por asociado.'''

    return batch_query_hist(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        ventana_extra=ventana_extra,
    )


if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    fac_rec_gecc = extract_fac_rec_gecc(labels=labels, engine=engine)

    guardar(df=fac_rec_gecc, path=DATA_FEATURES, name=KIND)
