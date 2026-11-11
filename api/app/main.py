"""API de formularios de Software Data Lab.

Recibe el formulario de contacto y la lista de espera del curso, los guarda en SQLite
y avisa por correo (SMTP). Pensada para correr detrás de nginx en el mismo dominio:
nginx redirige /api/ a este servicio (ver README del proyecto).
"""

import hashlib
import json
import logging
import os
import re
import smtplib
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from email.message import EmailMessage

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("sdl.api")

DB_PATH = os.getenv("DB_PATH", "/data/sdl.db")
IP_SALT = os.getenv("IP_SALT", "")
RATE_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))
RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "600"))

CORREO_SIMPLE = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")


# --------------------------------------------------------------------------- base de datos
def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def iniciar_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(conectar()) as con, con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS envios (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo    TEXT NOT NULL,
                creado  TEXT NOT NULL,
                ip_hash TEXT NOT NULL,
                clave   TEXT,
                datos   TEXT NOT NULL
            )
            """
        )
        # Evita duplicados en la lista de espera (misma clave = mismo correo).
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_envios_clave ON envios(tipo, clave) WHERE clave IS NOT NULL"
        )


def guardar(tipo: str, ip: str, clave: str | None, datos: dict) -> bool:
    """Guarda un envío. Devuelve False si ya existía (clave repetida)."""
    ip_hash = hashlib.sha256(f"{IP_SALT}{ip}".encode()).hexdigest()[:16]
    with closing(conectar()) as con, con:
        cur = con.execute(
            "INSERT OR IGNORE INTO envios (tipo, creado, ip_hash, clave, datos) VALUES (?, ?, ?, ?, ?)",
            (
                tipo,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ip_hash,
                clave,
                json.dumps(datos, ensure_ascii=False),
            ),
        )
        return cur.rowcount == 1


# --------------------------------------------------------------------------- límite de envíos
_intentos: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def limitar(tipo: str, ip: str) -> None:
    ahora = time.monotonic()
    cola = _intentos[(tipo, ip)]
    while cola and ahora - cola[0] > RATE_WINDOW:
        cola.popleft()
    if len(cola) >= RATE_MAX:
        raise HTTPException(status_code=429, detail="Demasiados intentos. Espera unos minutos e intenta de nuevo.")
    cola.append(ahora)


def ip_cliente(request: Request) -> str:
    # nginx fija X-Real-IP; el contenedor solo escucha en 127.0.0.1, así que el encabezado es confiable.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "desconocida")


# --------------------------------------------------------------------------- correo
def _una_linea(texto: str, maximo: int = 80) -> str:
    return " ".join(texto.split())[:maximo]


def avisar(tipo: str, datos: dict) -> None:
    """Envía el aviso por SMTP. Si falla, el envío ya quedó guardado en la base."""
    host = os.getenv("SMTP_HOST", "")
    destino = os.getenv("MAIL_TO", "")
    if not host or not destino:
        log.warning("SMTP sin configurar: el envío quedó guardado pero no se envió correo")
        return

    msg = EmailMessage()
    remitente = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER", "")
    msg["From"] = remitente
    msg["To"] = destino

    if tipo == "contacto":
        msg["Subject"] = f"[SDL] Nuevo contacto: {_una_linea(datos['nombre'], 60)}"
        if CORREO_SIMPLE.match(datos["contacto"]):
            msg["Reply-To"] = datos["contacto"]
        cuerpo = (
            f"Nombre: {datos['nombre']}\n"
            f"Empresa: {datos['empresa'] or '-'}\n"
            f"Contacto: {datos['contacto']}\n\n"
            f"Qué necesita:\n{datos['necesidad']}\n"
        )
    else:
        msg["Subject"] = "[SDL] Nueva suscripción al curso de fútbol"
        msg["Reply-To"] = datos["email"]
        cuerpo = f"Nombre: {datos['nombre']}\nCorreo: {datos['email']}\n"
    msg.set_content(cuerpo)

    puerto = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER", "")
    clave = os.getenv("SMTP_PASSWORD", "")
    try:
        if os.getenv("SMTP_SECURITY", "starttls") == "ssl":
            servidor: smtplib.SMTP = smtplib.SMTP_SSL(host, puerto, timeout=15)
        else:
            servidor = smtplib.SMTP(host, puerto, timeout=15)
        with servidor:
            if os.getenv("SMTP_SECURITY", "starttls") != "ssl":
                servidor.starttls()
            if usuario:
                servidor.login(usuario, clave)
            servidor.send_message(msg)
    except Exception:  # noqa: BLE001 - no se registran datos personales
        log.exception("No se pudo enviar el correo de aviso (%s)", tipo)


# --------------------------------------------------------------------------- modelos
class Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)
    gotcha: str = Field("", alias="_gotcha", max_length=200)  # campo trampa para bots


class Contacto(Base):
    nombre: str = Field(min_length=1, max_length=120)
    empresa: str = Field("", max_length=160)
    contacto: str = Field(min_length=3, max_length=160)
    necesidad: str = Field(min_length=3, max_length=2000)


class Curso(Base):
    nombre: str = Field(min_length=1, max_length=120)
    email: EmailStr


# --------------------------------------------------------------------------- app
@asynccontextmanager
async def ciclo(_: FastAPI):
    iniciar_db()
    yield


app = FastAPI(title="SDL API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)


@app.exception_handler(RequestValidationError)
async def datos_invalidos(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Revisa los datos e intenta de nuevo."})


def recibir(tipo: str, datos: Base, request: Request, tareas: BackgroundTasks, clave: str | None) -> dict:
    if datos.gotcha:  # un bot llenó el campo trampa: respuesta normal, sin guardar ni avisar
        return {"ok": True}
    ip = ip_cliente(request)
    limitar(tipo, ip)
    payload = datos.model_dump(exclude={"gotcha"})
    if guardar(tipo, ip, clave, payload):
        tareas.add_task(avisar, tipo, payload)
    return {"ok": True}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/contacto")
def contacto(datos: Contacto, request: Request, tareas: BackgroundTasks) -> dict:
    return recibir("contacto", datos, request, tareas, clave=None)


@app.post("/api/curso")
def curso(datos: Curso, request: Request, tareas: BackgroundTasks) -> dict:
    return recibir("curso", datos, request, tareas, clave=datos.email.lower())
