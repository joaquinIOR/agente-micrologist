"""Memoria de largo plazo en Chroma: colecciones 'politicas' y 'recuerdos'."""
import uuid
from datetime import date

import chromadb

from .datos import DIR

# Políticas simuladas de MicroLogist.
POLITICAS = [
    "Un vehículo con revisión técnica, permiso de circulación o SOAP vencido no puede circular: "
    "debe quedar en estado 'bloqueado' y se crea una orden de tipo documento con prioridad alta.",
    "Un documento que vence en 15 días o menos genera una orden de tipo documento con prioridad media; "
    "si vence entre 16 y 30 días, prioridad baja. El vehículo sigue operativo.",
    "La mantención preventiva corresponde cada 10.000 km desde la última mantención. "
    "Si se supera ese kilometraje se crea una orden de tipo mantencion con prioridad media.",
    "Un vehículo que está en taller no se bloquea ni se le cambia el estado hasta que el taller lo libere, "
    "y no se duplica una orden que ya está abierta para el mismo vehículo y tipo.",
    "Cuando hay varias tareas pendientes se atienden primero los documentos vencidos, "
    "después los documentos próximos a vencer y al final las mantenciones preventivas.",
]

_cliente = None


def _coleccion(nombre):
    # shortcut: embeddings en inglés; usar uno multilingüe si crecen las políticas
    global _cliente
    if _cliente is None:
        _cliente = chromadb.PersistentClient(path=str(DIR / "chroma"))
    col = _cliente.get_or_create_collection(nombre)
    if nombre == "politicas" and col.count() == 0:
        col.add(ids=[f"pol-{i}" for i in range(len(POLITICAS))], documents=POLITICAS)
    return col


def buscar(nombre, consulta, k=3):
    col = _coleccion(nombre)
    if col.count() == 0:
        return []
    return col.query(query_texts=[consulta], n_results=min(k, col.count()))["documents"][0]


def guardar(texto):
    _coleccion("recuerdos").add(ids=[uuid.uuid4().hex], documents=[f"[{date.today().isoformat()}] {texto}"])
