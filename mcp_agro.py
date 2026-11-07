"""Servidor MCP de AgroBot (S3): ofrece los manuales de datos/documentos/ a cualquier cliente MCP.

Solo lectura y solo esa carpeta. Con stdio no se puede imprimir nada: stdout es el canal del protocolo.

    uv run mcp_agro.py --servidor     # lo lanza el agente solo; no hace falta correrlo a mano
"""

import sys
from pathlib import Path

from fastmcp.client.transports import StdioTransport
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pypdf import PdfReader

# No importa config.py a propósito: el servidor no necesita claves ni el modelo
DOCUMENTOS = Path(__file__).resolve().parent / "datos" / "documentos"
MAX_CARACTERES = 6000  # un manual ficticio mide ~1500; el tope evita llenar el contexto del modelo

servidor = MCPServer("AgroBot Manuales")


def manuales_disponibles() -> list[str]:
    return sorted(pdf.stem for pdf in DOCUMENTOS.glob("*.pdf"))


@servidor.tool()
def listar_manuales() -> list[str]:
    """Nombres de los manuales y guías agrícolas disponibles (PDF ficticios del curso)."""
    return manuales_disponibles()


@servidor.tool()
def leer_manual(nombre: str) -> dict[str, str]:  # con tipos, el protocolo anuncia el esquema de la salida
    """Texto completo de un manual o guía agrícola, por ejemplo 'manual_papa'.

    Args:
        nombre: uno de los nombres que devuelve listar_manuales, sin '.pdf'
    """
    # El nombre se compara con la lista: nunca se arma una ruta con lo que manda el modelo
    if nombre not in manuales_disponibles():
        raise ToolError(f"No existe el manual '{nombre}'. Disponibles: {', '.join(manuales_disponibles())}")
    texto = "\n".join(pagina.extract_text() for pagina in PdfReader(DOCUMENTOS / f"{nombre}.pdf").pages)
    return {"manual": nombre, "texto": texto[:MAX_CARACTERES], "fuente": f"{nombre}.pdf (material ficticio)"}


def lanzar_servidor() -> StdioTransport:
    """Cómo se lanza este mismo archivo como servidor (stdio: el cliente le habla por su entrada y salida)."""
    # keep_alive=False: el subproceso nace y muere con cada conexión. Con True quedaría atado al event
    # loop que lo creó y fallaría en el siguiente («Event loop is closed»).
    return StdioTransport(
        command=sys.executable, args=[str(Path(__file__).resolve()), "--servidor"], keep_alive=False
    )


if __name__ == "__main__":
    if "--servidor" in sys.argv:
        servidor.run()  # stdio: aquí no se imprime nada
    else:
        print("Este archivo es un servidor MCP. Lo lanza el agente (asistente.py); para verlo: pytest.")
