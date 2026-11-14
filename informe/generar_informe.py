"""Genera el informe EP2 (Word). Uso: python informe.py <carpeta_repo>"""
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

REPO = Path(sys.argv[1])
SALIDA = REPO / "informe" / "Informe_EP2_ISY0101.docx"

doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Cm(2)
    s.left_margin = s.right_margin = Cm(2.2)
estilo = doc.styles["Normal"]
estilo.font.name = "Arial"
estilo.font.size = Pt(10.5)
estilo.paragraph_format.space_after = Pt(4)
estilo.paragraph_format.line_spacing = 1.0
for n, t in (("Heading 1", 13), ("Heading 2", 11)):
    doc.styles[n].font.name = "Arial"
    doc.styles[n].font.size = Pt(t)
    doc.styles[n].paragraph_format.space_before = Pt(8)
    doc.styles[n].paragraph_format.space_after = Pt(3)

# Número de página en el pie
pie = doc.sections[0].footer.paragraphs[0]
pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
for tipo, texto in (("begin", None), (None, "PAGE"), ("end", None)):
    run = pie.add_run()
    if tipo:
        el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), tipo)
    else:
        el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = texto
    run._r.append(el)


def p(texto, negrita=False, centro=False):
    par = doc.add_paragraph()
    run = par.add_run(texto)
    run.bold = negrita
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER if centro else WD_ALIGN_PARAGRAPH.JUSTIFY
    return par


def tabla(filas, anchos):
    t = doc.add_table(rows=len(filas), cols=len(filas[0]))
    t.style = "Light Grid Accent 1"
    for i, fila in enumerate(filas):
        for j, celda in enumerate(fila):
            c = t.cell(i, j)
            c.width = Cm(anchos[j])
            c.text = celda
            for par in c.paragraphs:
                for r in par.runs:
                    r.font.size = Pt(9)
                    r.bold = i == 0
    doc.add_paragraph()


# Encabezado (sin portada aparte para respetar el máximo de cinco páginas)
p("Agente de gestión de flota para MicroLogist", negrita=True, centro=True).runs[0].font.size = Pt(15)
p("Evaluación Parcial N°2 · ISY0101 Ingeniería de Soluciones con IA", centro=True)
p("Autor: Joaquín Orellana Canales", centro=True)
p("Repositorio: https://github.com/joaquinIOR/agente-micrologist", centro=True)

doc.add_heading("1. Requerimiento organizacional", 1)
p("MicroLogist es una empresa de transporte que controla los vencimientos de la revisión técnica, el permiso de "
  "circulación y el SOAP, además de las mantenciones de cada vehículo, revisando ficha por ficha. Este trabajo es "
  "manual, lento y depende de que alguien se acuerde de revisar. Si un documento vence y nadie lo nota, el vehículo "
  "sigue circulando de forma irregular y la empresa queda expuesta a multas.")
p("Desarrollé un agente que automatiza ese flujo completo: revisa la flota, decide qué hacer según las políticas "
  "internas de la empresa, registra la acción (crea órdenes de trabajo o bloquea vehículos) e informa el resultado. "
  "Los datos de la flota y las políticas son simulados, pero el flujo es el mismo que se haría en la operación real.")

doc.add_heading("2. Diseño e implementación del agente", 1)
p("El agente está construido en Python con LangGraph, el framework de LangChain para agentes con flujo explícito. "
  "El modelo de lenguaje es gemini-2.5-flash de Google, con temperatura 0 para que las decisiones sean "
  "reproducibles, y Groq con openai/gpt-oss-120b queda configurado como respaldo. El modelo se carga con init_chat_model, por lo que el proveedor se cambia desde el archivo .env "
  "sin modificar el código.")
p("El agente cuenta con siete herramientas, separadas según su función:")
tabla([
    ["Tipo", "Herramienta", "Función"],
    ["Consulta", "consultar_vehiculo", "Ficha, documentos y órdenes abiertas de una patente."],
    ["Consulta", "revisar_flota", "Pendientes de toda la flota, ordenados por urgencia."],
    ["Consulta semántica", "buscar_politica", "Recupera por significado las políticas internas aplicables."],
    ["Escritura", "crear_orden", "Registra una orden de trabajo; rechaza duplicados y datos inválidos."],
    ["Escritura", "cambiar_estado", "Cambia el estado del vehículo; no bloquea uno que está en taller."],
    ["Escritura", "redactar_informe", "Genera un informe en Markdown en la carpeta de informes."],
    ["Escritura", "guardar_recuerdo", "Guarda un hecho en la memoria de largo plazo."],
], [3.2, 3.8, 9.5])
p("El razonamiento lo aportan tres nodos del grafo que usan el modelo con roles distintos: planificar, ejecutar y "
  "revisar. Las herramientas validan sus propios datos de entrada (patente existente, tipo y prioridad válidos), de "
  "modo que el agente recibe un rechazo explícito cuando una acción no corresponde y puede adaptarse.")

doc.add_heading("3. Orquestación de componentes", 1)
img = REPO / "informe" / "orquestacion.png"
if img.exists():
    doc.add_picture(str(img), width=Cm(11))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    p("Figura 1. Diagrama de orquestación del agente.", centro=True).runs[0].italic = True
p("Cada solicitud del usuario recorre el siguiente flujo:")
tabla([
    ["Nodo", "Qué hace"],
    ["recuperar", "Busca en la memoria de largo plazo recuerdos relacionados con el mensaje."],
    ["planificar", "El modelo entrega un plan estructurado: pasos ordenados por urgencia y escrituras autorizadas."],
    ["ejecutar", "El modelo sigue el plan y decide qué herramienta llamar (ciclo razonar–actuar)."],
    ["herramientas", "Ejecuta la herramienta si el plan la autoriza y devuelve el resultado al modelo."],
    ["revisar", "El modelo evalúa si la solicitud quedó resuelta; si falta algo, vuelve a planificar."],
], [3.2, 13.3])
p("El ciclo entre ejecutar y herramientas se repite hasta que el modelo entrega una respuesta final. Si el revisor "
  "detecta que algo quedó pendiente o que una condición cambió, el flujo vuelve a planificar, con un tope de tres "
  "planes por solicitud para evitar un bucle infinito.")

doc.add_heading("4. Memoria y recuperación de contexto", 1)
tabla([
    ["", "Corto plazo", "Largo plazo"],
    ["Qué guarda", "Historial de la conversación", "Recuerdos del usuario y políticas de la empresa"],
    ["Cómo se consulta", "En orden exacto y completo", "Por significado (búsqueda semántica, 3 resultados)"],
    ["Componente", "Checkpointer SQLite de LangGraph (hilos.db), por thread_id", "Chroma persistente con embeddings locales"],
], [3.2, 6.5, 6.8])
p("La memoria de corto plazo permite que el agente resuelva referencias dentro de una conversación, por ejemplo "
  "«¿y qué pasó con el primero que bloqueaste?». Como el historial queda guardado en disco, al volver a ejecutar "
  "python main.py con el mismo hilo la conversación continúa donde quedó. Para que un flujo prolongado no exceda la "
  "ventana del modelo, se envía el turno actual completo y solo los turnos anteriores más recientes que caben en "
  "6.000 tokens (trim_messages); el historial completo sigue guardado en disco.")
p("La memoria de largo plazo tiene dos colecciones en Chroma. La colección recuerdos se consulta al inicio de cada "
  "turno, así un dato guardado en una conversación aparece en otra distinta. La colección politicas es la base de "
  "conocimiento: el agente la consulta antes de actuar. Elegí recuperación semántica porque el usuario no repite "
  "las mismas palabras; en las pruebas, la pregunta «¿puedo bloquear un camión que está en reparación?» recupera la "
  "política sobre vehículos en taller aunque no comparten palabras clave.")

doc.add_heading("5. Planificación y toma de decisiones", 1)
p("El plan se genera antes de tocar cualquier dato y sigue la prioridad definida por la empresa: primero los "
  "documentos vencidos, luego los que están por vencer y al final las mantenciones. Además, el planificador declara "
  "qué herramientas de escritura autoriza la solicitud: una pregunta no autoriza ninguna y un pedido de informe "
  "autoriza solo redactar_informe. El nodo herramientas rechaza en código cualquier escritura no autorizada.")
p("Los siguientes escenarios muestran cómo el agente ajusta su comportamiento según las condiciones:")
tabla([
    ["Situación", "Decisión del agente"],
    ["KXTR45 tiene la revisión técnica vencida y está operativo.", "Lo bloquea y crea una orden de tipo documento con prioridad alta."],
    ["HRBD78 también tiene la revisión vencida, pero está en taller y ya tiene una orden abierta.", "La herramienta rechaza el bloqueo y la orden duplicada; el agente lo explica y continúa con el resto del plan."],
    ["El usuario solo pregunta por el estado del PGSY90.", "Consulta y responde sin escribir nada; si intenta crear una orden, se rechaza."],
    ["El usuario pide bloquear la patente ABCD12, que no existe.", "Informa el rechazo sin inventar datos."],
    ["El revisor detecta que faltó crear una orden después de bloquear.", "Replanifica solo lo pendiente y lo completa."],
], [8.2, 8.3])

doc.add_heading("6. Decisiones de diseño", 1)
for titulo, texto in [
    ("LangGraph en lugar de un agente ReAct de un solo bucle. ",
     "El proceso tiene etapas definidas y quería que quedaran explícitas como un grafo. LangGraph además trae el "
     "checkpointer para la memoria de corto plazo y permite reemplazar el nodo estándar de herramientas por uno propio "
     "que valida permisos. Para escalar, cada componente se puede cambiar sin tocar el grafo: SQLite por PostgreSQL, "
     "Chroma local por un servidor vectorial y los datos simulados por la API real de la empresa."),
    ("Planificador, ejecutor y revisor separados. ",
     "Cada rol tiene una salida acotada y validable. El plan estructurado fija la prioridad y los permisos antes de "
     "actuar, y el razonamiento queda visible en la consola durante la demostración."),
    ("SQLite para el historial y Chroma para lo semántico. ",
     "El historial necesita orden exacto y persistencia, no búsqueda por significado, y SQLite lo entrega sin servidor. "
     "Los recuerdos y las políticas se consultan por significado, y Chroma funciona en local, persistente y sin clave."),
    ("Reglas críticas en código y no solo en el prompt. ",
     "En las pruebas con el modelo real, el agente creó órdenes y bloqueó vehículos ante una simple pregunta, aunque el "
     "prompt lo prohibía. Por eso todo lo que modifica la flota se valida en código, donde es determinista y se puede "
     "probar."),
    ("Gemini como modelo principal y Groq como respaldo. ",
     "Partí con Groq y gpt-oss-120b, pero su cuota diaria gratuita se agotaba con pocas ejecuciones completas. Gemini "
     "tiene capa gratuita, soporta herramientas y salida estructurada, lo que verifiqué con el agente, y tiene una "
     "ventana de contexto amplia. Groq quedó como respaldo automático: si Gemini falla, la misma llamada se repite con "
     "Groq y el agente sigue, así una cuota agotada no detiene la demo."),
]:
    par = p("")
    par.add_run(titulo).bold = True
    par.add_run(texto)

doc.add_heading("7. Pruebas", 1)
p("Las pruebas se ejecutan con python -m pytest -q y usan un modelo guionado, que entrega respuestas fijas, para "
  "probar la orquestación sin clave de API. Cubren la consulta ordenada por urgencia, las validaciones de escritura "
  "(orden duplicada, vehículo en taller, ruta del informe), la recuperación semántica, el grafo completo con "
  "replanificación y continuidad del hilo, el rechazo de escrituras no autorizadas, el recorte del historial en "
  "hilos largos y el respaldo automático cuando el modelo principal falla.")

p("Resultado: los 7 casos de prueba pasan (7 passed). La salida completa está en evidencia/pytest.txt.")

doc.add_heading("Evidencia de ejecución real", 2)
p("Extracto de la ejecución del escenario 1 con Gemini, ante el mensaje «Revisa la flota y regulariza todo lo "
  "pendiente». La traza completa está en evidencia/escenario1_gemini.txt.")
TRAZA = [
    "[plan] Consultar el estado real de la flota. | Consultar la política aplicable... | Crear órdenes para "
    "documentos vencidos. | ...por vencer. | ...mantenimientos pendientes.",
    "[herramienta] revisar_flota({})",
    "[herramienta] buscar_politica({'consulta': 'política para documentos vencidos y por vencer...'})",
    "[herramienta] cambiar_estado({'estado': 'bloqueado', 'patente': 'KXTR45'})",
    "[resultado] KXTR45 pasó de 'operativo' a 'bloqueado'.",
    "[herramienta] crear_orden({... 'prioridad': 'alta', 'tipo': 'documento', 'patente': 'KXTR45'})",
    "[resultado] Orden #2 creada para KXTR45 (documento, prioridad alta).",
    "[herramienta] crear_orden({'patente': 'HRBD78', 'tipo': 'documento', ... 'prioridad': 'alta'})",
    "[resultado] Rechazada: HRBD78 ya tiene la orden abierta #1 de tipo documento. No se duplica.",
    "[resultado] Orden #3 creada para LJPW12 (documento, prioridad media).",
    "[resultado] Orden #4 creada para PGSY90 (documento, prioridad baja).",
    "[resultado] Orden #5 y #6: mantención para HRBD78 y PGSY90 (prioridad media).",
]
for linea in TRAZA:
    par = doc.add_paragraph()
    par.paragraph_format.space_after = Pt(0)
    r = par.add_run(linea)
    r.font.name = "Consolas"
    r.font.size = Pt(8)
p("")
p("La traza muestra el orden de prioridad de la política (vencidos, por vencer, mantenciones), la consulta de la "
  "política antes de actuar y la adaptación ante una condición distinta: HRBD78 está en taller y ya tiene una orden, "
  "así que el agente no lo bloquea y la herramienta rechaza la orden duplicada.")
p("Las ejecuciones de memoria y de decisiones también quedaron registradas en la carpeta evidencia:")
tabla([
    ["Mensaje", "Resultado real"],
    ["Hilo A: «Recuerda que el taller no recibe vehículos los sábados»",
     "Guarda el recuerdo en la memoria de largo plazo."],
    ["Hilo B, nuevo: «¿Cuándo puedo mandar el PGSY90 al taller?»",
     "Recupera el recuerdo en [memoria] y responde que, como hoy es sábado, puede ir el lunes."],
    ["Mismo hilo del escenario 1: «¿Y qué pasó con el primero que bloqueaste?»",
     "Responde KXTR45 usando el historial del hilo (memoria de corto plazo)."],
    ["«¿Cómo está el PGSY90?»", "Consulta y responde sin crear órdenes ni cambiar estados."],
    ["«Bloquea el vehículo ABCD12»", "Informa que la patente no existe y no inventa datos."],
], [8.2, 8.3])

doc.add_heading("8. Limitaciones", 1)
p("Los turnos antiguos de un hilo se recortan, no se resumen: lo que queda fuera de la ventana de 6.000 tokens solo "
  "se conserva si el agente lo guardó en la memoria de largo plazo. Los embeddings por defecto de Chroma están entrenados principalmente en "
  "inglés; funcionan con las políticas actuales, pero si la base crece conviene un modelo multilingüe. Las capas "
  "gratuitas de Gemini y Groq limitan el uso diario de tokens.")

doc.add_heading("9. Conclusión", 1)
p("El agente resuelve el requerimiento de MicroLogist: revisa la flota, decide según las políticas, registra las "
  "acciones e informa, manteniendo el contexto dentro y entre conversaciones. Considero que la decisión más "
  "importante fue validar en código las acciones que modifican datos, porque el modelo no siempre respeta las "
  "instrucciones del prompt. El diseño en grafo permite crecer hacia la operación real cambiando los componentes de "
  "datos sin rehacer la orquestación.")
p("Para el desarrollo usé Claude Code como apoyo para programar y redactar; las decisiones de diseño fueron mías. La presentación la hice con Claude.")

doc.add_heading("Referencias", 1)
REFS = [
    "Chroma. (s. f.). Chroma documentation [Documentación de software]. https://docs.trychroma.com",
    "Google. (s. f.). Gemini API documentation [Documentación de software]. https://ai.google.dev/gemini-api/docs",
    "Groq. (s. f.). GroqCloud documentation [Documentación de software]. https://console.groq.com/docs",
    "LangChain. (s. f.-a). LangChain documentation [Documentación de software]. https://docs.langchain.com",
    "LangChain. (s. f.-b). LangGraph documentation [Documentación de software]. https://docs.langchain.com/oss/python/langgraph/overview",
    "Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems, 33, 9459–9474. https://arxiv.org/abs/2005.11401",
    "OpenAI. (2025). gpt-oss-120b & gpt-oss-20b model card (arXiv:2508.10925). arXiv. https://doi.org/10.48550/arXiv.2508.10925",
    "Pydantic. (s. f.). Pydantic documentation [Documentación de software]. https://docs.pydantic.dev",
    "pytest. (s. f.). pytest documentation [Documentación de software]. https://docs.pytest.org",
    "Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. En Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing (pp. 3982–3992). Association for Computational Linguistics. https://arxiv.org/abs/1908.10084",
    "SQLite. (s. f.). SQLite documentation [Documentación de software]. https://www.sqlite.org/docs.html",
    "Wang, L., Xu, W., Lan, Y., Hu, Z., Lan, Y., Lee, R. K.-W., & Lim, E.-P. (2023). Plan-and-solve prompting: Improving zero-shot chain-of-thought reasoning by large language models. En Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (pp. 2609–2634). Association for Computational Linguistics. https://arxiv.org/abs/2305.04091",
    "Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. En International Conference on Learning Representations (ICLR 2023). https://arxiv.org/abs/2210.03629",
]
for r in REFS:
    par = doc.add_paragraph(r)
    par.paragraph_format.left_indent = Cm(1.27)
    par.paragraph_format.first_line_indent = Cm(-1.27)  # sangría francesa APA
    par.runs[0].font.size = Pt(9.5)

SALIDA.parent.mkdir(exist_ok=True)
doc.save(SALIDA)
print(SALIDA)
