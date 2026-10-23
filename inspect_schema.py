import os

import psycopg2

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_NAME = os.getenv("DB_NAME", "PESER")
DB_USER = os.getenv("DB_USER", "peser")
DB_PASS = os.getenv("DB_PASS", "password")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

TABLES = [
    "ps_geo_comune",
    "ps_t_anagrafica_pc",
    "ps_d_stato_piano",
    "ps_d_tipo_piano",
    "ps_d_tipo_delibera",
    "ps_r_piano_comune",
]


def main() -> None:
    """Stampa a video le colonne delle tabelle principali per correggere le query."""

    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
    )
    cur = conn.cursor()

    for table in TABLES:
        print("=" * 60)
        print(f"TABLE {table}")
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            ("public", table),
        )
        rows = cur.fetchall()
        if not rows:
            print("NO COLUMNS FOUND")
        else:
            for name, dtype in rows:
                print(f"- {name} : {dtype}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
