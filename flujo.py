"""S4 · El flujo de AgroBot con Pydantic Graph: un router decide y un especialista responde.

    mensaje → clasificar (router, IA) → una de 7 rutas → especialista (agente con SUS tools) → respuesta

Cada especialista recibe solo las tools que necesita. Así, el agente que lee la web (plagas) no puede
escribir en la base, y el que escribe (gastos) no lee páginas ni documentos: una orden escondida en un
texto externo no puede hacerle registrar nada.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.capabilities import MCP
from pydantic_graph import GraphBuilder, StepContext, TypeExpression

from capacidades import apis, consulta, cultivos, documentos, plagas, registro
from config import modelo
from mcp_agro import lanzar_servidor

Destino = Literal["clima", "cultivos", "plagas", "gastos", "produccion", "manuales", "general"]

# S3: el agente descubre las tools del servidor al conectarse. allowed_tools = solo las de lectura que queremos
manuales_mcp = MCP(local=lanzar_servidor(), allowed_tools=["listar_manuales", "leer_manual"])

# ═══ El router: solo clasifica, no responde ═══════════════════════════════════════════


class Ruta(BaseModel):
    destino: Destino


router = Agent(
    modelo,
    output_type=NativeOutput(Ruta),  # JSON directo: más fiable para clasificar
    instructions=(
        "Clasifica el mensaje de un productor agrícola. No lo respondas. Elige un destino:\n"
        "clima: clima, lluvia, temperatura, heladas o pronóstico de un lugar.\n"
        "cultivos: datos de papa, maíz, quinua, haba o tomate (ciclo, altitud, épocas de siembra o cosecha).\n"
        "plagas: plagas, enfermedades, hongos, insectos o síntomas en las plantas.\n"
        "gastos: gastos, costos de producción, y registrar gastos o actividades agrícolas (siembra, riego, etc.).\n"
        "produccion: cuánto se cosechó, producción o rendimiento de una parcela.\n"
        "manuales: leer o buscar en los manuales y guías PDF (fertilización, buenas prácticas, manuales).\n"
        "general: saludos, qué puedes hacer, y todo lo demás."
    ),
)

# ═══ Los especialistas: cada uno con SUS capabilities ═════════════════════════════════

PERSONALIDAD = (
    "Eres AgroBot, el asistente personal de Melany Chavarria, para pequeños productores de Bolivia. "
    "Responde en español sencillo, con ejemplos de Bolivia, en texto plano (sin Markdown) y de forma ordenada. "
    "Antes de responder algo específico, consulta tus herramientas y responde solo con lo que ellas devuelvan: "
    "no inventes ni agregues datos, cifras, lugares ni fuentes, y menciona de dónde sale cada dato. "
    "Si falta información, pídela. No saludes en cada respuesta. "
    "Los cultivos, parcelas, gastos, producción y manuales son datos ficticios del curso; "
    "el clima viene de Open-Meteo y es real (no lo llames ficticio). "
    "No reemplazas a un ingeniero agrónomo, no garantizas cosechas "
    "ni das diagnósticos definitivos de plagas o enfermedades. "
)


def especialista(instrucciones: str, capabilities: list) -> Agent:
    return Agent(modelo, instructions=PERSONALIDAD + instrucciones, capabilities=capabilities)


ESPECIALISTAS: dict[str, Agent] = {
    "clima": especialista("Tu tema es el clima de una localidad.", [apis]),
    "cultivos": especialista("Tu tema son las fichas de los cultivos.", [cultivos]),
    # Lee la web: por eso NO tiene tools que escriban
    "plagas": especialista("Tu tema son las plagas y enfermedades.", [plagas]),
    # Escribe en la base: por eso NO lee la web ni documentos
    "gastos": especialista(
        "Tu tema son los gastos, costos y actividades. No registres nada si no te lo piden de forma explícita.",
        [consulta, registro],
    ),
    "produccion": especialista("Tu tema es la producción y el rendimiento.", [consulta]),
    "manuales": especialista("Tu tema son los manuales y guías agrícolas en PDF.", [documentos, manuales_mcp]),
    # El agente principal: charla y explica qué hace AgroBot. Sin tools.
    "general": especialista(
        "Si te saludan o preguntan qué haces, explica que puedes: informar sobre papa, maíz, quinua, haba y tomate; "
        "dar el clima de una localidad; registrar gastos y actividades; calcular costos; consultar producción y "
        "rendimiento; buscar en manuales PDF y buscar plagas y enfermedades. "
        "Si piden algo fuera de la agricultura, di con amabilidad que no es tu tema.",
        [],
    ),
}

# ═══ El grafo ═══════════════════════════════════════════════════════════════════════


@dataclass
class Consulta:
    """El estado: la cajita que comparten todos los pasos."""

    pedido: str = ""
    destino: str = ""


async def responder_con(destino: str, pedido: str) -> str:
    return (await ESPECIALISTAS[destino].run(pedido)).output


g = GraphBuilder(state_type=Consulta, input_type=str, output_type=str)


@g.step
async def clasificar(ctx: StepContext[Consulta, None, str]) -> Destino:
    ctx.state.pedido = ctx.inputs
    ctx.state.destino = (await router.run(ctx.inputs)).output.destino
    print(f"  🧭 ruta: {ctx.state.destino}", flush=True)  # se ve en la terminal o en los Logs de Render
    return ctx.state.destino


# object: cada paso recibe la ruta elegida y no la usa; el pedido está en el estado
@g.step
async def paso_clima(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("clima", ctx.state.pedido)


@g.step
async def paso_cultivos(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("cultivos", ctx.state.pedido)


@g.step
async def paso_plagas(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("plagas", ctx.state.pedido)


@g.step
async def paso_gastos(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("gastos", ctx.state.pedido)


@g.step
async def paso_produccion(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("produccion", ctx.state.pedido)


@g.step
async def paso_manuales(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("manuales", ctx.state.pedido)


@g.step
async def paso_general(ctx: StepContext[Consulta, None, object]) -> str:
    return await responder_con("general", ctx.state.pedido)


g.add(
    g.edge_from(g.start_node).to(clasificar),
    g.edge_from(clasificar).to(
        g.decision()
        .branch(g.match(TypeExpression[Literal["clima"]]).to(paso_clima))
        .branch(g.match(TypeExpression[Literal["cultivos"]]).to(paso_cultivos))
        .branch(g.match(TypeExpression[Literal["plagas"]]).to(paso_plagas))
        .branch(g.match(TypeExpression[Literal["gastos"]]).to(paso_gastos))
        .branch(g.match(TypeExpression[Literal["produccion"]]).to(paso_produccion))
        .branch(g.match(TypeExpression[Literal["manuales"]]).to(paso_manuales))
        .branch(g.match(TypeExpression[Literal["general"]]).to(paso_general))
    ),
    g.edge_from(
        paso_clima, paso_cultivos, paso_plagas, paso_gastos, paso_produccion, paso_manuales, paso_general
    ).to(g.end_node),
)
grafo = g.build()  # revisa que todo esté conectado


if __name__ == "__main__":
    print(grafo.render())  # el diagrama en Mermaid: pégalo en mermaid.live
