from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    count_proveedores = db.execute(text('SELECT COUNT(*) FROM proveedores')).scalar()
    print(f'Tabla proveedores: {count_proveedores} registros')
    
    count_proveedor = db.execute(text('SELECT COUNT(*) FROM proveedor')).scalar()
    print(f'Tabla proveedor: {count_proveedor} registros')
    
    print('\n--- Primeros 5 de proveedores ---')
    result = db.execute(text('SELECT id, razon_social FROM proveedores LIMIT 5')).fetchall()
    for row in result:
        print(f'ID: {row[0]}, Razón Social: {row[1]}')
    
    print('\n--- Primeros 5 de proveedor ---')
    result = db.execute(text('SELECT id, razon_social FROM proveedor LIMIT 5')).fetchall()
    for row in result:
        print(f'ID: {row[0]}, Razón Social: {row[1]}')
        
except Exception as e:
    print(f'Error: {e}')
finally:
    db.close()
