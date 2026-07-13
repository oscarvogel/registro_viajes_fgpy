from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    # Verificar si hay datos en movimientocombustible con proveedor_id
    query = text("SELECT COUNT(*) FROM movimientocombustible WHERE proveedor_id IS NOT NULL")
    count = db.execute(query).scalar()
    print(f"Registros en movimientocombustible con proveedor_id: {count}")
    
    # Verificar si hay datos en tablero_produccion con proveedor_id que no existen en proveedores
    query = text("""
        SELECT COUNT(*) 
        FROM tablero_produccion t
        WHERE t.proveedor_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM proveedor p WHERE p.id = t.proveedor_id)
    """)
    count = db.execute(query).scalar()
    print(f"Registros en tablero_produccion con proveedor_id inválido: {count}")
    
    # Ver ejemplos de proveedor_id usados
    query = text("""
        SELECT DISTINCT proveedor_id 
        FROM tablero_produccion 
        WHERE proveedor_id IS NOT NULL
        ORDER BY proveedor_id
        LIMIT 10
    """)
    result = db.execute(query).fetchall()
    print(f"\nProveedores usados en tablero_produccion:")
    for row in result:
        # Verificar si existe en proveedor
        check = db.execute(text("SELECT razon_social FROM proveedor WHERE id = :id"), {"id": row[0]}).fetchone()
        status = f"✓ {check[0]}" if check else "✗ NO EXISTE"
        print(f"  ID {row[0]}: {status}")
        
except Exception as e:
    print(f'Error: {e}')
finally:
    db.close()
