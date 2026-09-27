'''Funciones comunes para modulos'''
import datetime
import pandas as pd

from sqlalchemy import Engine,text
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
from dateutil.relativedelta import relativedelta
from propensity.config import SQL_DIR
from propensity.utils.exceptions import (
    FeatureQueryError, DuplicateFeatureError,
    FeatureNoMatchError, SaveFileError,
)

LLAVES = ['strIdentificacion', 'strPeriodo']

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

def _leer_query(
    kind:str,
    sustituciones:dict[str,str]|None = None,
) -> str:
    '''Lee el .sql de la fuente y aplica sustituciones de texto.

    Args:
        kind: Nombre del archivo en sql/, sin extension.
        sustituciones: Marcadores a reemplazar en el texto de la consulta,
            sin las llaves. Ej: {'empresa': 'BANCOOMEVA'} reemplaza {empresa}.
            El marcador {IDS} NO se toca aca: lo maneja `_consultar_lotes`.

    Raises:
        FileNotFoundError: Si no existe el .sql de esa fuente.
    '''
    QUERY_PATH = SQL_DIR / f'{kind}.sql'

    if not QUERY_PATH.exists():
        raise FileNotFoundError(f'Query Not Found: {kind} - {QUERY_PATH}')

    query = QUERY_PATH.read_text(encoding='utf-8')

    for marcador, valor in (sustituciones or {}).items():
        query = query.replace(f'{{{marcador}}}', valor)

    return query

def _consultar_lotes(
    query:str,
    engine:Engine,
    params:dict,
    cedulas:list,
    batch_size:int,
    kind:str,
) -> list[pd.DataFrame]:
    '''Ejecuta la consulta de UN periodo, en lotes de cedulas.

    Es el nucleo compartido por `batch_query` (fotos) y `batch_query_hist`
    (historia). No valida nada ni ancla periodos: solo consulta y devuelve
    los pedazos crudos.

    Args:
        query: Texto del .sql, con el marcador {IDS} sin reemplazar.
        engine: Engine ya construido. Se reusa su pool en cada lote.
        params: Parametros nombrados de la consulta (ej: periodo_foto).
        cedulas: Identificaciones a consultar en este periodo.
        batch_size: Maximo de cedulas por consulta. Oracle no admite mas
            de 1.000 elementos en un IN: usar <= 900 para fuentes de GCC.
        kind: Nombre de la fuente, solo para el mensaje de error.

    Raises:
        FeatureQueryError: Si la base rechaza la consulta.
    '''
    LOTES = [
        cedulas[i:i+batch_size] for i in range(0, len(cedulas), batch_size)
    ]

    resultados = []

    for lote in LOTES:

        CEDULAS_LOTE = ','.join(f"'{c}'" for c in lote)
        query_lote = text(query.replace('{IDS}', CEDULAS_LOTE))

        try:
            with engine.connect() as conn:
                resultados.append(
                    pd.read_sql(
                        sql=query_lote,
                        con=conn,
                        params=params,
                    )
                )
        except SQLAlchemyError as e:
            raise FeatureQueryError(
                f'Error consultando {kind} - params={params}: {e}'
            ) from e

    return resultados

def _periodo_rezagado(
    periodo:int|str,
    rezago:int,
) -> str:
    '''Convierte un periodo YYYYMM en la fecha del periodo rezagado.'''
    return (
        datetime.datetime.strptime(str(periodo), '%Y%m')
        - relativedelta(months=rezago)
    ).strftime('%Y-%m-%d')

def batch_query(
    kind:str,
    labels:pd.DataFrame,
    engine:Engine,
    rezago:int=1,
    batch_size:int=2_000,
    umbral:float=0.5,
    sustituciones:dict[str,str]|None = None,
) -> pd.DataFrame:
    '''Extrae una fuente de FOTO: una fila por (asociado, periodo).

    Para cada periodo `t` de labels consulta la fuente en `t - rezago` y
    ancla el resultado al periodo de la etiqueta, de modo que la fila
    quede alineada con el target sin mirar el futuro.

    Contrato del .sql: debe devolver la columna `strIdentificacion` y
    recibir el periodo como el parametro nombrado `:periodo_foto` (en
    formato YYYY-MM-DD). La lista de cedulas va en el marcador {IDS}.
    El periodo lo asigna esta funcion: lo que devuelva el .sql se pisa.

    Args:
        kind: Nombre del .sql en sql/, sin extension.
        labels: Panel de etiquetas. Define poblacion y periodos.
        engine: Engine de la base donde vive la fuente.
        rezago: Meses de desfase del anclaje temporal. Debe ser >= 1:
            con 0 la feature miraria el mismo mes del evento (fuga).
        batch_size: Cedulas por consulta (<= 900 si la fuente es Oracle).
        umbral: Cobertura minima por periodo antes de fallar.
        sustituciones: Marcadores extra del .sql (ej: {'empresa': '...'}).

    Raises:
        ValueError: Si `rezago` < 1.
        DuplicateFeatureError: Si hay mas de una fila por (cedula, periodo).
        FeatureNoMatchError: Si algun periodo queda debajo del umbral.
    '''
    # --- Se lanza error si rezago < 1 --- #

    if rezago < 1:
        raise ValueError(f'Se espera rezago >= 1 - se obtuvo {rezago}')

    if labels.empty:
        raise ValueError('labels esta vacio: no hay poblacion que consultar')

    query = _leer_query(kind=kind, sustituciones=sustituciones)

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

        ## --- Se genera el periodo rezagado: Parametros de la consulta --- #

        PARAMETROS = {
            'periodo_foto': _periodo_rezagado(periodo=p, rezago=rezago)
        }

        print(f'Consultando {kind} - periodo {p} (foto {PARAMETROS["periodo_foto"]})...')

        ## --- Se ancla cada lote al periodo de la etiqueta --- ##

        results.extend(
            lote.assign(strPeriodo=p) for lote in _consultar_lotes(
                query=query,
                engine=engine,
                params=PARAMETROS,
                cedulas=CEDULAS_PERIODO,
                batch_size=batch_size,
                kind=kind,
            )
        )

    # --- Se crea el dataframe final --- #

    feature = (
        pd.concat(
            results,
            axis=0,
            ignore_index=True,
        )
    )

    _validar_contrato(df=feature, kind=kind)

    feature = feature.astype({'strIdentificacion':'int64'})

    # --- Validar unicidad --- #

    VALORES_REPETIDOS = (
        feature
        .duplicated(
            subset=LLAVES,
            keep='first',
        )
        .sum()
    )

    if VALORES_REPETIDOS > 0:
        raise DuplicateFeatureError(
            f'Se encontraron: {VALORES_REPETIDOS} filas con llave duplicada en - {kind}'
        )

    # --- Validar cobertura --- #
    COBERTURA = _validar_cobertura(
        labels=labels,
        feature=feature,
    )

    print(f'Cobertura {kind}:\n{COBERTURA.to_string(index=False)}')

    CRITICOS = (
        COBERTURA[
            COBERTURA['cobertura'] < umbral
        ]
    )

    if CRITICOS.shape[0] > 0:
        raise FeatureNoMatchError(f'Se en encuentran periodos sin cobertura: {CRITICOS.to_string()}')

    return feature

def batch_query_hist(
    kind:str,
    labels:pd.DataFrame,
    engine:Engine,
    rezago:int=1,
    ventana_extra:int=12,
    batch_size:int=2_000,
    sustituciones:dict[str,str]|None = None,
    fallar_si_vacio:bool=True,
) -> pd.DataFrame:
    '''Extrae una fuente HISTORICA: varias filas por asociado.

    A diferencia de `batch_query`, aqui cada fila conserva SU propio
    periodo: son los insumos crudos con los que `features/` construira
    despues las ventanas moviles. Por eso no se ancla ni se valida
    unicidad por (cedula, periodo de etiqueta).

    Periodos consultados: el periodo foto de cada etiqueta (`t - rezago`)
    mas `ventana_extra` meses anteriores al mas antiguo de ellos, para que
    la ventana movil mas larga nazca completa en el primer periodo
    etiquetado. El ultimo mes consultado es `t_max - rezago`: la fuente
    nunca ve el mes en que se evalua la reactivacion.

    Contrato del .sql: debe devolver `strIdentificacion` y `strPeriodo`
    (el periodo real del dato, en YYYYMM) y recibir `:periodo_foto` en
    formato YYYY-MM-DD.

    Args:
        kind: Nombre del .sql en sql/, sin extension.
        labels: Panel de etiquetas. Define poblacion y rango de periodos.
        engine: Engine de la base donde vive la fuente.
        rezago: Meses de desfase del corte temporal. Debe ser >= 1.
        ventana_extra: Meses de historia adicional antes de la foto mas
            antigua. Con rezago=1 la foto del primer grupo es `t-1`; con 12
            meses extra la historia llega hasta `t-13`: cubre una ventana
            movil de 12 meses (`t-12` a `t-1`) mas un punto de referencia
            (`t-13`) para calcular variaciones.
        batch_size: Cedulas por consulta (<= 900 si la fuente es Oracle).
        sustituciones: Marcadores extra del .sql (ej: {'empresa': '...'}).
        fallar_si_vacio: Si un periodo no devuelve ninguna fila, lanza
            error. Señal tipica de una particion sin cargar.

    Raises:
        ValueError: Si `rezago` < 1 o `ventana_extra` < 0.
        FeatureNoMatchError: Si algun periodo vuelve vacio.
    '''
    if rezago < 1:
        raise ValueError(f'Se espera rezago >= 1 - se obtuvo {rezago}')

    if ventana_extra < 0:
        raise ValueError(f'Se espera ventana_extra >= 0 - se obtuvo {ventana_extra}')

    if labels.empty:
        raise ValueError('labels esta vacio: no hay poblacion que consultar')

    query = _leer_query(kind=kind, sustituciones=sustituciones)

    # --- Periodos foto: uno por cada periodo etiquetado --- #

    PERIODOS_FOTO = sorted(
        {
            _periodo_rezagado(periodo=p, rezago=rezago)
            for p in labels['strPeriodo'].unique().tolist()
        }
    )

    # --- Historia adicional hacia atras del mas antiguo --- #

    MAS_ANTIGUO = datetime.datetime.strptime(PERIODOS_FOTO[0], '%Y-%m-%d')

    PERIODOS_EXTRA = [
        (MAS_ANTIGUO - relativedelta(months=i)).strftime('%Y-%m-%d')
        for i in range(1, ventana_extra + 1)
    ]

    PERIODOS = sorted(set(PERIODOS_FOTO + PERIODOS_EXTRA))

    # --- Toda la poblacion de labels, en todos los periodos --- #

    CEDULAS = labels['strIdentificacion'].unique().tolist()

    print(
        f'{kind}: {len(PERIODOS)} periodos ({PERIODOS[0]} a {PERIODOS[-1]}) '
        f'x {len(CEDULAS)} cedulas'
    )

    # ===============
    # BUCLE CONSULTA
    # ===============

    results = []
    VACIOS = []

    for p_foto in PERIODOS:

        PARAMETROS = {'periodo_foto': p_foto}

        print(f'Consultando {kind} - foto {p_foto}...')

        lotes = _consultar_lotes(
            query=query,
            engine=engine,
            params=PARAMETROS,
            cedulas=CEDULAS,
            batch_size=batch_size,
            kind=kind,
        )

        FILAS_PERIODO = sum(len(lote) for lote in lotes)

        if FILAS_PERIODO == 0:
            VACIOS.append(p_foto)

        print(f'   filas: {FILAS_PERIODO}')

        results.extend(lotes)

    if VACIOS and fallar_si_vacio:
        raise FeatureNoMatchError(
            f'{kind}: los siguientes periodos no devolvieron filas: {VACIOS}'
        )

    historia = (
        pd.concat(
            results,
            axis=0,
            ignore_index=True,
        )
    )

    _validar_contrato(df=historia, kind=kind)

    # --- Las llaves llegan como texto en BI y como numero en Oracle: --- #
    # --- sin unificarlas, el cruce entre fuentes no encuentra nada.  --- #

    return historia.astype({'strIdentificacion':'int64', 'strPeriodo':'int64'})

def _validar_contrato(
    df:pd.DataFrame,
    kind:str,
) -> None:
    '''Verifica que la consulta devolvio las columnas llave.

    Sin esto, un alias mal escrito en el .sql no falla aca sino mucho
    despues, en el join, y con un mensaje que no menciona la causa.
    '''
    FALTANTES = [c for c in LLAVES if c not in df.columns]

    if FALTANTES:
        raise FeatureQueryError(
            f'{kind}: faltan las columnas llave {FALTANTES}. '
            f'Columnas recibidas: {list(df.columns)}'
        )

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

def guardar(
    df:pd.DataFrame, 
    path: Path, 
    name: str,
)-> None:
    
    # --- Validamos que la ruta sea valida --- #
    TODAY = datetime.datetime.today().strftime('%d-%m-%Y')    
    FILE_NAME = f'{name}_{TODAY}.parquet'
    FINAL_PATH = path / name / FILE_NAME
    
    FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    print(f'Exportando: {FILE_NAME}...')
    try:
        (
            df
            .to_parquet(
                FINAL_PATH, 
                index=False, 
                engine='pyarrow', 
            )
        )
        print(f'{FILE_NAME} persistido correctamente✅')
    except Exception as e:
        raise SaveFileError(f'Error Guardando: {FILE_NAME}-{e}') from e