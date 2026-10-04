'''Lee config/config.yml y lo expone como diccionario.'''
from pathlib import Path

import yaml

from propensity.config import PROJECT_ROOT

CONFIG_YML = PROJECT_ROOT / 'config' / 'config.yml'


def leer_config(
    ruta: str | Path = CONFIG_YML,
) -> dict:
    '''Retorna el contenido de config.yml como diccionario.

    Args:
        ruta: Ruta al .yml. Por defecto config/config.yml en la raiz.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si el contenido no es un mapeo clave: valor.
    '''
    RUTA = Path(ruta)

    if not RUTA.exists():
        raise FileNotFoundError(f'No existe el archivo de configuracion: {RUTA}')

    with open(RUTA, encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    if not isinstance(config, dict):
        raise ValueError(f'{RUTA.name} debe ser un mapeo clave: valor')

    return config
