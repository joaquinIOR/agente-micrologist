"""Chat por consola. Uso: python main.py [hilo]   (el mismo hilo retoma la conversación anterior)."""
import os
import sqlite3
import sys

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite import SqliteSaver

from agente.datos import DIR
from agente.grafo import construir


def mostrar(nodo, cambio):
    if cambio.get("contexto"):
        print(f"  [memoria] {cambio['contexto']}")
    if cambio.get("plan"):
        print("  [plan] " + " | ".join(cambio["plan"]))
    if cambio.get("pendiente"):
        print(f"  [replanificar] {cambio['pendiente']}")
    for m in cambio.get("messages", []):
        for llamada in getattr(m, "tool_calls", None) or []:
            print(f"  [herramienta] {llamada['name']}({llamada['args']})")
        if m.type == "tool":
            print(f"  [resultado] {m.content}")
        elif nodo == "ejecutar" and m.text:
            print(f"\nAgente: {m.text}")


def main():
    load_dotenv()
    hilo = sys.argv[1] if len(sys.argv) > 1 else "principal"
    DIR.mkdir(parents=True, exist_ok=True)
    llm = init_chat_model(os.environ.get("LLM_MODELO", "groq:openai/gpt-oss-120b"), temperature=0)
    checkpointer = SqliteSaver(sqlite3.connect(DIR / "hilos.db", check_same_thread=False))
    agente = construir(llm, checkpointer)
    config = {"configurable": {"thread_id": hilo}}
    print(f"Agente MicroLogist (hilo '{hilo}'). Escribe 'salir' para terminar.")
    while (texto := input("\nTú: ").strip()) != "salir":
        if not texto:
            continue
        # Se imprime cada paso del grafo para que el razonamiento sea visible en la demo.
        try:
            for paso in agente.stream({"messages": [("user", texto)]}, config, stream_mode="updates"):
                for nodo, cambio in paso.items():
                    mostrar(nodo, cambio or {})
        except Exception as e:  # un fallo del proveedor no debe botar la sesión; el hilo queda guardado
            print(f"  [error] {e}")


if __name__ == "__main__":
    main()
