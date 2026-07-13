from sqlalchemy.orm import Session
from database import SessionLocal
import models

def clean_dnis():
    session = SessionLocal()
    users = session.query(models.Empleado).all()
    count = 0
    for u in users:
        if u.documento:
            original = u.documento
            # Remove dots, spaces, tabs, newlines
            cleaned = "".join(c for c in original if c.isdigit())
            
            if original != cleaned:
                print(f"Updating ID {u.id}: '{original}' -> '{cleaned}'")
                u.documento = cleaned
                count += 1
    
    if count > 0:
        session.commit()
        print(f"Updated {count} records.")
    else:
        print("No records needed updating.")
    
    session.close()

if __name__ == "__main__":
    clean_dnis()
