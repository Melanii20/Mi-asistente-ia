"""AgroBot: el router y los especialistas viven en flujo.py (S4); aquí está la puerta de entrada.

Pruébalo en la terminal, sin Telegram:  uv run asistente.py
"""

import asyncio

from flujo import ESPECIALISTAS, Consulta, grafo

asistente = ESPECIALISTAS["general"]  # el agente principal: charla y explica qué hace AgroBot


async def responder(mensaje: str) -> str:
    """Lo único que necesita el bot: un mensaje entra, una respuesta sale. El grafo decide quién responde."""
    return await grafo.run(state=Consulta(), inputs=mensaje)  # await: mientras espera, el bot atiende a otros


async def main() -> None:
    while (mensaje := input("tú> ").strip()) not in {"", "salir"}:
        print("asistente>", await responder(mensaje))


if __name__ == "__main__":
    asyncio.run(main())  # un solo asyncio.run: todo lo async vive dentro
