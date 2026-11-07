"""Pruebas sin modelo real ni internet: uv run pytest

Un modelo falso (FunctionModel) pide la tool que queremos, y comprobamos lo que hace el código.
"""

import json
import os
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

os.environ.setdefault("GEMINI_API_KEY_LOCAL", "clave-de-prueba")  # para importar sin .env (no se llama a Gemini)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from pydantic_ai import ModelResponse, TextPart, ToolCallPart, ToolReturnPart  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

import api  # noqa: E402
import asistente  # noqa: E402
import bot  # noqa: E402
import capacidades  # noqa: E402
import flujo  # noqa: E402
import mcp_agro  # noqa: E402
from config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def base_temporal(tmp_path, monkeypatch):
    """Cada prueba usa su propia base, no la de datos/."""
    monkeypatch.setattr(capacidades, "DB", tmp_path / "agrobot.db")


def pide(tool: str, args: dict) -> FunctionModel:
    """Un modelo falso: la 1.ª vez pide la tool; cuando recibe su resultado, responde texto."""

    def responder(mensajes, info):
        ultimo = mensajes[-1].parts[-1]
        if isinstance(ultimo, ToolReturnPart):
            return ModelResponse(parts=[TextPart(f"Resultado: {ultimo.content}")])
        return ModelResponse(parts=[ToolCallPart(tool, args)])

    return FunctionModel(responder)


def router_falso(destino: str) -> FunctionModel:
    """Un router de mentira: siempre clasifica el pedido en el destino que le digamos (JSON, como NativeOutput)."""
    return FunctionModel(lambda mensajes, info: ModelResponse(parts=[TextPart(json.dumps({"destino": destino}))]))


@contextmanager
def flujo_falso(destino: str, especialista: FunctionModel):
    """Router y especialista falsos: se prueba el grafo y las tools reales, sin gastar cuota."""
    with ExitStack() as pila:
        pila.enter_context(flujo.router.override(model=router_falso(destino)))
        pila.enter_context(flujo.ESPECIALISTAS[destino].override(model=especialista))
        yield


def test_consultar_cultivo():
    ficha = capacidades.consultar_cultivo("papa")  # una tool es una función normal
    assert ficha["nombre_cientifico"] == "Solanum tuberosum" and "fuente" in ficha
    assert "error" in capacidades.consultar_cultivo("cafe")


def test_calcular_costos_suma_y_desglosa():
    costos = capacidades.calcular_costos("P01")
    assert costos["total_bs"] == 4950
    assert costos["por_categoria_bs"]["semillas"] == 1800
    assert costos["costo_por_hectarea_bs"] == 3300  # 4950 / 1.5 ha
    assert costos["costo_por_kg_bs"] == 0.28  # 4950 / 18000 kg
    assert "error" in capacidades.calcular_costos("P99")


def test_produccion_y_rendimiento():
    p = capacidades.consultar_produccion("P04")  # dos cosechas: 1500 + 1200 kg en 1 ha
    assert p["total_kg"] == 2700 and p["rendimiento_kg_ha"] == 2700
    assert capacidades.consultar_produccion("p01")["rendimiento_kg_ha"] == 12000  # acepta minúsculas


def test_dos_tools_a_la_vez_no_chocan_al_crear_la_base():
    """Bug real: Gemini pidió costos y producción a la vez y ambas intentaron crear la base."""
    assert not capacidades.DB.exists()
    with ThreadPoolExecutor(max_workers=8) as hilos:
        resultados = list(hilos.map(capacidades.calcular_costos, ["P01", "P02"] * 4))
    assert all("error" not in r for r in resultados)


def test_produccion_sin_datos_no_inventa():
    r = capacidades.consultar_produccion("P05")  # el tomate aún no tiene cosechas
    assert "error" in r and "rendimiento_kg_ha" not in r


async def test_registrar_gasto_escribe_en_la_base():
    with flujo_falso("gastos", pide("registrar_gasto", {
        "fecha": "2026-05-02", "parcela_id": "P05", "categoria": "herramientas",
        "descripcion": "Tijeras de podar", "monto": 90,
    })):
        respuesta = await asistente.responder("Anota 90 Bs de tijeras en P05.")
    assert "Gasto registrado" in respuesta
    assert capacidades.calcular_costos("P05")["total_bs"] == 2100  # 2010 del CSV + 90


async def test_gasto_invalido_no_se_guarda():
    malos = [
        {"fecha": "2026-05-02", "parcela_id": "P01", "categoria": "semillas", "descripcion": "x", "monto": -5},
        {"fecha": "ayer", "parcela_id": "P01", "categoria": "semillas", "descripcion": "x", "monto": 5},
        {"fecha": "2026-05-02", "parcela_id": "P99", "categoria": "semillas", "descripcion": "x", "monto": 5},
    ]
    for args in malos:
        with flujo_falso("gastos", pide("registrar_gasto", args)):
            assert "No se guardó" in await asistente.responder("Anota un gasto.")
    assert capacidades.calcular_costos("P01")["total_bs"] == 4950  # nada cambió


async def test_registrar_actividad():
    args = {"fecha": "2026-05-03", "parcela_id": "P02", "tipo": "riego", "descripcion": "Riego por surcos"}
    with flujo_falso("gastos", pide("registrar_actividad", args)):
        assert "Actividad registrada" in await asistente.responder("Regué P02.")
    filas = capacidades.leer("SELECT * FROM actividades WHERE parcela_id = ? AND fecha = ?", ("P02", "2026-05-03"))
    assert len(filas) == 1
    assert "No se guardó" in capacidades.registrar_actividad("31-02-2026", "P02", "riego", "x")


def falso_open_meteo(monkeypatch, con_resultados: bool = True):
    """Reemplaza httpx.get: responde como Open-Meteo, sin internet."""

    def get(url, params=None, timeout=None):
        peticion = httpx.Request("GET", url)
        if "geocoding" in url:
            cuerpo = {"results": [{"name": "Tiraque", "admin1": "Cochabamba", "latitude": -17.4, "longitude": -65.7, "elevation": 3300}]} if con_resultados else {"generationtime_ms": 0.1}
            return httpx.Response(200, json=cuerpo, request=peticion)
        n = params["forecast_days"]
        diario = {
            "time": [f"2026-11-0{i + 1}" for i in range(n)],
            "temperature_2m_max": [18.0] * n, "temperature_2m_min": [3.0] * n,
            "precipitation_sum": [0.0] * n, "precipitation_probability_max": [None] * n,
            "wind_speed_10m_max": [12.0] * n,
        }
        actual = {"temperature_2m": 11.5, "relative_humidity_2m": 60, "precipitation": 0.0, "wind_speed_10m": 8.0}
        return httpx.Response(200, json={"current": actual, "daily": diario}, request=peticion)

    monkeypatch.setattr(capacidades.httpx, "get", get)


def test_clima_con_open_meteo_simulado(monkeypatch):
    falso_open_meteo(monkeypatch)
    clima = capacidades.consultar_clima("Tiraque", dias=2)
    assert clima["lugar"] == "Tiraque, Cochabamba" and clima["fuente"] == "Open-Meteo"
    assert len(clima["pronostico"]) == 2 and clima["ahora"]["temperature_2m"] == 11.5
    assert clima["pronostico"][0]["prob_lluvia_pct"] is None  # sin dato: no se inventa
    assert len(capacidades.consultar_clima("Tiraque", dias=99)["pronostico"]) == 7  # tope de 7 días


def test_clima_localidad_desconocida_pide_precision(monkeypatch):
    falso_open_meteo(monkeypatch, con_resultados=False)
    assert "más específica" in capacidades.consultar_clima("Lugarinexistente")["error"]


async def test_agente_usa_la_tool_de_clima(monkeypatch):
    falso_open_meteo(monkeypatch)
    with flujo_falso("clima", pide("consultar_clima", {"localidad": "Tiraque"})):
        assert "Open-Meteo" in await asistente.responder("¿Cómo estará el clima en Tiraque?")


async def test_chat_ajeno_se_rechaza_sin_llamar_al_modelo(monkeypatch):
    monkeypatch.setattr(settings, "telegram_permitidos", "123")
    respuestas = []

    async def reply_text(texto):
        respuestas.append(texto)

    def modelo_prohibido(mensajes, info):
        raise AssertionError("no debía llamarse al modelo")

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=999), message=SimpleNamespace(text="hola", reply_text=reply_text)
    )
    with flujo.router.override(model=FunctionModel(modelo_prohibido)):
        await bot.mensaje(update, None)
    assert "No autorizado" in respuestas[0] and "999" in respuestas[0]


async def test_start_saluda_solo_a_chats_permitidos(monkeypatch):
    monkeypatch.setattr(settings, "telegram_permitidos", "123")
    respuestas = []

    async def reply_text(texto):
        respuestas.append(texto)

    for chat in (123, 999):
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=chat), message=SimpleNamespace(reply_text=reply_text))
        await bot.inicio(update, None)
    assert "AgroBot" in respuestas[0]
    assert "AgroBot" not in respuestas[1] and "999" in respuestas[1]


async def test_chat_permitido_recibe_la_respuesta_del_flujo(monkeypatch):
    monkeypatch.setattr(settings, "telegram_permitidos", "123")
    respuestas = []

    async def reply_text(texto):
        respuestas.append(texto)

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123), message=SimpleNamespace(text="costos P01", reply_text=reply_text)
    )
    with flujo_falso("gastos", pide("calcular_costos", {"parcela_id": "P01"})):
        await bot.mensaje(update, None)
    assert "4950" in respuestas[0]


def test_permitidos(monkeypatch):
    monkeypatch.setattr(settings, "telegram_permitidos", " 123, 456 ,")
    assert settings.permitidos == {"123", "456"}
    monkeypatch.setattr(settings, "telegram_permitidos", "")
    assert settings.permitidos == set()  # vacío = nadie


# ── S2: manuales (RAG) y búsqueda web ──


def embedding_falso(textos: list[str]) -> list[list[float]]:
    """Embeddings de mentira pero deterministas: cuenta palabras en 128 casillas. Sin red ni cuota."""
    vectores = []
    for texto in textos:
        v = [0.0] * 128
        for palabra in texto.lower().replace(",", " ").replace(".", " ").split():
            v[zlib.crc32(palabra.encode()) % 128] += 1.0
        vectores.append(v)
    return vectores


@pytest.fixture
def rag_sin_gemini(monkeypatch):
    """El RAG de verdad (PDFs, trozos, Chroma) pero con embeddings falsos."""
    monkeypatch.setattr(capacidades, "embeddings_de", embedding_falso)
    capacidades.indice.cache_clear()
    yield
    capacidades.indice.cache_clear()


def test_pdfs_ficticios_indexados_y_citados(rag_sin_gemini):
    assert len(list(capacidades.DOCUMENTOS.glob("*.pdf"))) == 6
    resultados = capacidades.buscar("tizón tardío manchas oscuras en las hojas de la papa", k=3)
    fuentes = [r["fuente"] for r in resultados]
    assert any(f.startswith("guia_control_plagas-") for f in fuentes)  # la cita dice de qué PDF sale


async def test_buscar_manual_agrega_cita(rag_sin_gemini):
    pregunta = "aporque a los 40 o 50 días: se acerca tierra a la base de la planta para proteger los tubérculos"
    with flujo_falso("manuales", pide("buscar_manual", {"pregunta": pregunta})):
        respuesta = await asistente.responder("¿Cuándo se hace el aporque?")
    assert "[PDF: manual_papa-" in respuesta


class TavilyFalso:
    """Reemplaza a AsyncTavilyClient: anota las llamadas y responde lo que le digamos."""

    llamadas: list[dict] = []
    respuestas: list[dict] = []

    def __init__(self, api_key):
        assert api_key == "clave-tavily-de-prueba"

    async def search(self, consulta, **kwargs):
        TavilyFalso.llamadas.append(kwargs)
        return TavilyFalso.respuestas.pop(0)


def hay_tavily(monkeypatch, respuestas: list[dict]):
    TavilyFalso.llamadas, TavilyFalso.respuestas = [], respuestas
    monkeypatch.setattr(settings, "tavily_api_key", SecretStr("clave-tavily-de-prueba"))
    monkeypatch.setattr(capacidades, "AsyncTavilyClient", TavilyFalso)


def un_resultado(url: str) -> dict:
    return {"results": [{"title": "Tizón tardío", "url": url, "content": "x" * 1000, "score": 0.9}]}


async def test_buscar_plagas_separa_pdf_y_web(monkeypatch, rag_sin_gemini):
    hay_tavily(monkeypatch, [un_resultado("https://www.fao.org/tizon")])
    r = await capacidades.buscar_plagas("tizón tardío")
    assert all(m["cita"].startswith("[PDF: ") for m in r["manuales_pdf"])
    assert r["web"][0]["cita"] == "[Web: https://www.fao.org/tizon]" and r["web"][0]["fuente_confiable"] is True
    assert len(r["web"][0]["texto"]) == 600  # se recorta el texto externo
    assert TavilyFalso.llamadas[0]["include_domains"] == capacidades.FUENTES_CONFIABLES  # primero, fuentes técnicas


async def test_buscar_plagas_sin_fuentes_tecnicas_abre_busqueda_y_avisa(monkeypatch, rag_sin_gemini):
    hay_tavily(monkeypatch, [{"results": []}, un_resultado("https://blog-cualquiera.com/tizon")])
    r = await capacidades.buscar_plagas("tizón tardío")
    assert r["web"][0]["fuente_confiable"] is False
    assert "include_domains" not in TavilyFalso.llamadas[1]


async def test_buscar_plagas_sin_clave_igual_devuelve_manuales(monkeypatch, rag_sin_gemini):
    monkeypatch.setattr(settings, "tavily_api_key", SecretStr(""))
    r = await capacidades.buscar_plagas("tizón tardío")
    assert "TAVILY_API_KEY" in r["web"]["error"] and r["manuales_pdf"]


async def test_buscar_plagas_si_tavily_falla_no_rompe(monkeypatch, rag_sin_gemini):
    hay_tavily(monkeypatch, [])  # sin respuestas: search lanza IndexError, como una API caída
    r = await capacidades.buscar_plagas("tizón tardío")
    assert r["web"] == {"error": "No pude consultar la web en este momento."} and r["manuales_pdf"]


# ── S3: servidor MCP de manuales (un subproceso real por stdio, sin modelo ni internet) ──


async def test_mcp_anuncia_solo_dos_tools_de_lectura():
    async with Client(mcp_agro.lanzar_servidor()) as c:
        nombres = {t.name for t in await c.list_tools()}
    assert nombres == {"listar_manuales", "leer_manual"}


async def test_mcp_lista_y_lee_un_manual():
    async with Client(mcp_agro.lanzar_servidor()) as c:
        lista = (await c.call_tool("listar_manuales", {})).structured_content["result"]  # las listas vienen en "result"
        manual = (await c.call_tool("leer_manual", {"nombre": "manual_quinua"})).structured_content
    assert len(lista) == 6 and "manual_quinua" in lista
    assert "saponina" in manual["texto"] and manual["fuente"].startswith("manual_quinua.pdf")


@pytest.mark.parametrize("nombre", ["../.env", "..\\config", "pyproject.toml", "manual_papa.pdf", "/etc/passwd", ""])
async def test_mcp_rechaza_nombres_fuera_de_la_lista(nombre):
    async with Client(mcp_agro.lanzar_servidor()) as c:
        with pytest.raises(ToolError, match="No existe el manual"):  # ToolError sí deja pasar su mensaje
            await c.call_tool("leer_manual", {"nombre": nombre})


async def test_agente_lee_manual_por_mcp():
    with flujo_falso("manuales", pide("leer_manual", {"nombre": "manual_quinua"})):
        respuesta = await asistente.responder("Lee el manual de quinua.")
    assert "saponina" in respuesta


# ── S4: el grafo (router + especialistas) ──

RUTAS = ["clima", "cultivos", "plagas", "gastos", "produccion", "manuales", "general"]


def dice_su_nombre(nombre: str) -> FunctionModel:
    return FunctionModel(lambda mensajes, info: ModelResponse(parts=[TextPart(f"respondió {nombre}")]))


@pytest.mark.parametrize("destino", RUTAS)
async def test_el_grafo_envia_cada_pedido_a_su_especialista(destino):
    with ExitStack() as pila:
        pila.enter_context(flujo.router.override(model=router_falso(destino)))
        for nombre, agente in flujo.ESPECIALISTAS.items():  # todos falsos: solo debe responder el elegido
            pila.enter_context(agente.override(model=dice_su_nombre(nombre)))
        assert await asistente.responder("hola") == f"respondió {destino}"


async def test_el_router_recibe_el_mensaje_y_el_especialista_tambien():
    vistos = {}

    def router(mensajes, info):
        vistos["router"] = mensajes[-1].parts[-1].content
        return ModelResponse(parts=[TextPart(json.dumps({"destino": "cultivos"}))])

    def especialista(mensajes, info):
        vistos["especialista"] = mensajes[-1].parts[-1].content
        return ModelResponse(parts=[TextPart("ok")])

    with flujo.router.override(model=FunctionModel(router)), flujo.ESPECIALISTAS["cultivos"].override(model=FunctionModel(especialista)):
        await asistente.responder("¿Cuándo siembro quinua?")
    assert vistos == {"router": "¿Cuándo siembro quinua?", "especialista": "¿Cuándo siembro quinua?"}


async def test_aislamiento_quien_lee_la_web_no_escribe_y_quien_escribe_no_lee_la_web():
    """La defensa contra órdenes escondidas en textos externos: cada especialista ve solo sus tools."""
    tools = {}
    for nombre, agente in flujo.ESPECIALISTAS.items():

        def ver(mensajes, info, nombre=nombre):
            tools[nombre] = {t.name for t in info.function_tools}
            return ModelResponse(parts=[TextPart("ok")])

        with agente.override(model=FunctionModel(ver)):
            await agente.run("hola")

    escritoras = {"registrar_gasto", "registrar_actividad"}
    de_lectura_externa = {"buscar_plagas", "buscar_manual", "leer_manual", "listar_manuales"}
    assert tools["gastos"] >= escritoras and not tools["gastos"] & de_lectura_externa
    for nombre, nombres in tools.items():
        if nombre != "gastos":
            assert not nombres & escritoras, nombre  # solo "gastos" puede escribir
    assert "buscar_plagas" in tools["plagas"]
    assert tools["general"] == set() and tools["cultivos"] == {"consultar_cultivo"}
    assert tools["produccion"] == {"calcular_costos", "consultar_produccion"}


async def test_si_el_router_falla_el_error_sube_para_que_el_bot_avise():
    def roto(mensajes, info):
        raise RuntimeError("503")

    with flujo.router.override(model=FunctionModel(roto)), pytest.raises(Exception):
        await asistente.responder("hola")


def test_todos_los_especialistas_saben_de_quien_son():
    """La identidad va en PERSONALIDAD, común a todos: da igual qué ruta reciba la pregunta."""
    assert "asistente personal de Melany Chavarria" in flujo.PERSONALIDAD


def test_el_grafo_se_dibuja_con_las_7_rutas():
    diagrama = flujo.grafo.render()
    for ruta in RUTAS:
        assert f"paso_{ruta}" in diagrama


# ── Extra opcional: la API (API.md) ──


async def post_chat(cuerpo: dict, token: str | None = None) -> httpx.Response:
    """Llama a la API en el mismo proceso, sin servidor ni red."""
    cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
    transporte = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://prueba") as cliente:
        return await cliente.post("/chat", json=cuerpo, headers=cabeceras)


async def test_api_sin_token_valido_no_llama_al_modelo(monkeypatch):
    def modelo_prohibido(mensajes, info):
        raise AssertionError("no debía llamarse al modelo")

    with flujo.router.override(model=FunctionModel(modelo_prohibido)):
        monkeypatch.setattr(settings, "api_tokens", SecretStr(""))
        assert (await post_chat({"mensaje": "hola"}, "cualquiera")).status_code == 401  # vacío = nadie
        monkeypatch.setattr(settings, "api_tokens", SecretStr("abc, def"))
        assert (await post_chat({"mensaje": "hola"})).status_code == 401
        assert (await post_chat({"mensaje": "hola"}, "xyz")).status_code == 401
        assert (await post_chat({"mensaje": ""}, "abc")).status_code == 422  # Pydantic valida el pedido


async def test_api_con_token_responde(monkeypatch):
    monkeypatch.setattr(settings, "api_tokens", SecretStr("abc,def"))
    with flujo_falso("gastos", pide("calcular_costos", {"parcela_id": "P01"})):
        r = await post_chat({"mensaje": "¿Cuánto costó la parcela P01?"}, "def")
    assert r.status_code == 200
    assert "4950" in r.json()["texto"]
