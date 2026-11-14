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
    """LLM falso: devuelve respuestas fijas en orden, para probar la orquestación sin API key."""

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

    fin = agente.invoke({"messages": [("user", "hola")]}, config)  # mismo hilo: conserva el historial
    assert fin["messages"][0].content == "Regulariza KXTR45" and fin["planes"] == 1


def test_escritura_no_autorizada_se_rechaza():
    llm = ModeloGuionado([
        Plan(pasos=["Consultar PGSY90"]),  # una pregunta: el plan no autoriza escrituras
        _llamada("crear_orden", patente="PGSY90", tipo="mantencion", motivo="km", prioridad="media"),
        AIMessage("PGSY90 tiene la mantención atrasada."),
        Revision(completo=True, pendiente=""),
    ])
    fin = construir(llm, MemorySaver()).invoke({"messages": [("user", "¿Cómo está el PGSY90?")]},
                                               {"configurable": {"thread_id": "t2"}})
    assert "Rechazada" in fin["messages"][-2].content
    assert not conectar().execute("SELECT 1 FROM ordenes WHERE patente='PGSY90'").fetchone()
