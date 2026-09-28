"""Comprueba las reglas de tema y relaciones con títulos reales (python herramientas/probar_reglas.py).

Cada caso: (título, idioma, país de la cámara, ¿ONU?, relaciones esperadas como {ISO3: orientación}).
Sale con error si alguna regla no da lo esperado.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from concordia import relaciones as R  # noqa: E402

CASOS = [
    ("Necessity of ending the economic, commercial and financial embargo imposed by the United States of America against Cuba",
     "en", None, True, {"USA": "negativa", "CUB": "positiva"}),
    ("Situation of human rights in the Islamic Republic of Iran", "en", None, True, {"IRN": "negativa"}),
    ("Israeli practices affecting the human rights of the Palestinian people in the Occupied Palestinian Territory, including East Jerusalem",
     "en", None, True, {"ISR": "negativa", "PSE": "positiva"}),
    ("Territorial integrity of Ukraine", "en", None, True, {"UKR": "positiva", "RUS": "negativa"}),
    ("Situation of human rights in the temporarily occupied territories of Ukraine, including the Autonomous Republic of Crimea and the city of Sevastopol, Ukraine",
     "en", None, True, {"UKR": "positiva", "RUS": "negativa"}),
    ("Status of internally displaced persons and refugees from Abkhazia, Georgia, and the Tskhinvali region/South Ossetia, Georgia",
     "en", None, True, {"GEO": "positiva", "RUS": "negativa"}),
    ("Cooperation between the United Nations and the Shanghai Cooperation Organization", "en", None, True, {}),
    ("Iran Sanctions Relief Review Act", "en", "USA", False, {"IRN": "negativa"}),
    ("Israel Security Assistance Support Act", "en", "USA", False, {"ISR": "positiva"}),
    ("United States-Chile Free Trade Agreement Implementation Act", "en", "USA", False, {"CHL": "positiva"}),
    ("Countering Russian aggression; Taiwan Relations Reinforcement", "en", "USA", False, {"RUS": "negativa", "TWN": "neutra"}),
    ("New Mexico Water Act; Georgia peanut growers", "en", "USA", False, {}),
    ("Puerto Rico Status Act", "en", "USA", False, {}),
    ("Northern Ireland Protocol Bill", "en", "GBR", False, {}),
    ("Convenio entre el Reino de España y la República de Colombia para evitar la doble imposición", "es", "ESP", False, {"COL": "positiva"}),
    ("Proposición no de Ley sobre la condena de la invasión rusa de Ucrania", "es", "ESP", False, {"RUS": "negativa", "UKR": "positiva"}),
    ("Proposición no de Ley relativa al reconocimiento del Estado de Palestina", "es", "ESP", False, {"PSE": "positiva"}),
]
TEMAS = [
    ("Proposición no de Ley relativa al reconocimiento del Estado de Palestina", "es", None),  # «relativa» no es IVA
    ("Department of Defense Appropriations Act", "en", "PRE"),
]


def main():
    fallos = 0
    for titulo, idioma, origen, onu, esperado in CASOS:
        obtenido = {r["pais"]: r["orientacion"] for r in R.relaciones(titulo, idioma, origen, onu)}
        if obtenido != esperado:
            fallos += 1
            print(f"✗ {titulo[:80]}\n    esperado {esperado}\n    obtenido {obtenido}")
    for titulo, idioma, esperado in TEMAS:
        if (t := R.tema(titulo, idioma)) != esperado:
            fallos += 1
            print(f"✗ tema de {titulo[:60]}: esperado {esperado}, obtenido {t}")
    print(f"{len(CASOS) + len(TEMAS) - fallos} de {len(CASOS) + len(TEMAS)} casos bien")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
