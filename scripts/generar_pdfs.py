"""Genera los PDFs ficticios de datos/documentos/ (material académico, no oficial).

Solo se usa para crear los documentos de práctica; el bot no lo importa.
    uv run scripts/generar_pdfs.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SALIDA = Path(__file__).resolve().parent.parent / "datos" / "documentos"
AVISO = (
    "Material académico ficticio elaborado para el curso «Más allá de los chatbots». "
    "No es una publicación oficial ni reemplaza la asesoría de un ingeniero agrónomo."
)

# Cada documento: nombre de archivo -> (título, [(sección, texto), ...])
DOCUMENTOS = {
    "manual_papa": (
        "Manual del cultivo de papa (ficticio)",
        [
            ("Condiciones del cultivo", "La papa se adapta a zonas de valle alto y altiplano, entre 2800 y 4000 msnm, con temperaturas de 10 a 18 grados. Prefiere suelos sueltos, profundos y bien drenados. Las heladas tempranas dañan el follaje y reducen el rendimiento."),
            ("Siembra", "En la zona andina se siembra entre octubre y noviembre, al inicio de las lluvias. Se usa semilla sana y de tamaño mediano, con distancia de 30 cm entre plantas y 80 cm entre surcos. La semilla certificada reduce el riesgo de enfermedades."),
            ("Labores culturales", "El aporque se hace a los 40 o 50 días: se acerca tierra a la base de la planta para proteger los tubérculos del sol y de las plagas. Se acompaña con un deshierbe manual para controlar las malezas."),
            ("Riego y cosecha", "La papa necesita humedad constante durante la tuberización, pero el exceso de agua favorece enfermedades. El ciclo dura cerca de 150 días. La cosecha se hace cuando el follaje se seca, entre abril y mayo, y los tubérculos se dejan secar a la sombra antes de almacenarlos."),
            ("Rendimiento referencial", "En este material ficticio se toma como referencia 12000 kg por hectárea con buen manejo. El rendimiento real depende de la semilla, el clima y la fertilización."),
        ],
    ),
    "manual_maiz": (
        "Manual del cultivo de maíz (ficticio)",
        [
            ("Condiciones del cultivo", "El maíz se produce en valles entre 1800 y 3000 msnm, con temperaturas de 15 a 25 grados. Necesita suelos fértiles y profundos. Es sensible a la falta de agua durante la floración."),
            ("Siembra", "Se siembra entre septiembre y octubre, con 2 o 3 semillas por golpe, a 30 cm entre plantas y 80 cm entre surcos. Se necesitan unos 20 kg de semilla por hectárea."),
            ("Fertilización", "El maíz responde bien al nitrógeno. Se recomienda aplicar la mitad del abono nitrogenado a la siembra y el resto cuando la planta tiene 40 o 50 cm de altura, antes de la floración."),
            ("Riego y malezas", "El riego en la floración y el llenado del grano es el más importante. El deshierbe se hace durante los primeros 40 días, cuando la competencia con las malezas causa más pérdida."),
            ("Cosecha", "El ciclo dura cerca de 180 días. Se cosecha entre marzo y abril, cuando las hojas de la mazorca están secas. Las mazorcas se secan al sol hasta que el grano baje a 14 por ciento de humedad para guardarlo sin hongos."),
            ("Rendimiento referencial", "En este material ficticio se toma como referencia 3000 kg de grano seco por hectárea."),
        ],
    ),
    "manual_quinua": (
        "Manual del cultivo de quinua (ficticio)",
        [
            ("Condiciones del cultivo", "La quinua crece en el altiplano y los valles altos, entre 3000 y 4000 msnm, con temperaturas de 8 a 18 grados. Tolera la sequía y los suelos pobres, pero sufre con heladas durante la floración."),
            ("Siembra", "Se siembra entre septiembre y octubre, en surcos o al voleo, con unos 10 kg de semilla por hectárea. Se necesita una cama de siembra bien mullida y semilla de calidad."),
            ("Labores culturales", "El raleo se hace cuando las plantas tienen 15 a 20 cm, dejando una planta cada 10 o 15 cm. Se acompaña con el deshierbe. El guano de camélidos aporta nutrientes y mejora el suelo."),
            ("Cosecha y poscosecha", "El ciclo dura cerca de 160 días. Se corta la planta cuando las hojas amarillean y el grano está duro. Se seca en parvas, se trilla sobre lonas y se limpia. El grano contiene saponina, que se elimina lavándolo o escarificándolo antes de comerlo."),
            ("Rendimiento referencial", "En este material ficticio se toma como referencia 1100 kg por hectárea."),
        ],
    ),
    "guia_control_plagas": (
        "Guía de control de plagas y enfermedades (ficticia)",
        [
            ("Principio general", "Una plaga no se diagnostica solo con una foto o una descripción. Observa varias plantas, anota qué parte está dañada y consulta a un técnico agrónomo antes de aplicar productos."),
            ("Tizón tardío de la papa", "Se presenta con lluvias y alta humedad. Aparecen manchas oscuras en las hojas y pudrición en los tubérculos. Para reducir el riesgo: usar semilla sana, evitar el exceso de riego, mejorar el drenaje y retirar las plantas enfermas."),
            ("Gorgojo de los Andes", "Es un insecto que daña los tubérculos de la papa con galerías. Se previene rotando cultivos, eliminando restos de cosecha y cosechando a tiempo."),
            ("Mancha chocolate del haba", "Aparecen manchas marrones en hojas y tallos cuando hay humedad alta. Ayuda sembrar con más distancia, evitar el exceso de nitrógeno y rotar el cultivo."),
            ("Mildiu de la quinua", "Produce manchas amarillentas en las hojas y se favorece con humedad. Se reduce con densidad de siembra adecuada, variedades tolerantes y buena aireación del campo."),
            ("Manejo integrado", "Combina prácticas: rotación de cultivos, semilla sana, monitoreo semanal, control de malezas y uso de productos solo cuando sea necesario, siguiendo las indicaciones de la etiqueta y las normas de SENASAG."),
        ],
    ),
    "guia_fertilizacion": (
        "Guía de fertilización (ficticia)",
        [
            ("Por qué fertilizar", "Las plantas toman del suelo nitrógeno, fósforo y potasio. Si el suelo no los tiene en cantidad suficiente, el rendimiento baja. Lo ideal es hacer un análisis de suelo antes de decidir cuánto aplicar."),
            ("Abonos orgánicos", "El estiércol de oveja, vaca o camélidos y el compost mejoran la estructura del suelo y aportan nutrientes poco a poco. Deben estar bien descompuestos antes de aplicarse. Se incorporan al suelo antes de la siembra."),
            ("Fertilizantes químicos", "La urea aporta nitrógeno y el fosfato diamónico aporta fósforo y nitrógeno. Se aplican en dosis divididas y nunca pegados a la semilla, para no quemarla. Siempre se respeta la dosis recomendada por un técnico."),
            ("Épocas de aplicación", "Una parte se aplica a la siembra y otra durante el crecimiento, por ejemplo en el aporque de la papa o antes de la floración del maíz. Evita aplicar antes de lluvias fuertes, porque el abono se lava."),
            ("Costos", "El fertilizante es uno de los gastos principales. Registrar cada compra en bolivianos permite saber cuánto cuesta producir cada kilo cosechado."),
        ],
    ),
    "buenas_practicas_agricolas": (
        "Buenas prácticas agrícolas (ficticia)",
        [
            ("Rotación de cultivos", "Alternar cultivos distintos en la misma parcela reduce plagas y enfermedades y mantiene la fertilidad. Por ejemplo, después de la papa conviene sembrar haba o quinua."),
            ("Manejo del agua", "Regar temprano en la mañana o al atardecer reduce la pérdida por evaporación. El riego por goteo ahorra agua en cultivos como el tomate. Un exceso de agua también daña las raíces."),
            ("Semilla y suelo", "Usa semilla sana y de buena procedencia. Cuida el suelo con abonos orgánicos, curvas de nivel en pendientes y cobertura para evitar la erosión."),
            ("Seguridad en el trabajo", "Usa guantes, mascarilla y ropa adecuada al manipular productos químicos. Guarda los envases cerrados, lejos de los alimentos y de los niños. No reutilices los envases vacíos."),
            ("Registros", "Anota las siembras, los riegos, las aplicaciones y los gastos. Con registros ordenados puedes calcular costos, comparar campañas y tomar mejores decisiones."),
            ("Cosecha y almacenamiento", "Cosecha en el momento adecuado, en un día seco. Limpia, clasifica y almacena el producto en un lugar ventilado, seco y protegido de roedores."),
        ],
    ),
}


def crear(nombre: str, titulo: str, secciones: list[tuple[str, str]]) -> None:
    estilos = getSampleStyleSheet()
    historia = [Paragraph(titulo, estilos["Title"]), Paragraph(AVISO, estilos["Italic"]), Spacer(1, 12)]
    for seccion, texto in secciones:
        historia += [Paragraph(seccion, estilos["Heading2"]), Paragraph(texto, estilos["BodyText"]), Spacer(1, 6)]
    SimpleDocTemplate(str(SALIDA / f"{nombre}.pdf"), pagesize=A4, title=titulo).build(historia)


if __name__ == "__main__":
    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, (titulo, secciones) in DOCUMENTOS.items():
        crear(nombre, titulo, secciones)
        print("creado", nombre + ".pdf")
