'''Extrae las etiquetas: reactivado -- No reactivado.

Es la espina del panel: define la poblacion en riesgo y los periodos
sobre los que despues se extraen todas las features.
'''
import pandas as pd
import datetime

from sqlalchemy import Engine, text
from dateutil.relativedelta import relativedelta

from propensity.config import DATA_RAW, SQL_DIR, get_db_settings
from propensity.db import build_bi_con
from propensity.utils.exceptions import LabelQueryError
from propensity.utils.utils import guardar

KIND = 'labels'
PERIODO_FINAL = 202607
N_PERIODOS = 13


def extract_labels(
    engine: Engine,
    periodo: int = PERIODO_FINAL,
    n_periodos: int = N_PERIODOS,
) -> pd.DataFrame:
    '''Arma el panel de cohortes apiladas, un periodo a la vez.

    Para cada periodo `t` trae los asociados inactivos al cierre de `t-1`
    y marca si reactivaron durante `t`.

    Args:
        engine: Engine de la bodega (BI).
        periodo: Ultimo periodo etiquetado, en YYYYMM.
        n_periodos: Cuantos periodos hacia atras etiquetar, incluyendo
            `periodo`. No confundir con el rezago temporal de las
            features: aca es un conteo de meses, no un desfase.

    Raises:
        FileNotFoundError: Si no existe sql/labels.sql.
        LabelQueryError: Si la bodega rechaza alguna consulta.
    '''
    # --- Se le da formato al periodo --- #

    periodo_format = (
        datetime.datetime.strptime(
            str(periodo),
            "%Y%m"
        )
    )

    # --- Se crean los periodos de consulta --- #

    periodos_consulta = sorted(
        [
        periodo_format - relativedelta(months=i) for i in range(n_periodos)
    ],
        reverse=False,
    )

    # --- Se genera la lista de parametros
    lista_parametros = [
            [
                (p - relativedelta(months=1)).strftime("%Y-%m-%d"),
                p.strftime("%Y-%m-%d")
            ] for p in periodos_consulta
    ]

    # --- Nos traemos la consulta --- #

    QUERY_PATH = SQL_DIR / f'{KIND}.sql'

    if not QUERY_PATH.exists():
        raise FileNotFoundError(f'No se encuentra la consulta: {QUERY_PATH.name}')

    labels_query = text(QUERY_PATH.read_text(encoding='utf-8'))

    # --- se genera la consulta iterada por parametros --- #

    results = []

    for params in lista_parametros:
        PARAMETROS = {
            'periodo_anterior':params[0],
            'periodo_actual': params[1]
        }
        try:
            p = params[1]
            print(f'Consultado etiquetas - {p}...')
            with engine.connect() as conn:
                labels_t = pd.read_sql(
                    sql=labels_query,
                    con=conn,
                    params=PARAMETROS,
                    dtype={
                        'strPeriodo':int,
                        'strIdentificacion': int,
                        'strEstadoInicial':'Int64',
                        'IndicadorReactivado': int
                    }
                )

            TOTAL_INACTIVOS = len(labels_t)
            TOTAL_REACTIVADOS = len(labels_t[labels_t['IndicadorReactivado']==1])
            print(f'Inactivos - {p}: {TOTAL_INACTIVOS}')
            print(f'Reactivados - {p}: {TOTAL_REACTIVADOS}')
            results.append(labels_t)
        except Exception as e:
            raise LabelQueryError(f'Error extrayendo labels: {e}') from e

    labels = (
            pd.concat(
                results,
                axis=0,
                ignore_index=True,
            )
        )

    return labels


if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))

    labels = extract_labels(engine=engine)

    guardar(df=labels, path=DATA_RAW, name=KIND)
