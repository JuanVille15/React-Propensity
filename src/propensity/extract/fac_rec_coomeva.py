'''Extrae facturacion y recaudo Coomeva (GCC / Oracle) - familia historia.'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_gcc_con
from propensity.utils.utils import batch_query_hist, find_last, guardar

KIND = 'fac_rec_coomeva'
REZAGO = 1
VENTANA_EXTRA = 12
# Oracle no admite mas de 1.000 elementos en un IN
BATCH_SIZE = 900


def extract_fac_rec_coomeva(
    labels: pd.DataFrame,
    engine: Engine,
    rezago: int = REZAGO,
    ventana_extra: int = VENTANA_EXTRA,
    batch_size: int = BATCH_SIZE,
) -> pd.DataFrame:
    '''Historia mensual de cuota, vencido y recaudo Coomeva por asociado.'''

    return batch_query_hist(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        ventana_extra=ventana_extra,
        batch_size=batch_size,
    )


if __name__ == '__main__':

    engine = build_gcc_con(get_db_settings('oracle'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    fac_rec_coomeva = extract_fac_rec_coomeva(labels=labels, engine=engine)

    guardar(df=fac_rec_coomeva, path=DATA_FEATURES, name=KIND)
