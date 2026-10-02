'''Orquestacion de la extraccion.

Sabe en que orden corren las fuentes, contra que base va cada una y
donde se persiste cada resultado. No sabe consultar nada: eso vive en
extract/ y en utils/.
'''
from typing import Callable

import pandas as pd
from sqlalchemy import Engine

from propensity.config import DATA_FEATURES, DATA_INTERIM, DATA_LABELS, DATA_RAW, get_db_settings
from propensity.db import build_bi_con, build_gcc_con
from propensity.extract.cantidad_productos import extract_cantidad_productos
from propensity.extract.demografica import extract_demografica
from propensity.extract.fac_rec_coomeva import extract_fac_rec_coomeva
from propensity.extract.fac_rec_estatu import extract_fac_rec_estatu
from propensity.extract.fac_rec_gecc import extract_fac_rec_gecc
from propensity.extract.gestiones import extract_gestiones
from propensity.extract.labels import extract_labels
from propensity.extract.pagos import EMPRESAS, extract_pagos
from propensity.extract.v_360 import extract_v_360
from propensity.transformacion.clean_demo import clean_demo
from propensity.utils.utils import find_last, guardar

# --- Cada fuente: que funcion la extrae y contra que base --- #
# --- Agregar una fuente nueva es una linea aca.           --- #

FUENTES: dict[str, tuple[Callable, str]] = {
    'demografica':        (extract_demografica,        'bi'),
    'v_360':              (extract_v_360,              'bi'),
    'cantidad_productos': (extract_cantidad_productos, 'bi'),
    'fac_rec_gecc':       (extract_fac_rec_gecc,       'bi'),
    'pagos':              (extract_pagos,              'bi'),
    'fac_rec_coomeva':    (extract_fac_rec_coomeva,    'gcc'),
    'fac_rec_estatu':     (extract_fac_rec_estatu,     'gcc'),
    'gestiones':          (extract_gestiones,          'gcc'),
}

# --- Limpieza: fuente -> funcion que la limpia.       --- #
# --- Lee de data/raw/features/<fuente>/ y persiste en --- #
# --- data/interim/<fuente>/.                          --- #

LIMPIEZAS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    'demografica': clean_demo,
}


class _Engines:
    '''Crea cada engine la primera vez que se pide, y lo reusa.

    Evita abrir una conexion a Oracle cuando solo se pidio una fuente
    de BI, y evita crear un pool nuevo por fuente.
    '''

    def __init__(self) -> None:
        self._engines: dict[str, Engine] = {}

    def get(self, base: str) -> Engine:
        if base not in self._engines:
            print(f'Abriendo conexion: {base.upper()}...')
            if base == 'bi':
                self._engines[base] = build_bi_con(get_db_settings('sql-server'))
            elif base == 'gcc':
                self._engines[base] = build_gcc_con(get_db_settings('oracle'))
            else:
                raise ValueError(f'Base desconocida: {base} - posibles: bi, gcc')
        return self._engines[base]


def _extraer_fuente(
    fuente: str,
    labels: pd.DataFrame,
    engines: _Engines,
) -> None:
    '''Extrae una fuente y la persiste en data/raw/features/<fuente>/.'''

    funcion, base = FUENTES[fuente]
    engine = engines.get(base)

    # --- pagos es una fuente pero dos extracciones, una por empresa --- #

    if fuente == 'pagos':
        for empresa in EMPRESAS:
            df = funcion(labels=labels, engine=engine, empresa=empresa)
            nombre = f'pagos_{empresa.lower().replace(" ", "_")}'
            guardar(df=df, path=DATA_FEATURES, name=nombre)
        return

    df = funcion(labels=labels, engine=engine)
    guardar(df=df, path=DATA_FEATURES, name=fuente)


def run_extract(
    fuente: str,
    periodo: int | None = None,
    n_periodos: int | None = None,
) -> None:
    '''Corre la extraccion de una fuente, o de todas en secuencia.

    Con `fuente='all'` extrae primero labels y le pasa ESE dataframe en
    memoria a todas las features, de modo que la corrida completa quede
    sobre una sola poblacion. Con una fuente puntual, labels se lee del
    ultimo parquet en disco.

    Si una fuente falla, las demas siguen: los errores se acumulan y se
    reportan al final, y lo que si salio ya quedo persistido.

    Args:
        fuente: Nombre en FUENTES, 'labels', o 'all'.
        periodo: Ultimo periodo a etiquetar (solo aplica a labels).
        n_periodos: Cuantos periodos etiquetar (solo aplica a labels).

    Raises:
        ValueError: Si la fuente no existe.
        RuntimeError: Si alguna fuente fallo durante la corrida.
    '''
    VALIDAS = list(FUENTES) + ['labels', 'all']

    if fuente not in VALIDAS:
        raise ValueError(f'Fuente no valida: {fuente} - posibles: {VALIDAS}')

    engines = _Engines()

    # ==========================
    # LABELS: define poblacion
    # ==========================

    if fuente in ('labels', 'all'):
        print('=' * 60)
        print('EXTRAYENDO LABELS')
        print('=' * 60)

        kwargs = {}
        if periodo is not None:
            kwargs['periodo'] = periodo
        if n_periodos is not None:
            kwargs['n_periodos'] = n_periodos

        labels = extract_labels(engine=engines.get('bi'), **kwargs)
        guardar(df=labels, path=DATA_RAW, name='labels')

        if fuente == 'labels':
            return
    else:
        labels = pd.read_parquet(find_last(DATA_LABELS))
        print(f'labels: {len(labels)} filas | {labels["strPeriodo"].nunique()} periodos')

    # ==========================
    # FEATURES
    # ==========================

    objetivo = list(FUENTES) if fuente == 'all' else [fuente]

    fallidas: dict[str, str] = {}

    for nombre in objetivo:
        print()
        print('=' * 60)
        print(f'EXTRAYENDO {nombre.upper()}  ({objetivo.index(nombre) + 1}/{len(objetivo)})')
        print('=' * 60)
        try:
            _extraer_fuente(fuente=nombre, labels=labels, engines=engines)
        except Exception as e:
            print(f'FALLO {nombre}: {type(e).__name__}: {e}')
            fallidas[nombre] = f'{type(e).__name__}: {e}'

    # ==========================
    # REPORTE FINAL
    # ==========================

    exitosas = [f for f in objetivo if f not in fallidas]

    print()
    print('=' * 60)
    print(f'RESUMEN: {len(exitosas)} ok | {len(fallidas)} con error')
    print('=' * 60)

    for nombre in exitosas:
        print(f'  ok     {nombre}')
    for nombre, error in fallidas.items():
        print(f'  ERROR  {nombre}: {error}')

    if fallidas:
        raise RuntimeError(
            f'Fuentes con error: {list(fallidas)}. '
            f'Reintenta solo esas con --fuente <nombre>.'
        )


def run_clean(fuente: str) -> None:
    '''Limpia una fuente (o todas las que tienen limpieza) y la persiste.

    Toma el ultimo parquet de data/raw/features/<fuente>/ y guarda el
    resultado en data/interim/<fuente>/.

    Args:
        fuente: Nombre en LIMPIEZAS, o 'all'.

    Raises:
        ValueError: Si la fuente no tiene limpieza definida.
    '''
    VALIDAS = list(LIMPIEZAS) + ['all']

    if fuente not in VALIDAS:
        raise ValueError(f'Fuente sin limpieza: {fuente} - posibles: {VALIDAS}')

    objetivo = list(LIMPIEZAS) if fuente == 'all' else [fuente]

    for nombre in objetivo:
        print('=' * 60)
        print(f'LIMPIANDO {nombre.upper()}')
        print('=' * 60)

        cruda = pd.read_parquet(find_last(DATA_FEATURES / nombre))
        limpia = LIMPIEZAS[nombre](cruda)
        guardar(df=limpia, path=DATA_INTERIM, name=nombre)


if __name__ == '__main__':
    run_extract(fuente='all')
