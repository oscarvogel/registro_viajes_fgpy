from database import SessionLocal, engine
from sqlalchemy import text

db = SessionLocal()

try:
    # Buscar todas las foreign keys que apuntan a proveedores
    query = text("""
        SELECT 
            CONSTRAINT_NAME,
            TABLE_NAME,
            COLUMN_NAME,
            REFERENCED_TABLE_NAME,
            REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = 'fgpy'
          AND REFERENCED_TABLE_NAME IN ('proveedor', 'proveedores')
        ORDER BY TABLE_NAME, COLUMN_NAME
    """)
    
    result = db.execute(query).fetchall()
    
    print("\n=== Foreign Keys relacionadas con proveedor/proveedores ===\n")
    for row in result:
        print(f"Tabla: {row[1]}")
        print(f"  Columna: {row[2]}")
        print(f"  Referencias: {row[3]}.{row[4]}")
        print(f"  Constraint: {row[0]}")
        print()
        
except Exception as e:
    print(f'Error: {e}')
finally:
    db.close()
