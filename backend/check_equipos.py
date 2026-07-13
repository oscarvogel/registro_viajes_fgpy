from sqlalchemy.orm import Session
from database import SessionLocal
import models
from sqlalchemy import text

def check_equipos():
    db = SessionLocal()
    # Check what columns actually exist/values
    equipos = db.query(models.Equipo).limit(10).all()
    print(f"Checking first 10 equipos...")
    for e in equipos:
        print(f"ID: {e.id}, Patente: {e.patente}, Desc: {e.descripcion}, tipo_movil_id: {e.tipo_movil_id} (Type: {type(e.tipo_movil_id)})")
    
    # Check count of type 4
    count_4 = db.query(models.Equipo).filter(models.Equipo.tipo_movil_id == 4).count()
    print(f"Total count of tipo_movil_id=4: {count_4}")

    db.close()

if __name__ == "__main__":
    check_equipos()
