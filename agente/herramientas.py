"""Herramientas de consulta y escritura del agente."""
import json
import re
import unicodedata
from datetime import date

from langchain_core.tools import tool

from . import memoria
from .datos import DIR, conectar

ESTADOS = {"operativo", "bloqueado", "en_taller"}
PRIORIDADES = {"alta", "media", "baja"}
TIPOS = {"documento", "mantencion"}


def _json(filas):
    return json.dumps([dict(f) for f in filas], ensure_ascii=False)


@tool
def consultar_vehiculo(patente: str) -> str:
    """Consulta la ficha de un vehículo: modelo, kilometraje, estado, documentos con su vencimiento y órdenes abiertas."""
    con = conectar()
    v = con.execute("SELECT * FROM vehiculos WHERE patente = ?", (patente.upper(),)).fetchone()
    if not v:
        return f"No existe un vehículo con patente {patente}."
    docs = con.execute("SELECT tipo, vence FROM documentos WHERE patente = ?", (v["patente"],)).fetchall()
    ordenes = con.execute("SELECT id, tipo, motivo, prioridad FROM ordenes WHERE patente = ? AND estado = 'abierta'",
                          (v["patente"],)).fetchall()
    return json.dumps({**dict(v), "km_desde_mantencion": v["km"] - v["km_ultima_mantencion"],
                       "documentos": [dict(d) for d in docs], "ordenes_abiertas": [dict(o) for o in ordenes]},
                      ensure_ascii=False)


@tool
def revisar_flota(dias: int = 30) -> str:
    """Lista los pendientes de toda la flota: documentos vencidos o que vencen dentro de `dias` días
    (dias_restantes negativo = vencido) y vehículos que superaron los 10.000 km desde su última mantención."""
    con = conectar()
    docs = con.execute(
        """SELECT d.patente, v.estado, d.tipo, d.vence,
                  CAST(julianday(d.vence) - julianday(?) AS INTEGER) AS dias_restantes
           FROM documentos d JOIN vehiculos v USING (patente)
           WHERE dias_restantes <= ? ORDER BY dias_restantes""", (date.today().isoformat(), dias)).fetchall()
    mant = con.execute("""SELECT patente, estado, km - km_ultima_mantencion AS km_desde_mantencion
                          FROM vehiculos WHERE km - km_ultima_mantencion > 10000""").fetchall()
    return json.dumps({"documentos": [dict(d) for d in docs], "mantenciones_atrasadas": [dict(m) for m in mant]},
                      ensure_ascii=False)


@tool
def buscar_politica(consulta: str) -> str:
    """Busca por significado en las políticas internas de la empresa (qué hacer ante documentos vencidos,
    prioridades, mantención, vehículos en taller). Úsala antes de decidir una acción."""
    return "\n".join(f"- {p}" for p in memoria.buscar("politicas", consulta))


@tool
def crear_orden(patente: str, tipo: str, motivo: str, prioridad: str) -> str:
    """Crea una orden de trabajo. tipo: 'documento' o 'mantencion'. prioridad: 'alta', 'media' o 'baja'."""
    patente = patente.upper()
    if tipo not in TIPOS or prioridad not in PRIORIDADES:
        return f"Rechazada: tipo debe ser uno de {sorted(TIPOS)} y prioridad uno de {sorted(PRIORIDADES)}."
    con = conectar()
    if not con.execute("SELECT 1 FROM vehiculos WHERE patente = ?", (patente,)).fetchone():
        return f"Rechazada: no existe un vehículo con patente {patente}."
    abierta = con.execute("SELECT id FROM ordenes WHERE patente = ? AND tipo = ? AND estado = 'abierta'",
                          (patente, tipo)).fetchone()
    if abierta:
        return f"Rechazada: {patente} ya tiene la orden abierta #{abierta['id']} de tipo {tipo}. No se duplica."
    cur = con.execute("INSERT INTO ordenes (patente, tipo, motivo, prioridad, creada) VALUES (?,?,?,?,?)",
                      (patente, tipo, motivo, prioridad, date.today().isoformat()))
    con.commit()
    return f"Orden #{cur.lastrowid} creada para {patente} ({tipo}, prioridad {prioridad})."


@tool
def cambiar_estado(patente: str, estado: str) -> str:
    """Cambia el estado de un vehículo a 'operativo', 'bloqueado' o 'en_taller'."""
    patente = patente.upper()
    if estado not in ESTADOS:
        return f"Rechazado: estado debe ser uno de {sorted(ESTADOS)}."
    con = conectar()
    v = con.execute("SELECT estado FROM vehiculos WHERE patente = ?", (patente,)).fetchone()
    if not v:
        return f"Rechazado: no existe un vehículo con patente {patente}."
    if v["estado"] == "en_taller" and estado == "bloqueado":
        return f"Rechazado: {patente} está en taller; no se bloquea hasta que el taller lo libere."
    con.execute("UPDATE vehiculos SET estado = ? WHERE patente = ?", (estado, patente))
    con.commit()
    return f"{patente} pasó de '{v['estado']}' a '{estado}'."


@tool
def redactar_informe(titulo: str, contenido_markdown: str) -> str:
    """Escribe un informe en Markdown en la carpeta de informes y devuelve la ruta del archivo."""
    sin_tildes = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-") or "informe"  # evita salir de la carpeta
    ruta = DIR / "informes" / f"{date.today().isoformat()}-{nombre}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"# {titulo}\n\n{contenido_markdown}\n", encoding="utf-8")
    return f"Informe guardado en {ruta}"


@tool
def guardar_recuerdo(texto: str) -> str:
    """Guarda en la memoria de largo plazo un hecho, decisión o preferencia del usuario que deba
    recordarse en conversaciones futuras (ej.: 'el taller no recibe vehículos los sábados')."""
    memoria.guardar(texto)
    return "Recuerdo guardado."


HERRAMIENTAS = [consultar_vehiculo, revisar_flota, buscar_politica, crear_orden, cambiar_estado,
                redactar_informe, guardar_recuerdo]
