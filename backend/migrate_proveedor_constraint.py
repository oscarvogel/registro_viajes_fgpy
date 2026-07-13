from database import engine
from sqlalchemy import text

print("=== Migrando constraint de proveedor_id en tablero_produccion ===\n")

try:
    with engine.begin() as conn:
        # 1. Eliminar el constraint antiguo
        print("1. Eliminando constraint antiguo...")
        conn.execute(text("""
            ALTER TABLE tablero_produccion 
            DROP FOREIGN KEY fk_tablero_produccion_proveedor_id_refs_proveedores
        """))
        print("   ✓ Constraint eliminado\n")
        
        # 2. Crear el nuevo constraint
        print("2. Creando nuevo constraint...")
        conn.execute(text("""
            ALTER TABLE tablero_produccion 
            ADD CONSTRAINT fk_tablero_produccion_proveedor_id_refs_proveedor 
            FOREIGN KEY (proveedor_id) REFERENCES proveedor(id) 
            ON DELETE SET NULL 
            ON UPDATE CASCADE
        """))
        print("   ✓ Nuevo constraint creado\n")
        
        # 3. Verificar
        print("3. Verificando constraint...")
        result = conn.execute(text("""
            SELECT 
                CONSTRAINT_NAME,
                REFERENCED_TABLE_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = 'fgpy'
              AND TABLE_NAME = 'tablero_produccion'
              AND COLUMN_NAME = 'proveedor_id'
              AND REFERENCED_TABLE_NAME IS NOT NULL
        """)).fetchone()
        
        if result:
            print(f"   ✓ Constraint: {result[0]}")
            print(f"   ✓ Referencia: {result[1]}.id")
            print("\n✅ Migración completada exitosamente!")
        else:
            print("   ⚠ No se encontró el constraint")
            
except Exception as e:
    print(f"\n❌ Error durante la migración: {e}")
    print("\nPuedes ejecutar manualmente:")
    print("  ALTER TABLE tablero_produccion DROP FOREIGN KEY fk_tablero_produccion_proveedor_id_refs_proveedores;")
    print("  ALTER TABLE tablero_produccion ADD CONSTRAINT fk_tablero_produccion_proveedor_id_refs_proveedor")
    print("    FOREIGN KEY (proveedor_id) REFERENCES proveedor(id) ON DELETE SET NULL ON UPDATE CASCADE;")
