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
from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

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
    elif tipo == "diagnostico":
        r = datos["resultado"]
        msg["Subject"] = f"[SDL] Diagnóstico {r['total']}/100 ({r['nivel']}): {_una_linea(datos['empresa'], 50)}"
        if CORREO_SIMPLE.match(datos["contacto"]):
            msg["Reply-To"] = datos["contacto"]
        lineas_dim = "\n".join(
            f"  - {BRECHA[i][0]}: {p}/100 ({nivel_de(p)})" for i, p in r["dimensiones"].items()
        )
        lineas_equipo = "\n".join(f"  - {k}: {v}" for k, v in datos["equipo"].items()) or "  -"
        servicios = ", ".join(SERVICIOS[s] for s in datos["servicios"]) or "-"
        cuerpo = (
            f"Nombre: {datos['nombre']}\n"
            f"Empresa: {datos['empresa']}\n"
            f"Contacto: {datos['contacto']}\n"
            f"Sector: {datos['sector'] or '-'}\n"
            f"Tamaño: {datos['tamano'] or '-'}\n\n"
            f"Brecha digital: {r['total']}/100 ({r['nivel']})\n{lineas_dim}\n\n"
            f"Gestión del equipo:\n{lineas_equipo}\n\n"
            f"Qué frena al equipo:\n{datos['friccion']}\n\n"
            f"Servicios de interés: {servicios}\n"
            f"Urgencia: {datos['urgencia'] or '-'}\n\n"
            f"Qué quiere lograr:\n{datos['objetivo'] or '-'}\n"
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


# Ids del diagnóstico de brecha digital: deben coincidir con src/data/diagnostico.json.
BRECHA: dict[str, tuple[str, tuple[str, ...]]] = {
    "procesos": ("Procesos", ("proc_definidos", "proc_manual")),
    "herramientas": ("Herramientas y sistemas", ("herr_info", "herr_buscar")),
    "datos": ("Datos e indicadores", ("dat_cifras", "dat_decisiones")),
    "atencion": ("Atención y comunicación", ("ate_solicitudes", "ate_recordatorios")),
    "seguridad": ("Seguridad y respaldo", ("seg_copias", "seg_accesos")),
}
IDS_BRECHA = {p for _, preguntas in BRECHA.values() for p in preguntas}
SERVICIOS = {
    "software": "Software a la medida",
    "datos": "Tableros y analítica de datos",
    "automatizacion": "Automatización con WhatsApp e IA",
    "soporte": "Auditoría, mantenimiento y soporte",
    "formacion": "Formación para equipos",
}
IDS_EQUIPO = ("asignacion", "seguimiento", "comunicacion")
NIVELES = ((25, "Inicial"), (50, "En desarrollo"), (75, "Intermedio"), (100, "Avanzado"))


def porcentaje(valores: list[int]) -> int:
    return round(sum(valores) / (len(valores) * 3) * 100) if valores else 0


def nivel_de(puntos: int) -> str:
    return next(nombre for tope, nombre in NIVELES if puntos <= tope)


class Diagnostico(Base):
    nombre: str = Field(min_length=1, max_length=120)
    empresa: str = Field(min_length=1, max_length=160)
    contacto: str = Field(min_length=3, max_length=160)
    sector: str = Field("", max_length=80)
    tamano: str = Field("", max_length=80)
    brecha: dict[str, int]
    equipo: dict[str, str] = Field(default_factory=dict)
    friccion: str = Field(min_length=3, max_length=2000)
    servicios: list[str] = Field(default_factory=list, max_length=len(SERVICIOS))
    urgencia: str = Field("", max_length=80)
    objetivo: str = Field("", max_length=2000)

    @field_validator("brecha")
    @classmethod
    def _brecha(cls, v: dict[str, int]) -> dict[str, int]:
        if set(v) != IDS_BRECHA or any(not 0 <= n <= 3 for n in v.values()):
            raise ValueError("brecha incompleta o fuera de rango")
        return v

    @field_validator("equipo")
    @classmethod
    def _equipo(cls, v: dict[str, str]) -> dict[str, str]:
        return {k: _una_linea(t, 120) for k, t in v.items() if k in IDS_EQUIPO}

    @field_validator("servicios")
    @classmethod
    def _servicios(cls, v: list[str]) -> list[str]:
        if any(s not in SERVICIOS for s in v):
            raise ValueError("servicio desconocido")
        return list(dict.fromkeys(v))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resultado(self) -> dict:
        """Puntaje 0-100 por dimensión y total, calculado aquí (no se confía en el navegador)."""
        dimensiones = {
            id_: porcentaje([self.brecha[p] for p in preguntas]) for id_, (_, preguntas) in BRECHA.items()
        }
        total = porcentaje(list(self.brecha.values()))
        return {"total": total, "nivel": nivel_de(total), "dimensiones": dimensiones}


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


@app.post("/api/diagnostico")
def diagnostico(datos: Diagnostico, request: Request, tareas: BackgroundTasks) -> dict:
    return recibir("diagnostico", datos, request, tareas, clave=None)


@app.post("/api/curso")
def curso(datos: Curso, request: Request, tareas: BackgroundTasks) -> dict:
    return recibir("curso", datos, request, tareas, clave=datos.email.lower())
