from sqlalchemy.orm import Session
from database import SessionLocal
import models

def list_users():
    db = SessionLocal()
    users = db.query(models.Empleado).all()
    print(f"Total users: {len(users)}")
    for u in users:
        print(f"ID: {u.id}, Name: {u.nombre} {u.apellido}, DNI: {u.documento}, Active: {u.activo}")
    
    db.close()

if __name__ == "__main__":
    list_users()
