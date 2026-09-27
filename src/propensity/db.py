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

def build_gcc_con(config:dict[str,str]) -> Engine:
    
    c_url = URL.create(
            "oracle+oracledb",
            username=config['USER'],
            password=config['PASSWORD'],
            host=config['SERVER'],
            port=int(config['PORT']),
            query={"service_name": config['SERVICE']},
        )

    con_gcc = create_engine(url=c_url)
    
    return con_gcc


if __name__ == '__main__':
    gcc_engine = build_gcc_con(get_db_settings('oracle'))
    with gcc_engine.connect() as conn:
        print(f'Conexion DWH GCC establecida✅')