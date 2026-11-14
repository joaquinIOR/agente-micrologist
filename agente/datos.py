"""Base SQLite simulada: flota de Transportes Quillay (empresa ficticia que usa MicroLogist). Se crea y siembra sola la primera vez."""
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DIR = Path(os.environ.get("AGENTE_DATOS", "datos"))

ESQUEMA = """
CREATE TABLE vehiculos (patente TEXT PRIMARY KEY, modelo TEXT, km INTEGER,
                        km_ultima_mantencion INTEGER, estado TEXT);
CREATE TABLE documentos (patente TEXT, tipo TEXT, vence TEXT);
CREATE TABLE ordenes (id INTEGER PRIMARY KEY, patente TEXT, tipo TEXT, motivo TEXT,
                      prioridad TEXT, estado TEXT DEFAULT 'abierta', creada TEXT);
"""


def _sembrar(con):
    hoy = date.today()
    en = lambda dias: (hoy + timedelta(days=dias)).isoformat()  # fechas relativas a hoy
    con.executescript(ESQUEMA)
    con.executemany("INSERT INTO vehiculos VALUES (?,?,?,?,?)", [
        ("KXTR45", "Camión Mercedes-Benz Atego 1726", 148200, 139000, "operativo"),
        ("LJPW12", "Furgón Peugeot Boxer", 62000, 60000, "operativo"),
        ("HRBD78", "Camión Volvo FH 460", 310500, 298000, "en_taller"),
        ("PGSY90", "Camioneta Toyota Hilux", 91500, 80000, "operativo"),
    ])
    con.executemany("INSERT INTO documentos VALUES (?,?,?)", [
        ("KXTR45", "revision_tecnica", en(-5)), ("KXTR45", "permiso_circulacion", en(140)), ("KXTR45", "soap", en(140)),
        ("LJPW12", "revision_tecnica", en(210)), ("LJPW12", "permiso_circulacion", en(140)), ("LJPW12", "soap", en(10)),
        ("HRBD78", "revision_tecnica", en(-20)), ("HRBD78", "permiso_circulacion", en(140)), ("HRBD78", "soap", en(140)),
        ("PGSY90", "revision_tecnica", en(25)), ("PGSY90", "permiso_circulacion", en(140)), ("PGSY90", "soap", en(140)),
    ])
    con.execute("INSERT INTO ordenes (patente, tipo, motivo, prioridad, creada) VALUES (?,?,?,?,?)",
                ("HRBD78", "documento", "Revisión técnica vencida", "alta", en(-18)))
    con.commit()


def conectar():
    DIR.mkdir(parents=True, exist_ok=True)
    ruta = DIR / "flota.db"
    nueva = not ruta.exists()
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    if nueva:
        _sembrar(con)
    return con
