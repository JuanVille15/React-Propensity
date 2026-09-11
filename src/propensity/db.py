'''Conexion a bases de datos'''
from sqlalchemy import Engine,create_engine
from sqlalchemy.engine import URL
from propensity.config import get_db_settings

def build_bi_con(config:dict[str,str]) -> Engine:
    
    c_url = URL.create(
            "mssql+pyodbc",
            host=config['SERVER'],
            port=int(config['PORT']),
            database=config['DATABASE'],
            query={'driver':config['DRIVER'],'trusted_connection':config['TRUSTED']}
    )
    
    con_bi = create_engine(url=c_url)
    
    return con_bi


if __name__ == '__main__':
    bi_engine = build_bi_con(get_db_settings('sql-server'))
    with bi_engine.connect() as conn:
        print(f'Conexion DWH BI establecida✅')