"""Schema and convention tests for the combustible image evidence flow."""
from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import models


class CombustibleImagenModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _make_movimiento(self, db, equipo_id=1, paniol_id=None, proveedor_id=1):
        mov = models.MovimientoCombustible(
            fecha=datetime(2026, 7, 31).date(),
            tipo_combustible_id=1,
            equipo_id=equipo_id,
            km_hora=12345.0,
            precio_litro=0.0,
            ingreso=100.0,
            egreso=0.0,
            unidad_negocio_id=1,
            paniol_id=paniol_id,
            remito="0000001",
            idtabla=0,
            tabla="movimientocombustible",
            usuario="1",
            fecha_grabacion=datetime(2026, 7, 31, 12, 0),
            observaciones="",
            proveedor_id=proveedor_id,
            periodo="202607",
            remito2="0",
        )
        db.add(mov)
        db.commit()
        db.refresh(mov)
        return mov

    def test_table_is_created_with_expected_columns(self):
        inspector = models.Base.metadata
        table = inspector.tables["combustible_imagenes"]
        names = {col.name for col in table.columns}
        self.assertEqual(
            names,
            {
                "id", "movimiento_id", "storage_path", "original_name",
                "mime_type", "sha256", "token_hash", "created_at", "expires_at",
            },
        )
        for col in ("movimiento_id", "storage_path", "original_name",
                    "mime_type", "sha256", "token_hash",
                    "created_at", "expires_at"):
            self.assertFalse(table.columns[col].nullable, f"{col} must be NOT NULL")

    def test_unique_index_on_token_hash(self):
        from sqlalchemy import UniqueConstraint
        table = models.Base.metadata.tables["combustible_imagenes"]
        unique_columns = set()
        for index in table.indexes:
            if index.unique:
                unique_columns.add(tuple(c.name for c in index.columns))
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                unique_columns.add(tuple(c.name for c in constraint.columns))
        self.assertIn(("token_hash",), unique_columns)

    def test_index_on_expires_at_and_movimiento_id(self):
        table = models.Base.metadata.tables["combustible_imagenes"]
        column_index_pairs = set()
        for index in table.indexes:
            for col in index.columns:
                column_index_pairs.add(col.name)
        self.assertIn("expires_at", column_index_pairs)
        self.assertIn("movimiento_id", column_index_pairs)
        self.assertIn("sha256", column_index_pairs)

    def test_relationship_round_trip(self):
        db = self.Session()
        mov = self._make_movimiento(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        token = "test-token-1"
        evidence = models.CombustibleImagen(
            movimiento_id=mov.id,
            storage_path="confirmed/20260731/abcd.jpg",
            original_name="ticket.jpg",
            mime_type="image/jpeg",
            sha256=hashlib.sha256(b"ticket").hexdigest(),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=now,
            expires_at=now + timedelta(days=60),
        )
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
        self.assertEqual(evidence.movimiento_id, mov.id)
        self.assertEqual(evidence.movimiento.id, mov.id)
        self.assertEqual(len(mov.imagenes), 1)
        self.assertIs(mov.imagenes[0], evidence)

    def test_token_hash_unique_constraint(self):
        db = self.Session()
        mov = self._make_movimiento(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        token = "test-token-dup"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        for offset in range(2):
            ev = models.CombustibleImagen(
                movimiento_id=mov.id,
                storage_path=f"confirmed/20260731/{offset}.jpg",
                original_name="ticket.jpg",
                mime_type="image/jpeg",
                sha256=hashlib.sha256(f"img-{offset}".encode()).hexdigest(),
                token_hash=token_hash,
                created_at=now,
                expires_at=now + timedelta(days=60),
            )
            db.add(ev)
            db.commit() if offset == 0 else None
        with self.assertRaises(IntegrityError):
            db.commit()
        db.rollback()

    def test_fk_to_movimientocombustible(self):
        table = models.Base.metadata.tables["combustible_imagenes"]
        fk_targets = set()
        for constraint in table.foreign_key_constraints:
            for element in constraint.elements:
                fk_targets.add((element.parent.name, element.target_fullname.split(".")[0]))
        self.assertIn(("movimiento_id", "movimientocombustible"), fk_targets)


class InternalProviderConventionTests(unittest.TestCase):
    """Documenta la convencion del proyecto: existe un proveedor
    INTERNO FORESTAL PARAGUAY en la tabla `proveedor`, cuyo id lo asigna
    la DB y se resuelve por nombre (no hardcoded).

    Esta convencion la usa fuel_image_service (ver issue #17).
    """

    def _make_db(self):
        engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        return Session()

    def test_helper_returns_id_when_internal_provider_exists(self):
        db = self._make_db()
        db.add(models.Proveedor(razon_social="INTERNO FORESTAL PARAGUAY", activo=True))
        db.add(models.Proveedor(razon_social="LIDER EXPRESS", activo=True))
        db.commit()
        interno_id = models.get_internal_provider_id(db)
        self.assertIsNotNone(interno_id)
        resolved = db.query(models.Proveedor).filter(models.Proveedor.id == interno_id).first()
        self.assertIsNotNone(resolved)
        self.assertIn("INTERNO", (resolved.razon_social or "").upper())

    def test_helper_is_case_insensitive(self):
        db = self._make_db()
        db.add(models.Proveedor(razon_social="interno forestal paraguay", activo=True))
        db.commit()
        interno_id = models.get_internal_provider_id(db)
        self.assertIsNotNone(interno_id)

    def test_helper_raises_when_internal_provider_missing(self):
        db = self._make_db()
        db.add(models.Proveedor(razon_social="LIDER EXPRESS", activo=True))
        db.add(models.Proveedor(razon_social="PETROBRAS", activo=True))
        db.commit()
        with self.assertRaises(RuntimeError) as ctx:
            models.get_internal_provider_id(db)
        self.assertIn("INTERNO", str(ctx.exception))
        self.assertIn("no encontrado", str(ctx.exception).lower())

    def test_helper_raises_when_multiple_internal_providers(self):
        db = self._make_db()
        db.add(models.Proveedor(razon_social="INTERNO FORESTAL PARAGUAY", activo=True))
        db.add(models.Proveedor(razon_social="INTERNO TRANSPORTE", activo=True))
        db.commit()
        with self.assertRaises(RuntimeError) as ctx:
            models.get_internal_provider_id(db)
        self.assertIn("Multiples", str(ctx.exception))

    def test_does_not_pick_id_one_with_generico_name(self):
        """id=1 historico (PROVEEDOR GENERICO) no debe ser tratado como INTERNO."""
        db = self._make_db()
        db.add(models.Proveedor(id=1, razon_social="PROVEEDOR GENERICO", activo=True))
        db.commit()
        with self.assertRaises(RuntimeError):
            models.get_internal_provider_id(db)

    def test_constant_razon_social_is_documented(self):
        self.assertEqual(models.INTERNAL_PROVIDER_RAZON_SOCIAL, "INTERNO FORESTAL PARAGUAY")


if __name__ == "__main__":
    unittest.main()
