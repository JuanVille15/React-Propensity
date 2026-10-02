'''Limpieza de la demografica - familia foto.

Recibe la salida cruda de `extract_demografica` (una fila por asociado y
periodo, columnas con prefijo demo_) y la deja lista para el cruce con
labels. Las reglas salen del EDA (notebooks/EDA_demo.ipynb,
docs/conclusiones_EDA_demografica.txt).

Todas las reglas son FIJAS (listas y topes constantes), ninguna se ajusta
con los datos de la corrida: asi la limpieza se puede aplicar igual a
train, test y scoring sin fuga de informacion. Lo que si depende de los
datos (imputacion, escalado, winsorizar por percentil) va en el paso de
modelado, ajustado solo sobre train.
'''
import numpy as np
import pandas as pd

from propensity.config import DATA_FEATURES, DATA_INTERIM
from propensity.utils.utils import find_last, guardar

LLAVES = ['strIdentificacion', 'strPeriodo']
SIN_DATO = 'Sin dato'
OTROS = 'Otros'

# --- Poblacion: personas naturales. NIT se excluye por ser empresa, --- #
# --- el resto de tipos por volumen (< 150 filas).                   --- #

TIPOS_DOCUMENTO = ['CC', 'CE']

# --- Sin poder predictivo en el EDA (IV ~ 0) --- #

COLS_DESCARTAR = [
    'demo_Tipo_Documento',
    'demo_Sexo',
]

# --- Codigos que en realidad significan "no hay dato" --- #

CODIGOS_SIN_DATO = [
    'No Cruza',
    'No Definido',
    'Desconocida',
    'Sin Segmento',
    'Ninguno / No definido',
]

# --- Categoricas: categorias que se conservan. Lo que no este en la --- #
# --- lista (y no sea sin dato) se agrupa en 'Otros'. Los renombres   --- #
# --- unen categorias con tasa de reactivacion similar.               --- #

CATEGORIAS = {
    'demo_Tipo_Vinculacion': {
        'conservar': [
            'Profesional', 'Técnicos y Tecnólogos', 'Familiar Asociado',
            'Mayor 60', 'Recién Graduado', 'Estudiante',
            'Empleado No Profesional', 'Transición', 'Personas Jurídicas',
        ],
    },
    'demo_Estado_Civil': {
        'conservar': ['Soltero', 'Casado', 'Union Libre', 'Separado/Viudo'],
        'renombrar': {
            'Separado':   'Separado/Viudo',
            'Divorciado': 'Separado/Viudo',
            'Viudo':      'Separado/Viudo',
        },
    },
    'demo_Nombre_Tipo_Vivienda': {
        'conservar': ['Familiar', 'Propia', 'Alquiler'],
    },
    'demo_Nombre_Nivel_Academico': {
        'conservar': ['Profesional', 'Técnico', 'Tecnólogo', 'Ninguno'],
    },
    'demo_Nombre_Ocupacion': {
        'conservar': [
            'Asalariado', 'Independiente', 'Otro tipo de Actividad',
            'Pensionado - Jubilado', 'Estudiante',
        ],
    },
    'demo_Segmento_Ciclo_de_Vida': {
        'conservar': [
            'Consolidacion', 'Transicion', 'Mujer Independiente',
            'En Formación', 'Maduro', 'Joven Asociado',
        ],
    },
}

# --- Estrato: 1-6 validos. 9 y 'No Cruza' son sin dato. 5 y 6 tienen --- #
# --- la misma tasa: se agrupan en 5 (= 5+).                          --- #

ESTRATOS_VALIDOS = ['1', '2', '3', '4', '5', '6']
TOPE_ESTRATO = 5

# --- Discretas: cola superior agrupada (valor = tope significa tope+) --- #
# --- suma_productos NO se topa: la tasa sigue subiendo con 4+.        --- #

TOPES_DISCRETAS = {
    'demo_Personas_a_Cargo': 1,
    'demo_Personas_a_Cargo_Menores_18': 2,
}

# --- Montos: tope fijo = p99 observado en el EDA (27-09-2026). Los   --- #
# --- maximos (9.100 M en ingresos, 6.000 M en egresos) son errores.  --- #

TOPES_MONTOS = {
    'demo_Ingresos': 30_000_000,
    'demo_Egresos':  10_500_000,
}

EDAD_MIN = 18
EDAD_MAX = 100


def _filtrar_poblacion(df: pd.DataFrame) -> pd.DataFrame:
    '''Deja solo personas naturales (CC y CE).'''

    mask = df['demo_Tipo_Documento'].isin(TIPOS_DOCUMENTO)
    print(f'Filtro tipo documento: se excluyen {(~mask).sum()} filas')

    return df[mask]


def _indicadores(df: pd.DataFrame) -> pd.DataFrame:
    '''Crea flags de faltantes / valores especiales que resultaron informativos.

    Se calculan ANTES de limpiar, porque la limpieza convierte esos valores
    en NaN y se perderia la distincion.
    '''
    estrato = df['demo_Estrato'].astype(str).str.strip()

    return df.assign(
        demo_flag_egresos_nulo=df['demo_Egresos'].isna().astype('int8'),
        demo_flag_ingresos_sin_dato=(
            df['demo_Ingresos'].isna() | (df['demo_Ingresos'] <= 0)
        ).astype('int8'),
        demo_flag_acierta_sin_consulta=(df['demo_Ptaje_acierta'] == 0).astype('int8'),
        demo_flag_estrato_sin_dato=(~estrato.isin(ESTRATOS_VALIDOS)).astype('int8'),
    )


def _limpiar_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    '''Unifica sin dato, agrupa categorias pequenas y convierte a category.'''

    df = df.copy()

    for col, reglas in CATEGORIAS.items():
        x = df[col].str.strip()
        x = x.replace(reglas.get('renombrar', {}))

        sin_dato = x.isna() | x.isin(CODIGOS_SIN_DATO)
        conservar = x.isin(reglas['conservar'])

        x = x.where(conservar, OTROS).where(~sin_dato, SIN_DATO)

        df[col] = pd.Categorical(
            x,
            categories=reglas['conservar'] + [OTROS, SIN_DATO],
        )

    return df


def _limpiar_discretas(df: pd.DataFrame) -> pd.DataFrame:
    '''Estrato a numero ordinal y topes en las discretas.'''

    df = df.copy()

    # --- Estrato: texto -> numero; codigos invalidos a NaN (quedan en el flag) --- #

    estrato = pd.to_numeric(df['demo_Estrato'], errors='coerce')
    estrato = estrato.where(estrato.between(1, 6))
    df['demo_Estrato'] = estrato.clip(upper=TOPE_ESTRATO).astype('Int8')

    for col, tope in TOPES_DISCRETAS.items():
        df[col] = df[col].clip(upper=tope)

    return df


def _limpiar_numericas(df: pd.DataFrame) -> pd.DataFrame:
    '''Invalidos a NaN y tope fijo en montos.'''

    df = df.copy()

    # --- Valores imposibles -> NaN --- #

    df['demo_Edad'] = df['demo_Edad'].where(
        df['demo_Edad'].between(EDAD_MIN, EDAD_MAX)
    )
    df['demo_Cuotas_canceladas_aportes'] = df['demo_Cuotas_canceladas_aportes'].where(
        df['demo_Cuotas_canceladas_aportes'] >= 0
    )
    df['demo_Saldoaportes'] = df['demo_Saldoaportes'].where(
        df['demo_Saldoaportes'] >= 0
    )

    # --- Ingresos en 0 no es un ingreso real: queda en el flag --- #

    df['demo_Ingresos'] = df['demo_Ingresos'].where(df['demo_Ingresos'] > 0)

    # --- Ptaje 0 = sin consulta en centrales, no un puntaje bajo --- #

    df['demo_Ptaje_acierta'] = df['demo_Ptaje_acierta'].replace(0, np.nan)

    # --- Montos: tope fijo --- #

    for col, tope in TOPES_MONTOS.items():
        df[col] = df[col].clip(upper=tope)

    return df


def clean_demo(demografica: pd.DataFrame) -> pd.DataFrame:
    '''Aplica la limpieza completa de la demografica.

    Orden: poblacion -> flags -> categoricas -> discretas -> numericas ->
    descarte de columnas. Los flags van antes de limpiar porque leen los
    valores originales (ceros, codigos de sin dato) que despues se vuelven NaN.

    La salida conserva las filas de CC y CE solamente: al cruzar con labels
    usar how='inner' (o filtrar labels con estas llaves) para que la
    poblacion del modelo sea la misma.

    Args:
        demografica: Salida de `extract_demografica`.

    Raises:
        KeyError: Si falta alguna columna esperada.
        ValueError: Si hay llaves duplicadas.
    '''
    ESPERADAS = (
        LLAVES
        + COLS_DESCARTAR
        + list(CATEGORIAS)
        + ['demo_Estrato', 'demo_Edad', 'demo_Ptaje_acierta',
           'demo_Cuotas_canceladas_aportes', 'demo_Saldoaportes']
        + list(TOPES_DISCRETAS)
        + list(TOPES_MONTOS)
    )
    FALTANTES = [c for c in ESPERADAS if c not in demografica.columns]

    if FALTANTES:
        raise KeyError(f'demografica: faltan columnas {FALTANTES}')

    DUPLICADOS = demografica.duplicated(subset=LLAVES).sum()

    if DUPLICADOS > 0:
        raise ValueError(f'demografica: {DUPLICADOS} filas con llave duplicada')

    print(f'Limpiando demografica: {len(demografica)} filas...')

    limpia = (
        demografica
        .pipe(_filtrar_poblacion)
        .pipe(_indicadores)
        .pipe(_limpiar_categoricas)
        .pipe(_limpiar_discretas)
        .pipe(_limpiar_numericas)
        .drop(columns=COLS_DESCARTAR)
        .reset_index(drop=True)
    )

    print(f'demografica limpia: {len(limpia)} filas | {limpia.shape[1]} columnas')

    return limpia


if __name__ == '__main__':

    demografica = pd.read_parquet(find_last(DATA_FEATURES / 'demografica'))

    limpia = clean_demo(demografica=demografica)

    guardar(df=limpia, path=DATA_INTERIM, name='demografica')
