'''Limpieza de la Vista 360 - familia foto.

Recibe la salida cruda de `extract_v_360` (una fila por asociado y periodo,
columnas con prefijo v360_) y la deja lista para el cruce con labels. Los
pasos son los del EDA (notebooks/EDA_v360.ipynb), en el mismo orden:

    1. Columnas identificadoras
    2. Columnas CeroPapel y Producto recomendado
    3. Textos de sin dato -> NaN
    4. Columnas con alto % de nulos
    5. Columnas constantes
    6. Columnas cuasi-constantes (se rescatan las que tienen lift en la minoria)
    7. Columnas con alta correlacion
    8. Columnas eliminadas por logica
    9. Columnas ya contenidas en la demografica

Se separa en dos funciones:
    - `seleccionar_columnas`: corre los pasos y decide que columnas quedan.
      Necesita labels (el paso 6 usa el target).
    - `clean_v360`: aplica esa seleccion a cualquier v_360 (train, test o
      scoring), sin volver a decidir.

`documentar` y `exportar_documentacion` generan el excel de documentacion
(docs/) y el .json de columnas a tener en cuenta (config/), con la fecha de
ejecucion en el nombre.
'''
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from propensity.config import DATA_FEATURES, DATA_INTERIM, DATA_LABELS, PROJECT_ROOT
from propensity.utils.utils import find_last, guardar

LLAVES = ['strIdentificacion', 'strPeriodo']
TARGET = 'IndicadorReactivado'
PREFIJO = 'v360_'

TENER_EN_CUENTA = 'Tener en cuenta'

DOCS_DIR = PROJECT_ROOT / 'docs'
CONFIG_DIR = PROJECT_ROOT / 'config'

# --- 1. Identificadoras --- #

COLS_IDENTIFICADORAS = [
    f'{PREFIJO}{c}' for c in [
        'skcliente', 'Estado', 'IndInactivo', 'Regional', 'Zona', 'Oficina',
        'Area Conocimiento', 'Habeas Data', 'ColaboradorGECC', 'Tipo Cliente',
        'Tipologia_Ciudad_Vinculacion', 'Tipologia_Ciudad_Residencia',
        'Nombre Asociado', 'CodDaneCiudadResidencia', 'CiudadResidencia',
        'CodDaneCiudadHomologada', 'CiudadHomologada', 'dtmFechaInsercion',
        'dtmFechaActualizacionBI', 'Alerta_ActualizacionDatos',
        'Fecha_Actualizacion_NPS_SAO', 'Fecha_Actualizacion_NPS_MI',
        'TipoIdentificacion',
        'Turnos_En_Oficinas_UltimaOficinaVisitada_Ult12Meses',
        'Identificacion', 'Periodo',
    ]
]

# --- 2. CeroPapel / Producto recomendado: se buscan por nombre --- #

PATRON_CERO_PAPEL = 'CeroPapel'
PATRON_PRODUCTO = 'Producto'

# --- 3. Textos que en realidad significan "no hay dato" --- #

VALORES_NULOS = [
    '', ' ', '  ', 'nan', 'NaN', 'NULL', 'null', 'N/A', 'n/a', 'NA',
    'ninguno', 'NINGUNO', '-', 'Sin información',
]

# --- 4 a 7. Umbrales --- #

UMBRAL_NULOS = 30           # % de nulos a partir del cual se elimina
UMBRAL_CUASI = 0.95         # frecuencia de la moda a partir de la cual es cuasi-constante
MIN_POS_RESCATE = 50        # positivos minimos en la minoria para rescatar
LIFT_RESCATE = 2.0          # lift minimo de la minoria para rescatar
UMBRAL_CORR = 0.95          # |spearman| a partir del cual se elimina

# --- 8. Eliminadas por logica --- #

COLS_LOGICA = [
    'v360_Tipo_Cliente_Asociado',
    'v360_UltimoEventoRecreacionAsistio_Histo',
    'v360_DebitoAutomatico',
    'v360_TIENE EL DEBITO AUTOMATICO AUTORIZADO',
    'v360_Corte_Facturacion_Asociado',
    'v360_Profesion',
]

# --- 9. Ya presentes en la demografica --- #

COLS_EN_DEMO = [
    'v360_Puntaje Acierta',
    'v360_Genero',
    'v360_Edad',
    'v360_Rango Edad',
    'v360_Antiguedad Actual (Años)',
    'v360_Tipo Vinculacion',
    'v360_Puntaje Acierta Rango',
    'v360_Estado Civil',
    'v360_Nivel Academico',
    'v360_Actividad Laboral',
    'v360_Rango Ingresos',
    'v360_numValorIngresos',
    'v360_Tipo de Vivienda',
    'v360_Segmento',
    'v360_Menores a cargo',
    'v360_Adultos a cargo',
    'v360_Estrato',
]


def _features(df: pd.DataFrame) -> list[str]:
    '''Columnas evaluables: todo menos llaves y target.'''

    return [c for c in df.columns if c not in LLAVES + [TARGET]]


def _cols_con_patron(df: pd.DataFrame, patron: str) -> list[str]:
    '''Paso 2: columnas cuyo nombre contiene `patron` (CeroPapel, Producto).'''

    return [c for c in _features(df) if patron in c.strip()]


def _reemplazar_nulos(df: pd.DataFrame) -> pd.DataFrame:
    '''Paso 3: textos de sin dato -> NaN.'''

    return df.replace(VALORES_NULOS, np.nan)


def _cols_alta_nulidad(df: pd.DataFrame, umbral: float = UMBRAL_NULOS) -> list[str]:
    '''Paso 4: columnas con `umbral`% o mas de nulos.'''

    pp_nulos = df[_features(df)].isnull().mean() * 100

    return pp_nulos.loc[pp_nulos >= umbral].index.tolist()


def _cols_constantes(df: pd.DataFrame) -> list[str]:
    '''Paso 5: columnas con un solo valor (sin contar nulos).'''

    return [c for c in _features(df) if df[c].nunique(dropna=True) <= 1]


def _evaluar_candidatas(
    df: pd.DataFrame,
    candidatas: list[str],
    min_pos: int = MIN_POS_RESCATE,
    lift_alto: float = LIFT_RESCATE,
) -> pd.DataFrame:
    '''Tasa de reactivacion en la minoria (todo lo que no es la moda).

    Una columna cuasi-constante se rescata si su minoria concentra
    reactivadores: al menos `min_pos` positivos y lift >= `lift_alto`.
    '''
    base = df[TARGET].mean()
    filas = []

    for col in candidatas:
        g = df.groupby(col, dropna=False)[TARGET].agg(['size', 'sum'])
        g.columns = ['n', 'pos']
        moda = g['n'].idxmax()
        minoria = g.drop(index=moda)

        n_min = minoria['n'].sum()
        pos_min = minoria['pos'].sum()
        tasa = pos_min / n_min if n_min else 0
        lift = tasa / base if base else 0

        filas.append({
            'columna': col,
            'pct_moda': g['n'].max() / len(df),
            'n_minoria': n_min,
            'pos_minoria': pos_min,
            'tasa_minoria': tasa,
            'lift_minoria': lift,
            'rescatar': (pos_min >= min_pos) and (lift >= lift_alto),
        })

    return pd.DataFrame(filas).sort_values('lift_minoria', ascending=False)


def _cols_cuasi_constantes(df: pd.DataFrame, umbral: float = UMBRAL_CUASI) -> list[str]:
    '''Paso 6: cuasi-constantes que NO se rescatan por lift.'''

    candidatas = [
        c for c in _features(df)
        if df[c].value_counts(normalize=True).iloc[0] >= umbral
    ]

    if not candidatas:
        return []

    evaluacion = _evaluar_candidatas(df=df, candidatas=candidatas)

    print(f'Cuasi-constantes: {len(candidatas)} candidatas | '
          f'{evaluacion["rescatar"].sum()} rescatadas')

    return evaluacion.loc[~evaluacion['rescatar'], 'columna'].tolist()


def _cols_alta_correlacion(df: pd.DataFrame, umbral: float = UMBRAL_CORR) -> list[str]:
    '''Paso 7: numericas con |spearman| > `umbral` contra alguna anterior.

    Los nulos se imputan con la mediana solo para calcular la correlacion.
    '''
    num = df[_features(df)].select_dtypes('number')
    num = num.fillna(num.median())

    corr = num.corr(method='spearman').abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))

    return [c for c in upper.columns if any(upper[c] > umbral)]


def seleccionar_columnas(
    v_360: pd.DataFrame,
    labels: pd.DataFrame,
) -> dict[str, str]:
    '''Corre los pasos del EDA y decide que columnas de v_360 se conservan.

    Cada paso se evalua sobre lo que dejo el anterior, igual que en el
    notebook. Debe correrse sobre los periodos de entrenamiento: el paso 6
    usa el target.

    Args:
        v_360: Salida de `extract_v_360`.
        labels: Panel de etiquetas con `IndicadorReactivado`.

    Returns:
        {columna: decision} para todas las columnas de v_360. Las que se
        conservan tienen la decision 'Tener en cuenta'.
    '''
    df = labels[LLAVES + [TARGET]].merge(v_360, how='left', on=LLAVES)

    decisiones = {c: TENER_EN_CUENTA for c in v_360.columns}

    def _eliminar(df: pd.DataFrame, cols: list[str], motivo: str) -> pd.DataFrame:
        for c in cols:
            decisiones[c] = motivo
        print(f'{motivo}: {len(cols)} columnas')
        return df.drop(columns=cols)

    df = _eliminar(df, [c for c in COLS_IDENTIFICADORAS if c in df.columns],
                   'Columna Identificadora')
    df = _eliminar(df, _cols_con_patron(df, PATRON_CERO_PAPEL),
                   'Columna Cero Papel - No util')
    df = _eliminar(df, _cols_con_patron(df, PATRON_PRODUCTO),
                   'Columna Producto Recomendado - No Util')

    df = _reemplazar_nulos(df)

    df = _eliminar(df, _cols_alta_nulidad(df), 'Alta Proporcion Nulos')
    df = _eliminar(df, _cols_constantes(df), 'Columna Constante')
    df = _eliminar(df, _cols_cuasi_constantes(df), 'Columna Cuasi-Constante (95% mismo valor)')
    df = _eliminar(df, _cols_alta_correlacion(df), 'Columnas con 95% de correlacion')
    df = _eliminar(df, [c for c in COLS_LOGICA if c in df.columns],
                   'Columna Eliminada por logica')
    df = _eliminar(df, [c for c in COLS_EN_DEMO if c in df.columns],
                   'Columna Contenida en Demografica')

    print(f'Se conservan {len(_features(df))} columnas')

    return decisiones


def clean_v360(
    v_360: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    '''Aplica a v_360 la seleccion de `seleccionar_columnas`.

    Args:
        v_360: Salida de `extract_v_360`.
        columnas: Columnas a conservar (las 'Tener en cuenta').

    Raises:
        KeyError: Si falta alguna columna de `columnas`.
        ValueError: Si hay llaves duplicadas.
    '''
    COLUMNAS = LLAVES + [c for c in columnas if c not in LLAVES]

    FALTANTES = [c for c in COLUMNAS if c not in v_360.columns]

    if FALTANTES:
        raise KeyError(f'v360: faltan columnas {FALTANTES}')

    DUPLICADOS = v_360.duplicated(subset=LLAVES).sum()

    if DUPLICADOS > 0:
        raise ValueError(f'v360: {DUPLICADOS} filas con llave duplicada')

    limpia = (
        v_360[COLUMNAS]
        .pipe(_reemplazar_nulos)
        .reset_index(drop=True)
    )

    print(f'v360 limpia: {len(limpia)} filas | {limpia.shape[1]} columnas')

    return limpia


def documentar(
    v_360: pd.DataFrame,
    decisiones: dict[str, str],
    limpia: pd.DataFrame,
) -> pd.DataFrame:
    '''Tabla de documentacion: una fila por columna de v_360.

    Nulos y frecuencia de la moda se miden sobre v_360 con los textos de sin
    dato ya convertidos a NaN. El tipo 'binaria' se asigna a las columnas
    conservadas con 2 valores o menos en la v_360 limpia.

    Args:
        v_360: Salida de `extract_v_360`.
        decisiones: Salida de `seleccionar_columnas`.
        limpia: Salida de `clean_v360`.
    '''
    base = _reemplazar_nulos(v_360)

    moda = {
        c: round(base[c].value_counts(dropna=False, normalize=True).iloc[0], 2)
        for c in base.columns
    }

    doc = pd.DataFrame({
        'Nombre_Columna': base.columns.tolist(),
        'Tipo_Dato': base.dtypes.astype(str).replace('object', 'str').values,
        'Cantidad_Nulos': base.isnull().mean().values,
        'FrecuenciaModa': [moda[c] for c in base.columns],
        'Decision': [decisiones[c] for c in base.columns],
    })

    binarias = [
        c for c in limpia.columns
        if c not in LLAVES and limpia[c].nunique() <= 2
    ]

    doc.loc[doc['Nombre_Columna'].isin(binarias), 'Tipo_Dato'] = 'binaria'

    return doc


def exportar_documentacion(
    doc: pd.DataFrame,
    docs_dir: Path = DOCS_DIR,
    config_dir: Path = CONFIG_DIR,
) -> None:
    '''Exporta el excel de documentacion y el .json de columnas a tener en cuenta.

    Nombres: doc_v360_<dd-mm-aaaa>.xlsx y columns_360_<dd-mm-aaaa>.json.
    '''
    HOY = datetime.datetime.today().strftime('%d-%m-%Y')

    RUTA_DOC = Path(docs_dir) / f'doc_v360_{HOY}.xlsx'
    RUTA_JSON = Path(config_dir) / f'columns_360_{HOY}.json'

    RUTA_DOC.parent.mkdir(parents=True, exist_ok=True)
    RUTA_JSON.parent.mkdir(parents=True, exist_ok=True)

    doc.to_excel(RUTA_DOC, index=False)
    print(f'Documentacion exportada: {RUTA_DOC}')

    conservar = doc[doc['Decision'] == TENER_EN_CUENTA]

    json_vista = {
        'Columna': conservar['Nombre_Columna'].tolist(),
        'Tipo': conservar['Tipo_Dato'].tolist(),
    }

    with open(RUTA_JSON, mode='w', encoding='utf-8') as writer:
        json.dump(json_vista, fp=writer, ensure_ascii=False, indent=4)

    print(f'Columnas exportadas: {RUTA_JSON}')


if __name__ == '__main__':

    labels = pd.read_parquet(find_last(DATA_LABELS))
    v_360 = pd.read_parquet(find_last(DATA_FEATURES / 'v_360'))

    decisiones = seleccionar_columnas(v_360=v_360, labels=labels)
    columnas = [c for c, d in decisiones.items() if d == TENER_EN_CUENTA]

    limpia = clean_v360(v_360=v_360, columnas=columnas)

    doc = documentar(v_360=v_360, decisiones=decisiones, limpia=limpia)
    exportar_documentacion(doc=doc)

    guardar(df=limpia, path=DATA_INTERIM, name='v_360')
