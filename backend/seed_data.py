from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from datetime import date

# Create tables
models.Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()

    # Check if data exists
    if db.query(models.Empleado).first():
        print("Data already exists. Skipping seed.")
        db.close()
        return

    print("Seeding data...")

    # Empleados
    emp1 = models.Empleado(
        nombre="Juan", 
        apellido="Perez", 
        email="juan@example.com", 
        documento="12345678", 
        fecha_contratacion=date.today(),
        activo=True,
        porcentaje=0.20
    )
    emp2 = models.Empleado(
        nombre="Carlos", 
        apellido="Gomez", 
        email="carlos@example.com", 
        documento="87654321", 
        fecha_contratacion=date.today(),
        activo=True,
        porcentaje=0.20
    )

    # Proveedores
    prov1 = models.Proveedor(
        razon_social="POMERA", 
        cuit="30-11111111-1",
        activo=True
    )
    prov2 = models.Proveedor(
        razon_social="FELBER FORESTAL", 
        cuit="30-22222222-2",
        activo=True
    )

    # Equipos (Camiones)
    eq1 = models.Equipo(
        descripcion="Scania 113",
        patente="AA123BB",
        nro_chasis="123456",
        nro_motor="654321",
        tipo_movil_id=1,
        movil_asociado=0,
        activo=True,
        ult_hr_km=100000.00
    )
    eq2 = models.Equipo(
        descripcion="Volvo 440",
        patente="CC456DD",
        nro_chasis="111111",
        nro_motor="222222",
        tipo_movil_id=1,
        movil_asociado=0,
        activo=True,
        ult_hr_km=50000.00
    )

    db.add_all([emp1, emp2, prov1, prov2, eq1, eq2])
    db.commit()
    print("Seeding complete!")
    db.close()

if __name__ == "__main__":
    seed()
