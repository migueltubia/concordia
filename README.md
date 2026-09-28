# Concordia

Votaciones parlamentarias del mundo y relaciones entre países: qué vota cada parlamento sobre otros
países (sanciones, tratados, ayuda, condenas…) y cómo vota cada Estado en la Asamblea General de la ONU,
con una ficha de cada asunto (resumen neutro, tema y países afectados con su orientación) y una web que
se abre sin servidor, con un mapa del mundo de relaciones entre países.

Es la versión mundial de [Escrutinio](https://github.com/migueltubia/escrutinio), con la misma
arquitectura: conectores por fuente, base SQLite troceada que cabe en GitHub, fichas hechas con IA solo a
partir del título, reglas deterministas para todo lo demás y una web estática con SQLite en WebAssembly.
Las fuentes salen del estudio `Votaciones parlamentarias en el mundo qué datos hay por país.md`. De
España solo se usa el ámbito nacional (el Congreso, tomado de Escrutinio).

Web publicada (cuando se active GitHub Pages): <https://migueltubia.github.io/concordia/>

Solo usa la biblioteca estándar de Python (3.10 o superior): ni dependencias ni servidor.

## Qué hay

| Fuente | Conector | Años | Detalle | Cómo |
| --- | --- | --- | --- | --- |
| Asamblea General de la ONU | `onu` | 1946–2023 | Voto de cada Estado en cada votación registrada | Dataset de Voeten et al. (Harvard Dataverse, CC0), con título y temas de cada resolución |
| Congreso de los Estados Unidos | `usa` | 2001– | Voto de cada congresista, Cámara y Senado | CSV de [Voteview](https://voteview.com) por Congreso, al día |
| Reino Unido, Cámara de los Comunes | `gbr` | 2016– | Voto de cada diputado en cada división | [Commons Votes API](https://commonsvotes-api.parliament.uk) |
| Polonia, Sejm | `pol` | 2019– | Voto de cada diputado y su club | [API del Sejm](https://api.sejm.gov.pl), legislaturas IX y X |
| España, Congreso de los Diputados | `esp` | 2011– | Voto de cada diputado, con las fichas de Escrutinio | Base troceada del repositorio de Escrutinio |

La tabla de cobertura con las cifras al día está en la ayuda de la web (`#/ayuda`), que la calcula con lo
que hay cargado.

**La ONU después de septiembre de 2023.** La fuente oficial y actualizada es el fichero «General Assembly
voting data» de la [Biblioteca Digital de la ONU](https://digitallibrary.un.org/record/4060887). Su web
responde a los programas con un reto anti-robots (AWS WAF), igual que press.un.org, y no se intenta
saltar: la recogida lo anota como aviso y la web lo dice. Para completar esos años basta descargar el CSV
desde el navegador, dejarlo en `data/raw/onu/undl/` y ejecutar `python -m concordia actualizar --fuente onu`:
el conector importa todo lo posterior a septiembre de 2023.

### Lo comprobado del estudio de fuentes

Al montar los conectores (28 de septiembre de 2026) se comprobó el estudio con descargas reales:

- **ONU.** El CSV oficial de la Biblioteca Digital y las notas de prensa de press.un.org responden con un
  reto anti-robots a cualquier programa. UNGA-DM (Ginebra, CC BY) se descarga bien, pero su extracto de
  votos llega a mediados de 2023 y no trae el título de las resoluciones (su API pide identificarse). El
  dataset de Voeten (versión 32) sí trae títulos y temas, y cubre hasta septiembre de 2023 (fin de la
  sesión 77): es la base histórica. Las versiones posteriores de ese dataset solo publican puntos ideales
  y afinidades, no los votos.
- **EEUU.** Voteview está al día (votaciones de la semana anterior) y publica un CSV por Congreso y cámara.
- **Reino Unido.** La API de los Comunes responde con 403 si la cabecera User-Agent lleva caracteres no
  ASCII; con una cabecera ASCII funciona. Empieza en 2016, como decía el estudio.
- **Polonia.** La API del Sejm da las legislaturas IX y X, con una petición por votación (unas 14.000).
- **España.** Se reutiliza la base troceada de Escrutinio desde su repositorio público.

## La web

Abre `web/index.html` (con doble clic, o publicada en GitHub Pages). Igual que en Escrutinio, el navegador
carga SQLite compilado a WebAssembly ([sql.js](https://github.com/sql-js/sql.js), MIT) y la página hace
sus consultas SQL sobre la base en memoria. El mapa usa [d3-geo](https://d3js.org/d3-geo) y
topojson-client (ISC) con la geometría de [world-atlas](https://github.com/topojson/world-atlas) (Natural
Earth, dominio público), todo en `web/vendor/`.

El mapa se centra en el país de origen (o en el de referencia) para que las flechas vayan por el camino
corto, amplía con la rueda del ratón, el doble clic o el pellizco, rotula los países principales sin que
se solapen y resalta las relaciones del país o la flecha que hay bajo el puntero.

La cabecera tiene dos selectores que valen para todas las vistas y van en la URL: el **país** (`p=ESP`) y
los **años** (`a=2021-2026`). Se filtra por años naturales y no por legislaturas, porque cada país tiene
las suyas.

| Sección | Qué responde |
| --- | --- |
| Mundo · Orientación | Mapa con flechas origen → destino: lo que el parlamento de un país aprueba sobre otro y cómo vota cada Estado en la ONU las resoluciones sobre otro. Color por saldo (azul positivo, rojo negativo, gris repartido), grosor por número de asuntos o votos. Filtros de origen, destino (varios, o pulsando en el mapa), vía (leyes u ONU), orientación, tema, tipo de relación y años. Cada flecha abre los asuntos que hay detrás |
| Mundo · Afinidad en la ONU | Coropletas de cuánto coincide el voto de un país con el de cada uno de los demás, flechas hacia los más y los menos afines, y evolución año a año |
| Mundo · Línea de tiempo | Debajo del mapa, en los dos modos: todo el periodo, año a año o acumulado, con reproducción (▶) y un histograma de relaciones positivas, neutras y negativas por año. El grosor y los colores son comparables entre años |
| Resumen | Cifras del parlamento del país, temas, qué vota sobre otros países, qué votan otros sobre él y con quién vota en la ONU. Si no tiene conector, qué datos publica su parlamento según el estudio de fuentes |
| Votaciones | Buscador de lo votado (por defecto, la votación que decide cada asunto) con ficha, relaciones con otros países, voto por partido y voto nominal |
| Partidos | Afinidad entre partidos del país (en general y por tema) y posición de cada partido por tema |
| En la ONU | El voto del país en la Asamblea: cifras, más y menos afines, evolución frente a otros países y buscador de sus votos |
| Ayuda | Qué es, cómo se lee, fuentes y cobertura, cómo se calcula, qué datos hay de cada país y limitaciones |

## Cómo se relacionan los países

La tabla `relacion` guarda aristas dirigidas **origen → destino** con orientación +1 (positiva), −1
(negativa) o 0 (neutra), y por qué vía:

- **Por ley.** Un asunto del parlamento del país de origen (ley, resolución, moción, tratado) cuya ficha
  dice que otro país es objeto del asunto. La orientación es la del asunto hacia ese país: una ley de
  sanciones es negativa para el sancionado; un convenio para evitar la doble imposición, positiva para el
  otro firmante; una ley de ayuda militar, positiva para quien la recibe. Se toma su votación decisiva y se
  marca si se aprobó (el mapa, por defecto, solo cuenta lo aprobado).
- **Por la ONU.** Cada Estado que vota una resolución sobre otro: votar sí a una resolución negativa para
  el país X (por ejemplo, sobre la situación de los derechos humanos en X) es una arista negativa hacia X;
  votar no, positiva. Las abstenciones y ausencias no cuentan.

La **afinidad en la ONU** es la medida habitual en los estudios sobre la Asamblea: en las votaciones
finales de cada año, 1 punto si dos Estados votan igual, ½ si uno se abstiene y el otro no, 0 si votan lo
contrario. Se guarda por año y par de Estados (`afinidad_onu`), así que se puede sumar cualquier periodo.

Quién decide qué países son objeto de un asunto y en qué sentido:

1. **La IA (DeepSeek)**, en la ficha de cada asunto, solo a partir del título y los metadatos (nunca de
   los votos), con una lista cerrada de tipos de relación y códigos ISO validados. Sabe, por ejemplo, que
   «Territorial integrity of Ukraine» es negativa para Rusia aunque el título no la nombre.
2. **Reglas** (`concordia/relaciones.py`), mientras no hay ficha: países nombrados en el título (en inglés
   o en español, con gentilicios y formas ambiguas como «Georgia» o «Jordan» tratadas aparte), orientación
   por palabras clave del tramo de la frase donde aparece cada país, víctima y agresor («invasión rusa de
   Ucrania»), y patrones propios de los títulos de la ONU («Situation of human rights in X», «embargo
   imposed by X against Y», prácticas israelíes en los territorios ocupados…). Los títulos en polaco no se
   leen con reglas.

Cada relación dice de dónde sale (`metodo`), y la web lo muestra.

## Almacenamiento: una SQLite por fuente y año

GitHub rechaza ficheros de más de 100 MB y la base de trabajo pasa de 1 GB (el voto de cada congresista de
EEUU desde 2001 y el de cada Estado en la ONU desde 1946). Lo que se versiona es `data/bd/`, troceado por
**fuente y año**, que es la unidad estable (un año cerrado no cambia) y la misma con la que se filtra en la
web:

| Fichero | Contenido |
| --- | --- |
| `data/bd/comun.sqlite` | Partidos de cada fuente |
| `data/bd/estado.json` | Marcas de la recogida incremental de cada fuente y últimos errores (texto, para ver los cambios) |
| `data/bd/<fuente>/<año>.sqlite` | Todo lo de un año de una fuente (`usa/2025.sqlite`, `onu/1986.sqlite`…): asuntos votados ese año con su ficha, votaciones, voto por partido, relaciones, afinidades y el voto nominal compacto |
| `data/bd/manifiesto.json` | Huella de cada fichero |

El voto nominal va compacto, como en Escrutinio: por cada votación, una cadena con el sentido de cada
miembro de la plantilla del año (`S` sí, `N` no, `A` abstención, `-` no vota, `.` no estaba) y otra con su
partido. Un asunto votado en dos años va en los dos ficheros. `partir` solo reescribe los ficheros que
cambian y `unir` reconstruye la base de trabajo (`data/concordia.sqlite`, que no se versiona).

La web va troceada igual, en `web/datos/`: `comun.js` (países, fuentes, partidos, cobertura),
`<fuente>/<año>.js` (lo que usan las vistas de país) y `mundo/<año>.js` (la capa ligera del mapa: relaciones
de ese año con el título y el resumen de cada asunto, y la afinidad en la ONU). La página solo descarga lo
que pide cada vista: el país y los años elegidos.

## Uso

```bash
python -m concordia unir          # base de trabajo desde data/bd/
python -m concordia actualizar    # todo el ciclo: recogida, fichas IA si hay clave, procesado, web y partir
python -m concordia estado        # resumen de la base de trabajo
```

Pasos sueltos:

```bash
python -m concordia recoger [--fuente usa,gbr] [--completo]   # conectores (y procesado de lo recogido)
python -m concordia probar <fuente> [--desde 2025]            # probar un conector sin tocar la base
python -m concordia procesar [--fuente onu] [--anios 2020-2023]
python -m concordia fichas-deepseek --limite 100              # fichas IA (DEEPSEEK_API_KEY)
python -m concordia fichas-exportar --limite 500              # pendientes para procesarlos por otra vía
python -m concordia fichas-importar "respuestas/*.jsonl" --modelo <modelo>
python -m concordia web / partir
```

El catálogo de países (`concordia/datos/paises.json`: códigos ISO, nombres en español, regiones M49 de la
ONU y centroides) y el mapa (`web/vendor/mundo.js`) se generan una vez con
`python herramientas/generar_paises.py`.

## Actualizar: en la nube o en local

Como en Escrutinio, la actualización es un solo programa (`python -m concordia actualizar`) y da igual
quién lo lance: GitHub Actions cada día o cualquiera con el repositorio clonado.

| Workflow | Cuándo | Qué hace |
| --- | --- | --- |
| `actualizar.yml` | Cada día a las 05:10 UTC; el domingo, además, guarda la base | `actualizar`, commit de `data/llm` (y los domingos y a mano, de `data/bd` y `web/datos`) y publicación de la web con los datos del día |
| `pages.yml` | Al subir cambios de `web/` y a mano | Publica `web/` en GitHub Pages |

Configuración, una vez: *Settings > Pages > Source*: **GitHub Actions**; *Settings > Secrets and
variables > Actions*: secreto `DEEPSEEK_API_KEY` y, opcional, variable `DEEPSEEK_MODEL` (por defecto
`deepseek-flash`). Sin clave se actualiza todo menos las fichas IA, y los asuntos nuevos quedan con la
ficha por reglas.

En local: `git pull`, `python -m concordia unir`, `python -m concordia actualizar`, `git add data/bd
web/datos data/llm`, commit y push enseguida. La clave va en `.env` (copiar `.env.ejemplo`), que no se sube.
Las mismas reglas que en Escrutinio para no chocar con Actions: pull justo antes, push justo después.

Cada día se hacen hasta 300 fichas (primero las de los años más recientes, repartidas entre fuentes).
Todo lo que devuelve la IA se guarda en `data/llm/fichas/<fuente>/<mes>.jsonl` y
`data/llm/relaciones/<fuente>/<mes>.jsonl`, que son la fuente de verdad: reconstruir la base no vuelve a
llamar a la IA. En España, las fichas (resumen y tema) son las de Escrutinio y la IA solo añade las
relaciones de los asuntos que pueden tenerlas.

## Añadir un país

Un módulo en `concordia/fuentes/` con `FUENTE` (código, país, cámaras, partidos, año de inicio, idioma de
los títulos) y `recoger(ctx)`, que devuelve asuntos y votaciones normalizados
(`concordia/fuentes/modelo.py`) con `ctx.guardar(asuntos, votaciones)`, y una línea en
`concordia/fuentes/__init__.py`. Guardar, calcular totales, voto por partido, votación decisiva, fichas por
reglas, relaciones y afinidades es común. Se prueba con `python -m concordia probar <código>`.

Los siguientes candidatos, por el estudio de fuentes (dificultad 1): Suecia, Irlanda, Francia, Países
Bajos (por grupo), Brasil, Corea del Sur y el Parlamento Europeo (HowTheyVote.eu). La ayuda de la web tiene
la tabla completa por país.

## Limitaciones

- Solo cuenta lo que se vota con votación registrada: lo aprobado por consenso o a mano alzada no aparece.
- La relación «por ley» solo tiene como origen los países con conector; el resto aparece como destino y
  en la ONU.
- La ONU llega hasta septiembre de 2023 mientras la fuente oficial no deje descargar los datos (ver arriba).
- La orientación sale del título: la IA puede equivocarse con títulos poco informativos y las reglas solo
  ven lo que el título dice. Cada relación dice quién la decidió y enlaza al texto oficial.
- En EEUU, «aprobado» es aprobado en la votación final de al menos una cámara, no que sea ley.
- En el Reino Unido, un proyecto de ley cuyas votaciones cruzan el cambio de año cuenta como dos asuntos.

## Licencia

Código bajo licencia MIT (`LICENSE`). sql.js es MIT; d3-geo, d3-array, topojson-client y world-atlas son
ISC; los datos de Natural Earth son de dominio público. Los datos de votaciones proceden de sus fuentes,
enlazadas desde cada votación: Voeten et al. (CC0), Voteview, UK Parliament (Open Parliament Licence),
Sejm RP y Congreso de los Diputados vía Escrutinio.
