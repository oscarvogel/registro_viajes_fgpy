"""Smoke test para el flujo OCR de combustible contra un backend en produccion.

Uso:
    API_URL=https://viajes.forestalparaguay.com/api AUTH_TOKEN=eyJ... \\
        python backend/scripts/smoke_fuel_image.py \\
        --ticket /path/to/ticket_petrobras.jpg \\
        --remito /path/to/remito_0007222.jpg

Verifica que el backend:
1. Devuelve un upload_token al analyze de cada tipo.
2. Acepta el confirm con el upload_token.
3. Devuelve movimiento_id e imagen_id.
4. Sirve el blob de la imagen confirmada.

Requiere una sesion valida (JWT) con un chofer que tenga
equipo/unidad configurados en Ajustes. El token se pasa via AUTH_TOKEN.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests


def analyze(api_url: str, token: str, image: Path, tipo: str) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}/fuel-image/analyze"
    with image.open("rb") as f:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (image.name, f, "image/jpeg")},
            data={"tipo": tipo},
            timeout=120,
        )
    response.raise_for_status()
    return response.json()


def confirm_ticket(api_url: str, token: str, payload: dict) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}/fuel-image/confirm/ticket"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def confirm_remito(api_url: str, token: str, payload: dict) -> dict[str, Any]:
    url = f"{api_url.rstrip('/')}/fuel-image/confirm/remito-interno"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_blob(api_url: str, token: str, image_id: int) -> int:
    url = f"{api_url.rstrip('/')}/fuel-image/{image_id}/blob"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return len(response.content)


def verify_ticket(api_url: str, token: str, image: Path) -> dict[str, Any]:
    print(f"\n=== Ticket: {image.name} ===")
    analysis = analyze(api_url, token, image, "ticket")
    print(f"  upload_token: {analysis['upload_token'][:20]}...")
    proposal = analysis["proposal"]
    print(f"  fecha:        {proposal.get('fecha')}")
    print(f"  litros:       {proposal.get('litros')}")
    print(f"  km_hora:      {proposal.get('km_hora')}")
    print(f"  remito:       {proposal.get('remito')}")
    print(f"  ruc:          {proposal.get('ruc')}")
    print(f"  emisor:       {proposal.get('razon_social_emisor')}")
    print(f"  producto:     {proposal.get('producto')}")
    print(f"  proveedor_id: {proposal.get('proveedor_id')}")
    if proposal.get("warnings"):
        print(f"  warnings:     {proposal['warnings']}")
    return analysis


def verify_remito(api_url: str, token: str, image: Path) -> dict[str, Any]:
    print(f"\n=== Remito interno: {image.name} ===")
    analysis = analyze(api_url, token, image, "remito_interno")
    print(f"  upload_token: {analysis['upload_token'][:20]}...")
    proposal = analysis["proposal"]
    print(f"  fecha:        {proposal.get('fecha')}")
    print(f"  litros:       {proposal.get('litros')}")
    print(f"  kilometros:   {proposal.get('kilometros')}")
    print(f"  remito:       {proposal.get('remito')}")
    print(f"  lugar:        {proposal.get('lugar_carga')}")
    print(f"  firmante:     {proposal.get('firmante')}")
    print(f"  tipo:         {proposal.get('tipo')}")
    print(f"  proveedor:    {proposal.get('proveedor_nombre')} (id={proposal.get('proveedor_id')})")
    if proposal.get("warnings"):
        print(f"  warnings:     {proposal['warnings']}")
    return analysis


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test del flujo OCR de combustible.")
    parser.add_argument("--api-url", required=True, help="URL base del backend (ej. https://.../api)")
    parser.add_argument("--token", required=True, help="JWT de un chofer autenticado")
    parser.add_argument("--ticket", type=Path, help="Path a la foto del ticket de estacion")
    parser.add_argument("--remito", type=Path, help="Path a la foto del remito interno")
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Solo analizar, no confirmar. Util para validar el OCR sin escribir en la base.",
    )
    args = parser.parse_args()

    if not args.ticket and not args.remito:
        print("ERROR: pasar al menos --ticket o --remito", file=sys.stderr)
        return 2

    try:
        if args.ticket:
            analysis = verify_ticket(args.api_url, args.token, args.ticket)
            if not args.skip_confirm:
                proposal = analysis["proposal"]
                payload = {
                    "upload_token": analysis["upload_token"],
                    "fecha_carga": proposal["fecha"],
                    "litros": float(proposal["litros"]),
                    "km_hora": int(proposal["km_hora"]),
                    "equipo_id": int(input("  equipo_id (de Ajustes): ")),
                    "paniol_id": int(input("  paniol_id (catalogo): ")),
                    "proveedor_id": proposal["proveedor_id"],
                    "remito": proposal["remito"],
                    "observaciones": "smoke script",
                }
                if payload["proveedor_id"] is None:
                    print("  WARN: proveedor_id nulo, el backend creara uno inactivo en BD")
                result = confirm_ticket(args.api_url, args.token, payload)
                print(f"  confirm OK: movimiento_id={result['movimiento_id']}, imagen_id={result['imagen_id']}")
                size = fetch_blob(args.api_url, args.token, result["imagen_id"])
                print(f"  blob size: {size} bytes")

        if args.remito:
            analysis = verify_remito(args.api_url, args.token, args.remito)
            if not args.skip_confirm:
                proposal = analysis["proposal"]
                payload = {
                    "upload_token": analysis["upload_token"],
                    "fecha_carga": proposal["fecha"],
                    "litros": float(proposal["litros"]),
                    "km_hora": float(proposal["kilometros"] or 0),
                    "equipo_id": int(input("  equipo_id (de Ajustes): ")),
                    "paniol_id": int(input("  paniol_id (catalogo): ")),
                    "remito": proposal["remito"],
                    "observaciones": "smoke script",
                }
                result = confirm_remito(args.api_url, args.token, payload)
                print(f"  confirm OK: movimiento_id={result['movimiento_id']}, imagen_id={result['imagen_id']}")
                size = fetch_blob(args.api_url, args.token, result["imagen_id"])
                print(f"  blob size: {size} bytes")

    except requests.HTTPError as e:
        print(f"\nERROR HTTP {e.response.status_code}: {e.response.text}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
