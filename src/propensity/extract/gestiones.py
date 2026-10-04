'''Extrae el historico de gestiones de cobranza desde la carpeta compartida.

La bodega GCC no tiene las gestiones completas: se leen los Excel mensuales
de RUTA_GESTIONES (config/config.yml), con estructura
<ruta>/<AAAA>/GESTIONES_<AAAAMM>.xlsx.

Familia historia, y ademas de EVENTOS: un asociado puede tener varias
gestiones en el mismo mes. Antes de unirla al panel hay que agregarla a
una fila por (asociado, periodo) en features/.

El periodo de cada gestion sale de `fecha_gestion`, NO del nombre del
archivo: un archivo puede traer gestiones del mes siguiente (ej:
GESTIONES_202407 trae 6.703 gestiones del 01/08/2024). Esas filas son
copias exactas de filas del archivo de su mes, asi que cada archivo solo
aporta las gestiones cuya fecha cae en su propio periodo. Dentro de cada
archivo se eliminan las filas identicas en todas sus columnas.

Se extraen los periodos de labels (t) mas `ventana_extra` meses antes del
mas antiguo. Incluir t es seguro solo porque features/ cruza por t-1: al
construir las features de la etiqueta t se usan unicamente gestiones con
strPeriodo <= t-1.
'''
import datetime

import pandas as pd

from pathlib import Path
from dateutil.relativedelta import relativedelta
from janitor import clean_names
from propensity.config import DATA_FEATURES, DATA_LABELS
from propensity.utils.config_yml import leer_config
from propensity.utils.utils import find_last, guardar

KIND = 'gestiones'
VENTANA_EXTRA = 12
FORMATO_FECHA = '%d/%m/%Y'

# --- Columnas a conservar, con el nombre que deja clean_names(). --- #
# --- Los encabezados cambian entre archivos ('Casa Cobranza' vs  --- #
# --- 'casa_cobranza', 'Acción' vs 'accion'): clean_names los unifica. --- #

COLUMNAS = {
    'identificacion_deudor': 'strIdentificacion',
    'fecha_gestion':         'fecha_gestion',
    'casa_cobranza':         'Actor_gestion',
    'accion':                'Accion',
    'respuesta':             'Respuesta',
}

def _get_rango(
    labels:pd.DataFrame,
    ventana_extra: int = VENTANA_EXTRA,
) -> list[int]:
    '''Periodos de labels mas `ventana_extra` meses antes del mas antiguo.'''

    PERIODOS = {int(p) for p in labels['strPeriodo'].unique()}

    PERIODO_MINIMO = datetime.datetime.strptime(str(min(PERIODOS)), '%Y%m')

    PERIODOS_ADICIONALES = {
        int((PERIODO_MINIMO - relativedelta(months=i)).strftime('%Y%m'))
        for i in range(1, ventana_extra + 1)
    }

    return sorted(PERIODOS | PERIODOS_ADICIONALES)

def _leer_archivo(
    ruta_gestiones:str | Path,
    periodo:int,
    cedulas:set[int],
) -> pd.DataFrame:
    '''Lee el Excel de un periodo y lo deja con las columnas de COLUMNAS.

    Se queda solo con la poblacion de labels: el archivo trae a todos los
    deudores de la cartera.

    Raises:
        FileNotFoundError: Si no existe el archivo del periodo.
        KeyError: Si al archivo le falta alguna columna de COLUMNAS.
    '''
    RUTA_ARCHIVO = Path(ruta_gestiones) / str(periodo)[:4] / f'GESTIONES_{periodo}.xlsx'

    if not RUTA_ARCHIVO.exists():
        raise FileNotFoundError(f'El archivo: {RUTA_ARCHIVO} no existe...')

    print(f'Extrayendo gestiones {periodo}...')

    # --- Se lee todo y luego se normalizan los nombres --- #

    gestiones = clean_names(
        pd.read_excel(
            RUTA_ARCHIVO,
            dtype=str,
        )
    )

    # --- Duplicados exactos en TODAS las columnas del archivo: error de carga. --- #
    # --- Se quitan antes de reducir a COLUMNAS: despues, dos gestiones       --- #
    # --- legitimas del mismo dia (sin hora) se verian iguales.               --- #

    DUPLICADAS = gestiones.duplicated()

    if DUPLICADAS.any():
        print(f'   {DUPLICADAS.sum()} filas duplicadas exactas descartadas')

    gestiones = gestiones.loc[~DUPLICADAS]

    FALTANTES = [c for c in COLUMNAS if c not in gestiones.columns]

    if FALTANTES:
        raise KeyError(f'{RUTA_ARCHIVO.name}: faltan columnas {FALTANTES}')

    gestiones = gestiones[list(COLUMNAS)].rename(columns=COLUMNAS)

    # --- Cedula a numero y fecha a datetime: lo que no convierte se descarta --- #

    CEDULA = pd.to_numeric(gestiones['strIdentificacion'], errors='coerce')
    FECHA = pd.to_datetime(gestiones['fecha_gestion'], format=FORMATO_FECHA, errors='coerce')

    INVALIDAS = CEDULA.isna() | FECHA.isna()

    if INVALIDAS.any():
        print(
            f'   {INVALIDAS.sum()} filas descartadas '
            f'(cedula no numerica: {CEDULA.isna().sum()} | fecha invalida: {FECHA.isna().sum()})'
        )

    gestiones = (
        gestiones
        .assign(
            strIdentificacion=CEDULA,
            fecha_gestion=FECHA,
        )
        .loc[~INVALIDAS]
        .astype({'strIdentificacion':'int64'})
    )

    # --- El periodo sale de la fecha de la gestion, no del nombre del archivo. --- #
    # --- Las de otro mes estan repetidas en el archivo de su mes: se descartan --- #

    gestiones = gestiones.assign(
        strPeriodo=gestiones['fecha_gestion'].dt.strftime('%Y%m').astype('int64'),
    )

    OTRO_MES = gestiones['strPeriodo'] != periodo

    if OTRO_MES.any():
        print(f'   {OTRO_MES.sum()} filas con fecha de otro mes descartadas')

    # --- Poblacion de labels --- #

    gestiones = gestiones[~OTRO_MES & gestiones['strIdentificacion'].isin(cedulas)]

    print(f'   filas: {len(gestiones)}')

    return gestiones

def extract_gestiones_directory(
    labels:pd.DataFrame,
    ruta_gestiones:str | Path,
    ventana_extra: int = VENTANA_EXTRA,
) -> pd.DataFrame:
    '''Extrae las gestiones de la poblacion de labels desde la carpeta compartida.

    Args:
        labels: Panel de etiquetas. Define poblacion y rango de periodos.
        ruta_gestiones: Carpeta raiz de los Excel (RUTA_GESTIONES en config.yml).
        ventana_extra: Meses de historia adicional antes del periodo mas antiguo.

    Raises:
        ValueError: Si labels esta vacio.
        FileNotFoundError: Si falta el archivo de algun periodo del rango.
    '''
    if labels.empty:
        raise ValueError('labels esta vacio: no hay poblacion que consultar')

    RANGO = _get_rango(
        labels,
        ventana_extra,
    )

    CEDULAS = set(labels['strIdentificacion'].astype('int64').unique())

    print(f'{KIND}: {len(RANGO)} periodos ({RANGO[0]} a {RANGO[-1]}) x {len(CEDULAS)} cedulas')

    # --- ciclo de extraccion --- #

    file_wrapper = [
        _leer_archivo(
            ruta_gestiones=ruta_gestiones,
            periodo=p,
            cedulas=CEDULAS,
        )
        for p in RANGO
    ]

    gestiones = (
        pd.concat(
            file_wrapper,
            axis=0,
            ignore_index=True
        )
    )

    return gestiones

if __name__ == '__main__':

    CONFIG = leer_config()

    labels = pd.read_parquet(find_last(DATA_LABELS))

    gestiones = extract_gestiones_directory(
        labels=labels,
        ruta_gestiones=CONFIG['RUTA_GESTIONES'],
    )

    guardar(df=gestiones, path=DATA_FEATURES, name=KIND)
