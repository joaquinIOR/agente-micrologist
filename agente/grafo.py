"""Grafo: recuperar -> planificar -> ejecutar <-> herramientas -> revisar (y replanificar si falta algo)."""
import time
from datetime import date
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from pydantic import BaseModel, Field

from . import memoria
from .herramientas import HERRAMIENTAS

MAX_PLANES = 3  # evita un bucle infinito
MAX_TOKENS_HISTORIAL = 6000  # historial enviado al modelo
REVISION = "[Revisión automática]"


def _recientes(mensajes):
    """Turno actual completo + turnos anteriores recientes hasta MAX_TOKENS_HISTORIAL."""
    inicio = max((i for i, m in enumerate(mensajes)
                  if m.type == "human" and not str(m.content).startswith(REVISION)), default=0)
    anteriores = trim_messages(mensajes[:inicio], max_tokens=MAX_TOKENS_HISTORIAL, strategy="last",
                               token_counter=count_tokens_approximately, start_on="human")
    return anteriores + mensajes[inicio:]

ROL = ("Eres el asistente de gestión de flota de MicroLogist, una empresa de transporte. "
       "Respondes en español. Nunca inventas datos: todo dato de vehículos sale de las herramientas.")


class Estado(TypedDict):
    messages: Annotated[list, add_messages]  # memoria de corto plazo
    contexto: str
    plan: list[str]
    planes: int
    pendiente: str
    escrituras: list[str]  # escrituras autorizadas


Escritura = Literal["crear_orden", "cambiar_estado", "redactar_informe", "guardar_recuerdo"]
POR_NOMBRE = {h.name: h for h in HERRAMIENTAS}


class Plan(BaseModel):
    pasos: list[str] = Field(description="Pasos concretos, ordenados del más urgente al menos urgente. "
                                         "Lista vacía si el mensaje es una conversación simple.")
    escrituras: list[Escritura] = Field(
        default_factory=list,
        description="Herramientas de escritura que la solicitud del usuario autoriza. Una pregunta no autoriza "
                    "ninguna. Pedir un informe autoriza solo redactar_informe. Pedir recordar algo autoriza solo "
                    "guardar_recuerdo. Pedir regularizar, bloquear o crear órdenes autoriza crear_orden y/o cambiar_estado.")


class Revision(BaseModel):
    completo: bool = Field(description="True si la solicitud del usuario quedó resuelta")
    pendiente: str = Field(description="Qué falta o qué condición cambió. Vacío si está completo.")


def _con_reintentos(modelo, mensajes):
    for intento in range(3):  # reintenta salidas inválidas
        try:
            return modelo.invoke(mensajes)
        except Exception as e:
            if intento == 2:
                raise
            if getattr(e, "status_code", None) == 429:
                # límite por minuto: espera; límite diario: falla
                cabeceras = getattr(getattr(e, "response", None), "headers", None) or {}
                espera = float(cabeceras.get("retry-after", 999))
                if espera > 60:
                    raise
                time.sleep(espera + 1)


class _Modelos:
    """Si el modelo principal falla, repite la llamada con el respaldo y sigue con él."""

    def __init__(self, principal, respaldo=None):
        self.principal, self.respaldo, self.en_respaldo = principal, respaldo, False

    def preparar(self, fn):
        return fn(self.principal), (fn(self.respaldo) if self.respaldo else None)

    def invocar(self, par, mensajes):
        principal, respaldo = par
        if not self.en_respaldo:
            try:
                return _con_reintentos(principal, mensajes)
            except Exception as e:
                if respaldo is None:
                    raise
                print(f"  [respaldo] el modelo principal falló ({type(e).__name__}); sigo con el modelo de respaldo")
                self.en_respaldo = True
        return _con_reintentos(respaldo, mensajes)


def _transcripcion(mensajes):
    """Historial en texto plano, para que planificador y revisor no intenten llamar herramientas."""
    lineas = []
    for m in mensajes:
        if m.type == "tool":
            lineas.append(f"resultado de {m.name}: {m.content[:600]}")
            continue
        for llamada in getattr(m, "tool_calls", None) or []:
            lineas.append(f"agente llama {llamada['name']}({llamada['args']})")
        if m.text:
            lineas.append(f"{'usuario' if m.type == 'human' else 'agente'}: {m.text}")
    return "\n".join(lineas)


def tras_revision(estado: Estado) -> str:
    return "planificar" if estado["pendiente"] and estado["planes"] < MAX_PLANES else END


def construir(llm, checkpointer=None, respaldo=None):
    modelos = _Modelos(llm, respaldo)
    planificador = modelos.preparar(lambda m: m.with_structured_output(Plan))
    revisor = modelos.preparar(lambda m: m.with_structured_output(Revision))
    ejecutor = modelos.preparar(lambda m: m.bind_tools(HERRAMIENTAS))
    _invocar = modelos.invocar

    def recuperar(estado):
        recuerdos = memoria.buscar("recuerdos", estado["messages"][-1].content)
        return {"contexto": "\n".join(recuerdos), "plan": [], "planes": 0, "pendiente": "", "escrituras": []}

    def planificar(estado):
        instruccion = SystemMessage(
            f"{ROL} Hoy es {date.today().isoformat()}.\n"
            "Divide la última solicitud del usuario en un máximo de 6 pasos priorizados, cada uno una frase corta en "
            "lenguaje natural (sin argumentos ni contenido de informes). Cada paso debe poder hacerse con estas "
            f"herramientas: {', '.join(h.name for h in HERRAMIENTAS)}. Empieza por consultar el estado real de la "
            "flota y la política aplicable; después las acciones. Regla de prioridad: primero documentos vencidos, "
            "luego documentos por vencer, al final mantenciones. No incluyas pasos que el usuario no pidió: "
            "redactar_informe solo si pide explícitamente un informe o reporte, guardar_recuerdo solo si pide "
            "recordar algo. Si el usuario solo pregunta algo, el plan solo consulta y responde, sin crear órdenes ni cambiar "
            "estados. Si el último mensaje es una revisión automática, replanifica solo lo que falta teniendo en "
            "cuenta lo que ya se hizo.\n"
            f"Recuerdos de conversaciones anteriores:\n{estado['contexto'] or '(ninguno)'}")
        plan = _invocar(planificador, [instruccion, HumanMessage(
            f"Conversación hasta ahora:\n{_transcripcion(_recientes(estado['messages']))}\n\nEntrega el plan.")])
        return {"plan": plan.pasos, "planes": estado["planes"] + 1, "escrituras": plan.escrituras}

    def ejecutar(estado):
        pasos = "\n".join(f"{i}. {p}" for i, p in enumerate(estado["plan"], 1)) or "(sin plan: responde directamente)"
        instruccion = SystemMessage(
            f"{ROL} Hoy es {date.today().isoformat()}.\n"
            f"Sigue este plan en orden usando las herramientas:\n{pasos}\n"
            "Consulta la política antes de crear órdenes o cambiar estados y aplícala completa a cada vehículo: "
            "si exige bloquear y además crear una orden, haz las dos cosas. Si una herramienta rechaza una acción, "
            "no insistas: adapta el resto del plan a esa condición y explícalo. "
            f"Herramientas de escritura autorizadas en esta solicitud: {', '.join(estado['escrituras']) or 'ninguna'}. "
            "No uses otras herramientas de escritura: serán rechazadas. "
            "Al terminar, resume lo que hiciste.\n"
            f"Recuerdos de conversaciones anteriores:\n{estado['contexto'] or '(ninguno)'}")
        return {"messages": [_invocar(ejecutor, [instruccion] + _recientes(estado["messages"]))]}

    def herramientas(estado):
        # permisos validados en código: el prompt no bastaba
        respuestas = []
        for llamada in estado["messages"][-1].tool_calls:
            nombre = llamada["name"]
            if nombre in Escritura.__args__ and nombre not in estado["escrituras"]:
                salida = f"Rechazada: el usuario no pidió usar {nombre} en esta solicitud. Continúa sin esa acción."
            else:
                try:
                    salida = POR_NOMBRE[nombre].invoke(llamada["args"])
                except Exception as e:  # el modelo puede corregir
                    salida = f"Error al ejecutar {nombre}: {e}"
            respuestas.append(ToolMessage(str(salida), tool_call_id=llamada["id"], name=nombre))
        return {"messages": respuestas}

    def revisar(estado):
        if not estado["plan"]:
            return {"pendiente": ""}
        rev = _invocar(revisor, [
            SystemMessage(f"{ROL}\nEvalúa si la última solicitud del usuario quedó resuelta. Juzga por lo que el "
                          "usuario pidió, no por si cada paso del plan se ejecutó literalmente: si la respuesta ya "
                          "contesta la solicitud con datos de las herramientas, está completo. Una acción rechazada "
                          "por una herramienta y explicada al usuario cuenta como resuelta. "
                          f"Plan de referencia: {estado['plan']}"),
            HumanMessage(f"Conversación:\n{_transcripcion(_recientes(estado['messages']))}\n\nEvalúa el resultado.")])
        if rev.completo or not rev.pendiente:
            return {"pendiente": ""}
        return {"pendiente": rev.pendiente,
                "messages": [HumanMessage(f"{REVISION} Falta: {rev.pendiente}")]}

    g = StateGraph(Estado)
    g.add_node("recuperar", recuperar)
    g.add_node("planificar", planificar)
    g.add_node("ejecutar", ejecutar)
    g.add_node("herramientas", herramientas)
    g.add_node("revisar", revisar)
    g.add_edge(START, "recuperar")
    g.add_edge("recuperar", "planificar")
    g.add_edge("planificar", "ejecutar")
    g.add_conditional_edges("ejecutar", tools_condition, {"tools": "herramientas", END: "revisar"})
    g.add_edge("herramientas", "ejecutar")
    g.add_conditional_edges("revisar", tras_revision, {"planificar": "planificar", END: END})
    # shortcut: el historial se recorta, no se resume
    return g.compile(checkpointer=checkpointer)
