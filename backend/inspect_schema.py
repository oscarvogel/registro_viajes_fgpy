from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
import os
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('DATABASE_URL')
if not url:
    print('No DATABASE_URL in .env')
    raise SystemExit(1)
print('Using DB URL:', url)
engine = create_engine(url)
parsed = make_url(url)
schema = parsed.database
q = text("SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'tablero_produccion';")
with engine.connect() as conn:
    rows = conn.execute(q, {'schema': schema}).fetchall()
    if not rows:
        print('Table tablero_produccion not found in schema', schema)
    else:
        print('Columns for tablero_produccion:')
        for r in rows:
            print(f"{r.COLUMN_NAME}\tnullable={r.IS_NULLABLE}\tdefault={r.COLUMN_DEFAULT}\ttype={r.COLUMN_TYPE}")
        print('\nColumns NOT NULL without DEFAULT:')
        for r in rows:
            if r.IS_NULLABLE == 'NO' and r.COLUMN_DEFAULT is None:
                print(f"- {r.COLUMN_NAME} ({r.COLUMN_TYPE})")
