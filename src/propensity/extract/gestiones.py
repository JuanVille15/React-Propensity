'''Extrae el historico de gestiones de cobranza (GCC / Oracle).

Familia historia, y ademas de EVENTOS: un asociado puede tener varias
gestiones en el mismo mes. Antes de unirla al panel hay que agregarla a
una fila por (asociado, periodo) en features/.

Un periodo sin gestiones es posible, asi que no se falla cuando un mes
vuelve vacio.
'''
import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings
from propensity.db import build_gcc_con
from propensity.utils.utils import batch_query_hist, find_last, guardar

KIND = 'gestiones'
REZAGO = 1
VENTANA_EXTRA = 12
BATCH_SIZE = 900


def extract_gestiones(
    labels: pd.DataFrame,
    engine: Engine,
    rezago: int = REZAGO,
    ventana_extra: int = VENTANA_EXTRA,
    batch_size: int = BATCH_SIZE,
) -> pd.DataFrame:
    '''Gestiones de cobranza por asociado, a nivel de evento.'''

    return batch_query_hist(
        kind=KIND,
        labels=labels,
        engine=engine,
        rezago=rezago,
        ventana_extra=ventana_extra,
        batch_size=batch_size,
        fallar_si_vacio=False,
    )


if __name__ == '__main__':

    engine = build_gcc_con(get_db_settings('oracle'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    gestiones = extract_gestiones(labels=labels, engine=engine)

    guardar(df=gestiones, path=DATA_FEATURES, name=KIND)
