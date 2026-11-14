import json

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from agente import memoria
from agente.datos import conectar
from agente.grafo import Plan, Revision, construir
from agente.herramientas import cambiar_estado, consultar_vehiculo, crear_orden, redactar_informe, revisar_flota


def test_consulta_flota_ordena_por_urgencia():
    docs = json.loads(revisar_flota.invoke({"dias": 30}))["documentos"]
    assert [d["patente"] for d in docs] == ["HRBD78", "KXTR45", "LJPW12", "PGSY90"]
    assert docs[0]["dias_restantes"] < 0
    assert "No existe" in consultar_vehiculo.invoke({"patente": "ZZZZ00"})


def test_escritura_valida_y_no_duplica():
    assert "Rechazada" in crear_orden.invoke({"patente": "LJPW12", "tipo": "x", "motivo": "m", "prioridad": "alta"})
    assert "ya tiene la orden abierta" in crear_orden.invoke(
        {"patente": "HRBD78", "tipo": "documento", "motivo": "m", "prioridad": "alta"})
    assert "está en taller" in cambiar_estado.invoke({"patente": "HRBD78", "estado": "bloqueado"})
    assert "creada" in crear_orden.invoke({"patente": "LJPW12", "tipo": "documento", "motivo": "SOAP", "prioridad": "media"})
    ruta = redactar_informe.invoke({"titulo": "../../Fuera", "contenido_markdown": "x"})
    assert "informes" in ruta and ".." not in ruta


def test_memoria_semantica():
    assert "en taller" in " ".join(memoria.buscar("politicas", "¿puedo bloquear un camión que está en reparación?", k=2))
    memoria.guardar("El taller Los Andes no recibe vehículos los sábados")
    assert "sábados" in memoria.buscar("recuerdos", "¿qué días atiende el taller?")[0]


class ModeloGuionado:
    """LLM falso con respuestas fijas."""

    def __init__(self, guion):
        self.guion = list(guion)

    def bind_tools(self, _):
        return self

    def with_structured_output(self, _):
        return self

    def invoke(self, _):
        return self.guion.pop(0)


def _llamada(nombre, **args):
    return AIMessage("", tool_calls=[{"name": nombre, "args": args, "id": nombre}])


def test_grafo_replanifica_y_recuerda_el_hilo():
    llm = ModeloGuionado([
        Plan(pasos=["Bloquear KXTR45"], escrituras=["cambiar_estado"]),
        _llamada("cambiar_estado", patente="KXTR45", estado="bloqueado"),
        AIMessage("Bloqueé KXTR45."),
        Revision(completo=False, pendiente="Falta crear la orden"),
        Plan(pasos=["Crear orden para KXTR45"], escrituras=["crear_orden"]),
        _llamada("crear_orden", patente="KXTR45", tipo="documento", motivo="Revisión técnica vencida", prioridad="alta"),
        AIMessage("Orden creada."),
        Revision(completo=True, pendiente=""),
        Plan(pasos=[]),
        AIMessage("Hola de nuevo."),
    ])
    agente = construir(llm, MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    fin = agente.invoke({"messages": [("user", "Regulariza KXTR45")]}, config)
    assert fin["planes"] == 2 and fin["messages"][-1].content == "Orden creada."
    con = conectar()
    assert con.execute("SELECT estado FROM vehiculos WHERE patente='KXTR45'").fetchone()["estado"] == "bloqueado"
    assert con.execute("SELECT 1 FROM ordenes WHERE patente='KXTR45'").fetchone()

    fin = agente.invoke({"messages": [("user", "hola")]}, config)  # mismo hilo
    assert fin["messages"][0].content == "Regulariza KXTR45" and fin["planes"] == 1


def test_escritura_no_autorizada_se_rechaza():
    llm = ModeloGuionado([
        Plan(pasos=["Consultar PGSY90"]),  # sin escrituras autorizadas
        _llamada("crear_orden", patente="PGSY90", tipo="mantencion", motivo="km", prioridad="media"),
        AIMessage("PGSY90 tiene la mantención atrasada."),
        Revision(completo=True, pendiente=""),
    ])
    fin = construir(llm, MemorySaver()).invoke({"messages": [("user", "¿Cómo está el PGSY90?")]},
                                               {"configurable": {"thread_id": "t2"}})
    assert "Rechazada" in fin["messages"][-2].content
    assert not conectar().execute("SELECT 1 FROM ordenes WHERE patente='PGSY90'").fetchone()


def test_historial_largo_se_recorta_y_conserva_el_turno_actual():
    from langchain_core.messages import HumanMessage
    from langchain_core.messages.utils import count_tokens_approximately

    from agente.grafo import MAX_TOKENS_HISTORIAL, REVISION, _recientes

    viejos = []
    for i in range(300):  # hilo largo
        viejos += [HumanMessage(f"pregunta {i} " + "x" * 200), AIMessage(f"respuesta {i} " + "y" * 200)]
    turno = [HumanMessage("Regulariza KXTR45"), _llamada("cambiar_estado", patente="KXTR45", estado="bloqueado"),
             HumanMessage(f"{REVISION} Falta: crear la orden")]
    enviados = _recientes(viejos + turno)
    assert enviados[-3:] == turno  # turno actual completo
    anteriores = enviados[:-3]
    assert anteriores and anteriores[0].type == "human" and anteriores[-1].content.startswith("respuesta 299")
    assert count_tokens_approximately(anteriores) <= MAX_TOKENS_HISTORIAL
    assert _recientes(turno) == turno  # hilo corto intacto


class ModeloSinCuota(ModeloGuionado):
    """LLM falso sin cuota."""

    def __init__(self):
        super().__init__([])
        self.llamadas = 0

    def invoke(self, _):
        self.llamadas += 1
        raise RuntimeError("429 cuota diaria agotada")


def test_respaldo_automatico_cuando_el_principal_falla():
    principal = ModeloSinCuota()
    respaldo = ModeloGuionado([
        Plan(pasos=["Consultar KXTR45"]),
        _llamada("consultar_vehiculo", patente="KXTR45"),
        AIMessage("KXTR45 está bloqueado."),
        Revision(completo=True, pendiente=""),
    ])
    fin = construir(principal, MemorySaver(), respaldo).invoke({"messages": [("user", "¿Cómo está el KXTR45?")]},
                                                             {"configurable": {"thread_id": "t3"}})
    assert fin["messages"][-1].content == "KXTR45 está bloqueado."
    assert principal.llamadas == 3  # luego solo el respaldo
    assert not respaldo.guion
