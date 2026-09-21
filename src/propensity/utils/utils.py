'''Funciones comunes para modulos'''
import datetime
import pandas as pd

from sqlalchemy import Engine,text
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
from typing import Literal
from dateutil.relativedelta import relativedelta
from propensity.utils.exceptions import FeatureQueryError, DuplicateFeatureError, FeatureNoMatchError




def find_last(
    dir:str|Path, 
    ext:str = '.parquet', 
) -> Path:
    '''Retorna la ruta del archivo más reciente de un directorio.

    El criterio de "más reciente" es la fecha de última modificación
    (`st_mtime`), no el orden alfabético del nombre. Ojo: copiar,
    sincronizar o restaurar archivos reescribe esa fecha, así que si
    `data/` se mueve entre máquinas el orden puede dejar de reflejar
    el orden real de generación.

    Args:
        dir: Directorio donde buscar. Acepta `str` o `Path`.
        ext: Extensión por la que filtrar, con punto incluido.
            Por defecto '.parquet'.

    Returns:
        Ruta al archivo con la fecha de modificación más reciente
        entre los que coinciden con `ext`.

    Raises:
        NotADirectoryError: Si `dir` no existe o no es un directorio.
        FileNotFoundError: Si el directorio no contiene ningún archivo
            con la extensión `ext`.
    '''
    PATTERN = f'*{ext}'
    DIR = Path(dir)
    
    # --- Validar que directory sea una carpeta --- #
    if not DIR.is_dir():
        raise NotADirectoryError(f'Parametro dir: {dir} - debe ser un directorio...')
    
    # --- Se listan archivos segun ext --- #
    files = DIR.glob(PATTERN)
    
    # --- Ordenamos la lista de archivos --- #
    sorted_files = (
            sorted(
                files, 
                key=lambda p: p.stat().st_mtime, 
                reverse=True, 
            )
        )
    
    if not sorted_files:
        raise FileNotFoundError(f'No hay archivos {ext} en {DIR}')

    return sorted_files[0]

def batch_query(
    kind:Literal['Demo', 
                 'v_360'],
    labels:pd.DataFrame,  
    engine:Engine,
    rezago:int=1,
    batch_size:int=2_000,
    umbral:float=0.5, 
) -> pd.DataFrame:
    
    # --- Se lanza error si rezago < 1 --- #
    
    if rezago < 1:
        raise ValueError(f'Se espera rezago >= 1 - se obtuvo {rezago}')
    
    ROOT = Path(__file__).parents[3].resolve()
    QUERY_PATH = ROOT / "sql" / f"{kind}.sql"
    
    # --- leemos la consulta --- #
    if not QUERY_PATH.exists():
        raise FileNotFoundError(f'Query Not Found: {kind} - {QUERY_PATH}')
     
    query = QUERY_PATH.read_text(encoding='utf-8')
    
    # --- Se itera por periodo labels --- #
    
    PERIODOS = (
        sorted(
            labels['strPeriodo'].unique().tolist(), 
            key= lambda p: datetime.datetime.strptime(str(p), '%Y%m'), 
            reverse=False, 
        )   
    )
     
    # ===============
    # BUCLE CONSULTA
    # ===============
    results = []
    # --- ciclo de iteracion --- # 
    for p in PERIODOS:
        
        ## --- Se encuentra las cedulas del periodo --- ##
        
        CEDULAS_PERIODO = (
            labels[labels['strPeriodo'] == p]
            ['strIdentificacion'].to_list()
        )
        
        LOTES_CEDULAS = [
            CEDULAS_PERIODO[
            i:i+batch_size
            ] for i in range(0, len(CEDULAS_PERIODO), batch_size)
        ]
        
        ## --- Se genera el periodo rezagado: Parametros de la consulta --- #
        
        p_lag = (
            datetime.datetime.strptime(str(p), '%Y%m') - relativedelta(months=rezago)
        ).strftime('%Y-%m-%d')
        
        PARAMETROS = {
            'periodo_foto':p_lag
        }
        
        ## --- Se itera por bloque de cedulas --- ##
        print(f'Consultado periodo {p}...')
        for l in LOTES_CEDULAS:
            
            CEDULAS_LOTE = ','.join(
                f"'{c}'" for c in l
            )
            
            query_lote = (
                text(
                    query.replace(
                        '{IDS}', 
                        CEDULAS_LOTE, 
                    )
                )
            )
            try:
                with engine.connect() as conn:
                    temp_query = (
                        pd.read_sql(
                            sql=query_lote, 
                            con=conn,
                            params=PARAMETROS,  
                            dtype={
                               'Documento':int,
                            }
                        )
                        .rename(
                            columns={
                                'Documento': 'strIdentificacion', 
                            }
                        )
                        .assign(
                            strPeriodo = p, 
                        )
                    )
                    results.append(temp_query) 
            except SQLAlchemyError as e:
                raise  FeatureQueryError(f'Error consultado: {kind}:{p} - {e}') from e
    
    # --- Se crea el dataframe final --- #
    
    feature = (
        pd.concat(
            results, 
            axis=0, 
            ignore_index=True, 
        )
    )
    
    # --- Validar unicidad --- #
    
    VALORES_REPETIDOS = (
        feature
        .duplicated(
            subset=['strIdentificacion','strPeriodo'], 
            keep='first', 
        )
        .sum()
    )
    
    if VALORES_REPETIDOS > 0:
        raise DuplicateFeatureError(f'Se encontraron: {VALORES_REPETIDOS} repetidos en - {kind}')
    
    # --- Validar cobertura --- #
    COBERTURA = _validar_cobertura(
        labels=labels, 
        feature=feature, 
    )
    
    CRITICOS = (
        COBERTURA[
            COBERTURA['cobertura'] < umbral
        ]
    )
    
    if CRITICOS.shape[0] > 0:
        raise FeatureNoMatchError(f'Se en encuentran periodos sin cobertura: {CRITICOS.to_string()}')

    return feature

def _validar_cobertura(
    labels:pd.DataFrame, 
    feature:pd.DataFrame,  
) -> pd.DataFrame:
    
    # --- Se genera el cruce --- #
    
    COBERTURA = (
        labels
        .merge(
            right=feature[['strPeriodo','strIdentificacion']], 
            how='left', 
            on=['strPeriodo','strIdentificacion'], 
            indicator=True, 
        )
        .assign(
            cruza = lambda df:
                (df['_merge'] == 'both')
        )
        .groupby(
            'strPeriodo'
        )
        ['cruza']
        .mean()
        .rename('cobertura')
        .reset_index()
    )
    
    return COBERTURA