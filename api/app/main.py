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
from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator, model_validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("sdl.api")

DB_PATH = os.getenv("DB_PATH", "/data/sdl.db")
IP_SALT = os.getenv("IP_SALT", "")
RATE_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))
RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "600"))

CORREO_SIMPLE = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")

# Versiones de la política de datos que el sitio ha publicado. Al cambiar el texto de la política agrega aquí la
# versión nueva y conserva las anteriores (páginas en caché). `npm run build` falla si src/data/politica.json
# tiene una versión que no está en esta lista (scripts/sincronizar-api.mjs).
POLITICAS_VALIDAS = ("2026-11-12",)

# Opciones válidas del formulario de diagnóstico, generadas desde src/data/diagnostico.json por
# scripts/sincronizar-api.mjs. Si falta, la API no arranca: mejor eso que aceptar valores sin comprobar.
with open(os.path.join(os.path.dirname(__file__), "opciones.json"), encoding="utf-8") as _f:
    OPCIONES = json.load(_f)


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
        servicios = ", ".join(SERVICIOS[s] for s in datos["servicios"])
        alertas = r["alertas"]
        marca = f"[ALERTAS {len(alertas)}] " if alertas else ""
        msg["Subject"] = (
            f"[SDL] {marca}Diagnóstico · {_una_linea(servicios, 70)} · {r['total']}/100 ({r['nivel']}): "
            f"{_una_linea(datos['empresa'], 50)}"
        )
        bloque_alertas = (
            "Alertas normativas (orientativas, no son asesoría legal):\n"
            + "\n".join(f"  - {a}" for a in alertas)
            + "\nOportunidad: acompañamiento en gobierno de datos (política, autorizaciones, contrato de encargo).\n\n"
            if alertas
            else ""
        )
        msg["Reply-To"] = datos["correo"]
        lineas_dim = "\n".join(
            f"  - {BRECHA[i][0]}: {p}/100 ({nivel_de(p)})" for i, p in r["dimensiones"].items()
        )
        lineas_detalle = "\n".join(
            f"{SERVICIOS[s]}:\n"
            + "\n".join(f"  - {etiqueta}: {datos['detalle'][k]}" for k, etiqueta in DETALLE[s].items())
            for s in datos["servicios"]
        )
        cuerpo = (
            f"Servicios que necesita: {servicios}\n\n"
            f"Nombre: {datos['nombre']}\n"
            f"Empresa: {datos['empresa']}\n"
            f"Correo: {datos['correo']}\n"
            f"WhatsApp: {datos['whatsapp']}\n"
            f"Sector: {datos['sector']}\n"
            f"Tamaño: {datos['tamano']}\n"
            f"Urgencia: {datos['urgencia'] or '-'}\n"
            f"Datos de personas que maneja: {', '.join(datos['datos_tipos'])}\n"
            f"Autorización de datos: aceptada (política {datos['politica']})\n\n"
            f"Sobre el servicio:\n{lineas_detalle}\n\n"
            f"Brecha digital: {r['total']}/100 ({r['nivel']})\n{lineas_dim}\n\n"
            f"{bloque_alertas}"
            f"Problema a resolver:\n{datos['friccion']}\n\n"
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
    "gobierno": (
        "Gobierno y normativa de datos",
        ("gob_politica", "gob_arco", "gob_retencion", "gob_responsables", "gob_incidentes"),
    ),
}
# Tipos de dato de personas que puede manejar la empresa. "ninguno" es excluyente con los demás.
TIPOS_DATO = ("basicos", "financieros", "menores", "salud", "biometricos", "ninguno")
# Preguntas de gobierno que se suman solo si la empresa maneja ese tipo de dato.
EXTRAS_GOBIERNO = {
    "menores": "gob_menores",
    "salud": "gob_salud",
    "biometricos": "gob_biometria",
    "financieros": "gob_financieros",
}
SERVICIOS = {
    "software": "Software a la medida",
    "datos": "Tableros y analítica de datos",
    "automatizacion": "Automatización con WhatsApp e IA",
    "soporte": "Auditoría, mantenimiento y soporte",
    "formacion": "Formación para equipos",
}
# Dimensiones de brecha digital que se miden según el servicio elegido.
SERVICIO_BRECHA: dict[str, tuple[str, ...]] = {
    "software": ("procesos", "herramientas", "gobierno"),
    "datos": ("datos", "herramientas", "gobierno"),
    "automatizacion": ("procesos", "atencion", "gobierno"),
    "soporte": ("herramientas", "seguridad", "gobierno"),
    "formacion": ("herramientas", "datos"),
}
# Preguntas propias de cada servicio (sin puntaje). La etiqueta corta se usa en el correo de aviso.
DETALLE: dict[str, dict[str, str]] = {
    "software": {"sw_tipo": "Qué necesita construir", "sw_usuarios": "Quiénes lo usarían", "sw_estado": "En qué punto está"},
    "datos": {"da_fuentes": "Dónde están sus datos", "da_necesidad": "Qué necesita ver o decidir", "da_herramienta": "Cómo reporta hoy"},
    "automatizacion": {"au_canal": "Canal de atención", "au_volumen": "Volumen diario", "au_tarea": "Qué automatizar primero"},
    "soporte": {"so_sistema": "Sistema a atender", "so_motivo": "Qué le preocupa", "so_modalidad": "Acompañamiento preferido"},
    "formacion": {"fo_tema": "Tema", "fo_personas": "Participantes", "fo_nivel": "Nivel actual"},
}
TELEFONO = re.compile(r"^[+\d\s().-]+$")
NIVELES = ((25, "Inicial"), (50, "En desarrollo"), (75, "Intermedio"), (100, "Avanzado"))


def dimensiones_de(servicios: list[str], tipos_dato: list[str]) -> list[str]:
    """Dimensiones de brecha de los servicios elegidos, sin repetir las compartidas."""
    dimensiones = list(dict.fromkeys(dim for s in servicios for dim in SERVICIO_BRECHA[s]))
    # El gobierno de datos solo se pregunta si la empresa maneja datos de personas.
    if tipos_dato == ["ninguno"]:
        dimensiones = [d for d in dimensiones if d != "gobierno"]
    return dimensiones


def preguntas_de(dimension: str, tipos_dato: list[str]) -> tuple[str, ...]:
    """Ids de pregunta de una dimensión; en gobierno se suman las que corresponden a los tipos de dato."""
    base = BRECHA[dimension][1]
    if dimension == "gobierno":
        return base + tuple(EXTRAS_GOBIERNO[t] for t in tipos_dato if t in EXTRAS_GOBIERNO)
    return base


def alertas_normativas(brecha: dict[str, int]) -> list[str]:
    """Señales de riesgo normativo según las respuestas (orientativas, no son asesoría legal)."""
    nivel = brecha.get
    reglas = (
        ("gob_menores", 1, "CRÍTICO · Datos de menores sin autorización del representante legal con prueba guardada."),
        ("gob_salud", 1, "CRÍTICO · Datos de salud sin control de acceso por rol ni trazabilidad."),
        ("gob_biometria", 1, "CRÍTICO · Biométricos, ubicación o cámaras sin autorización específica."),
        ("gob_financieros", 1, "ALTO · Datos financieros sin protección especial o compartidos por WhatsApp o correo."),
        ("gob_politica", 1, "ALTO · Sin política de tratamiento publicada ni autorización sistemática de los titulares."),
        ("gob_arco", 0, "ALTO · No sabría atender solicitudes de consulta, corrección o supresión de los titulares."),
        ("gob_responsables", 1, "ALTO · Sin responsable claro ni contratos con proveedores (encargo o transmisión, nube fuera de Colombia)."),
        ("gob_retencion", 0, "MEDIO · Conserva los datos personales sin un plazo definido."),
        ("gob_incidentes", 0, "MEDIO · Sin plan ante una filtración o pérdida de datos personales."),
    )
    return [texto for id_, tope, texto in reglas if nivel(id_) is not None and nivel(id_) <= tope]


def porcentaje(valores: list[int]) -> int:
    return round(sum(valores) / (len(valores) * 3) * 100) if valores else 0


def nivel_de(puntos: int) -> str:
    return next(nombre for tope, nombre in NIVELES if puntos <= tope)


class Diagnostico(Base):
    # Primero el contacto, todo obligatorio y validado: correo con formato real y WhatsApp con 7 a 15 dígitos.
    nombre: str = Field(min_length=1, max_length=120)
    empresa: str = Field(min_length=1, max_length=160)
    correo: EmailStr
    whatsapp: str = Field(min_length=7, max_length=30)
    # Autorización de tratamiento de datos: obligatoria. Se guarda la versión de la política que aceptó.
    acepta: bool
    politica: str = Field(min_length=1, max_length=40)
    # Después uno o varios servicios; de ellos dependen las preguntas.
    servicios: list[str] = Field(min_length=1, max_length=len(SERVICIOS))
    sector: str = Field(min_length=1, max_length=80)
    tamano: str = Field(min_length=1, max_length=80)
    # Qué tipos de datos de personas maneja la empresa: decide si se pregunta gobierno de datos y qué extras.
    datos_tipos: list[str] = Field(min_length=1, max_length=len(TIPOS_DATO))
    brecha: dict[str, int]
    detalle: dict[str, str]
    friccion: str = Field(min_length=3, max_length=2000)
    urgencia: str = Field("", max_length=80)
    objetivo: str = Field("", max_length=2000)

    @field_validator("servicios")
    @classmethod
    def _servicios(cls, v: list[str]) -> list[str]:
        if any(s not in SERVICIOS for s in v):
            raise ValueError("servicio desconocido")
        return list(dict.fromkeys(v))

    @field_validator("acepta")
    @classmethod
    def _acepta(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("falta la autorización de tratamiento de datos")
        return v

    @field_validator("datos_tipos")
    @classmethod
    def _datos_tipos(cls, v: list[str]) -> list[str]:
        if any(t not in TIPOS_DATO for t in v):
            raise ValueError("tipo de dato desconocido")
        v = list(dict.fromkeys(v))
        if "ninguno" in v and len(v) > 1:
            raise ValueError("'ninguno' no se combina con otros tipos")
        return v

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp(cls, v: str) -> str:
        if not TELEFONO.match(v) or not 7 <= len(re.sub(r"\D", "", v)) <= 15:
            raise ValueError("whatsapp inválido")
        return v

    @field_validator("politica")
    @classmethod
    def _politica(cls, v: str) -> str:
        if v not in POLITICAS_VALIDAS:
            raise ValueError("versión de la política desconocida")
        return v

    @field_validator("sector")
    @classmethod
    def _sector(cls, v: str) -> str:
        if v not in OPCIONES["sectores"]:
            raise ValueError("sector desconocido")
        return v

    @field_validator("tamano")
    @classmethod
    def _tamano(cls, v: str) -> str:
        if v not in OPCIONES["tamanos"]:
            raise ValueError("tamaño desconocido")
        return v

    @field_validator("urgencia")
    @classmethod
    def _urgencia(cls, v: str) -> str:
        if v and v not in OPCIONES["urgencias"]:
            raise ValueError("urgencia desconocida")
        return v

    @field_validator("detalle")
    @classmethod
    def _detalle(cls, v: dict[str, str]) -> dict[str, str]:
        for k, t in v.items():
            if t not in OPCIONES["detalle"].get(k, ()):
                raise ValueError(f"respuesta desconocida para {k}")
        return {k: _una_linea(t, 120) for k, t in v.items()}

    @model_validator(mode="after")
    def _coherente_con_los_servicios(self) -> "Diagnostico":
        # Las áreas compartidas entre servicios se preguntan una sola vez.
        esperadas = {
            p for dim in dimensiones_de(self.servicios, self.datos_tipos) for p in preguntas_de(dim, self.datos_tipos)
        }
        if set(self.brecha) != esperadas or any(not 0 <= n <= 3 for n in self.brecha.values()):
            raise ValueError("brecha incompleta o fuera de rango para los servicios")
        propias = {k for s in self.servicios for k in DETALLE[s]}
        if set(self.detalle) != propias or not all(self.detalle.values()):
            raise ValueError("preguntas de los servicios incompletas")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resultado(self) -> dict:
        """Puntaje 0-100 por dimensión y total, calculado aquí (no se confía en el navegador)."""
        dimensiones = {
            dim: porcentaje([self.brecha[p] for p in preguntas_de(dim, self.datos_tipos)])
            for dim in dimensiones_de(self.servicios, self.datos_tipos)
        }
        total = porcentaje(list(self.brecha.values()))
        return {
            "total": total,
            "nivel": nivel_de(total),
            "dimensiones": dimensiones,
            "alertas": alertas_normativas(self.brecha),
        }


# --------------------------------------------------------------------------- app
@asynccontextmanager
async def ciclo(_: FastAPI):
    if not IP_SALT:
        # Sin sal, el hash de la IP se puede revertir probando las IPv4 posibles: no guardamos nada así.
        raise RuntimeError("IP_SALT está vacío: define uno en .env (openssl rand -hex 32).")
    iniciar_db()
    yield


app = FastAPI(title="SDL API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo)

# Mensaje y paso del formulario de diagnóstico (0 contacto, 1 servicios, 2 empresa) por campo con error.
CAMPOS_DIAGNOSTICO = {
    "nombre": ("Escribe tu nombre.", 0),
    "empresa": ("Escribe el nombre de tu empresa.", 0),
    "correo": ("Revisa tu correo: parece no ser válido o no existe ese dominio.", 0),
    "whatsapp": ("Revisa tu WhatsApp: debe tener entre 7 y 15 dígitos.", 0),
    "acepta": ("Debes autorizar el tratamiento de tus datos para continuar.", 0),
    "politica": ("La política de datos cambió. Recarga la página e inténtalo de nuevo.", 0),
    "servicios": ("Elige al menos un servicio.", 1),
    "sector": ("Elige tu sector.", 2),
    "tamano": ("Elige el tamaño de tu empresa.", 2),
    "datos_tipos": ("Marca los tipos de datos que manejas.", 2),
}


@app.exception_handler(RequestValidationError)
async def datos_invalidos(request: Request, exc: RequestValidationError) -> JSONResponse:
    contenido: dict = {"detail": "Revisa los datos e intenta de nuevo."}
    if request.url.path == "/api/diagnostico":
        for error in exc.errors():
            campo = next((str(p) for p in error.get("loc", ()) if p in CAMPOS_DIAGNOSTICO), None)
            if campo:
                mensaje, paso = CAMPOS_DIAGNOSTICO[campo]
                contenido = {"detail": mensaje, "campo": campo, "paso": paso}
                break
    return JSONResponse(status_code=422, content=contenido)


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
