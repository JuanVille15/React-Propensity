'''Carga variables de entorno asi como tambien
   Configuracion en YAML '''

import os
from dotenv import load_dotenv
from typing import Literal,cast

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