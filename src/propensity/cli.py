'''Interfaz de linea de comandos del proyecto.

Solo traduce lo que se escribe en la terminal a llamadas de funciones.
Los imports del pipeline van dentro de cada rama para que `--help` no
cargue pandas, sqlalchemy ni los drivers de base de datos.
'''
import argparse

FUENTES = [
    'labels',
    'demografica',
    'v_360',
    'cantidad_productos',
    'fac_rec_gecc',
    'pagos',
    'fac_rec_coomeva',
    'fac_rec_estatu',
    'gestiones',
]


def main() -> None:

    parser = argparse.ArgumentParser(
        prog='propensity',
        description='Modelo de propension a la reactivacion - Coomeva',
    )
    sub = parser.add_subparsers(dest='comando', required=True)

    # --- extract --- #

    p_ext = sub.add_parser(
        'extract',
        help='Extrae una fuente (o todas) y la persiste en data/raw/',
    )
    p_ext.add_argument(
        '--fuente',
        choices=FUENTES + ['all'],
        required=True,
        help="'all' extrae labels y luego todas las features",
    )
    p_ext.add_argument(
        '--periodo',
        type=int,
        help='Ultimo periodo a etiquetar, YYYYMM (solo labels / all)',
    )
    p_ext.add_argument(
        '--n-periodos',
        type=int,
        help='Cuantos periodos etiquetar (solo labels / all)',
    )

    args = parser.parse_args()

    if args.comando == 'extract':
        from propensity.pipeline import run_extract

        run_extract(
            fuente=args.fuente,
            periodo=args.periodo,
            n_periodos=args.n_periodos,
        )


if __name__ == '__main__':
    main()
