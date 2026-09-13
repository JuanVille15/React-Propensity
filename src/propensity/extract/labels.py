'''Extrae las etiquetas: reactivado -- No reactivado
    de un periodo especifico'''
    
import pandas as pd
import datetime

from pathlib import Path
from sqlalchemy import text
from dateutil.relativedelta import relativedelta
from propensity.config import get_db_settings
from propensity.db import build_bi_con
from propensity.utils.exceptions import LabelQueryError

def extract_labels(
    con_config:dict[str,str], 
    periodo:int, 
    rezago:int
) -> pd.DataFrame:
    
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
        periodo_format - relativedelta(months=i) for i in range(rezago + 1)
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
    
    QUERY_PATH = Path(__file__).parents[3].resolve() / "sql" / "labels.sql"
    
    if not QUERY_PATH.exists():
        raise FileNotFoundError(f'No se encuentra la consulta: {QUERY_PATH.name}')
    
    labels_query = text(QUERY_PATH.read_text(encoding='utf-8'))
    
    # --- se genera la consulta iterada por parametros --- #
    
    results = []
    engine = (
    build_bi_con(config=con_config)
    )
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
    
    OUT_PATH = Path(__file__).parents[3].resolve() / "data" / "raw"
    FILE_NAME =f'labes_{datetime.datetime.today().strftime('%d-%m-%Y')}.parquet'
        
    con_config = get_db_settings('sql-server')
    labels = extract_labels(con_config=con_config, periodo=202607, rezago=12)
    print(f'Exportando labels...')
    labels.to_parquet(
        f'{OUT_PATH}/{FILE_NAME}', 
        engine='pyarrow', 
        index=False
    )
    print(f'labels persistido en: {OUT_PATH}')