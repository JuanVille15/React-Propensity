'''Extrae la demografica'''
import pandas as pd
import datetime
from pathlib import Path
from sqlalchemy import Engine

from propensity.utils.utils import batch_query, find_last
from propensity.db import build_bi_con
from propensity.config import get_db_settings


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
    
    DATA_RAW = r'data\raw'
    OUT_PATH = r'data\raw\features'
    FILE_NAME = f'Demografica_{datetime.datetime.today().strftime('%d-%m-%Y')}'
    
    engine = build_bi_con(get_db_settings('sql-server'))
    labels = pd.read_parquet(find_last(Path(f'{DATA_RAW}/labels')))
    demografica = extract_demografica(labels=labels, engine=engine)
    print(f'Exportando demografica...')
    
    if not Path(OUT_PATH).exists():
        Path(OUT_PATH).mkdir(parents=True, exist_ok=True)
    demografica.to_parquet(
        f'{OUT_PATH}/{FILE_NAME}.parquet', 
        index=False,
        engine='pyarrow', 
    )
    print(f'Demografica persistido en: {OUT_PATH}')
