'''Extrae la demografica (BI) - familia foto.'''
import pandas as pd
from sqlalchemy import Engine

from propensity.utils.utils import batch_query, find_last, guardar
from propensity.db import build_bi_con
from propensity.config import DATA_FEATURES, DATA_LABELS, get_db_settings


KIND = 'Demo'
REZAGO = 1
PREFIJO = 'demo_'
LLAVES = ['strIdentificacion', 'strPeriodo']

def extract_demografica(
    labels: pd.DataFrame, 
    engine: Engine, 
    rezago: int = REZAGO, 
    umbral: float = 0.95, 
) -> pd.DataFrame:
    
    demografica = batch_query(
        kind=KIND, 
        labels=labels, 
        engine=engine, 
        rezago=rezago, 
        umbral=umbral, 
    )
    
    # --- Se genera un prefijo a todo menos las llaves --- #
    
    return demografica.rename(
        columns=lambda c: c if c in LLAVES else f'{PREFIJO}{c}'
    )
    
if __name__ == '__main__':

    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(DATA_LABELS))

    demografica = extract_demografica(labels=labels, engine=engine)

    guardar(df=demografica, path=DATA_FEATURES, name='demografica')
