'''Carga variables de entorno asi como tambien
   Configuracion en YAML '''

import os
from dotenv import load_dotenv
from typing import Literal,cast
from pathlib import Path


def _get_root(
      marker:str='pyproject.toml'
   ) -> Path:
   
   '''Sube desde este archivo hasta encontrar la raíz del proyecto.'''
   
   actual = Path(__file__).resolve()
   
   for carpeta in actual.parents:
      if (carpeta / marker).exists():
         return carpeta
   
   raise FileNotFoundError(
      f'No se encontro {marker} en ninguna carpeta superior a {actual}'
   )

PROJECT_ROOT  = _get_root()
DATA_RAW      = PROJECT_ROOT / 'data' / 'raw'
DATA_LABELS   = DATA_RAW / 'labels'
DATA_FEATURES = DATA_RAW / 'features'
SQL_DIR       = PROJECT_ROOT / 'sql'

def get_db_settings(type:Literal['oracle', 
                                 'sql-server']) -> dict[str, str]:
   
   env_exist = load_dotenv()
   
   if not env_exist:
      raise FileNotFoundError(f'No existe .env en la raiz del proyecto...')
   
   if type == 'sql-server':

      VALORES = {
         'KIND':type,
         'DRIVER':os.getenv('CON_BI_DRIVER'),
         'SERVER':os.getenv('SERVER_BI'),
         'PORT':os.getenv('PORT_BI'),
         'DATABASE':os.getenv('DATABASE_BI'),
         'TRUSTED':os.getenv('Trusted_Connection'),
      }
         
      FALTANTES = [k for k,v in VALORES.items() if v is None]
      if FALTANTES:
         raise KeyError(f'Faltan variables en .env: {FALTANTES}')
   else:
      VALORES = {
         'KIND':type, 
      }

   return cast(dict[str,str], VALORES)