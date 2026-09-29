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

Solo usa la biblioteca estándar de Python (3.10 o superior): ni dependencias ni servidor (salvo Playwright,
opcional, para descargar la ONU reciente).

## Qué hay

| Fuente | Conector | Años | Detalle | Cómo |
| --- | --- | --- | --- | --- |
| Asamblea General de la ONU | `onu` | 1946–2025 | Voto de cada Estado en cada votación registrada | Hasta septiembre de 2023, dataset de Voeten et al. (Harvard Dataverse, CC0), con título y temas de cada resolución; después, fichero oficial de la [Biblioteca Digital de la ONU](https://digitallibrary.un.org/record/4060887) |
| Congreso de los Estados Unidos | `usa` | 2001– | Voto de cada congresista, Cámara y Senado | CSV de [Voteview](https://voteview.com) por Congreso, al día |
| Reino Unido, Cámara de los Comunes | `gbr` | 2016– | Voto de cada diputado en cada división | [Commons Votes API](https://commonsvotes-api.parliament.uk) |
| Polonia, Sejm | `pol` | 2019– | Voto de cada diputado y su club | [API del Sejm](https://api.sejm.gov.pl), legislaturas IX y X |
| España, Congreso de los Diputados | `esp` | 2011– | Voto de cada diputado, con las fichas de Escrutinio | Base troceada del repositorio de Escrutinio |
| Alemania, Bundestag | `deu` | 2019– | Voto de cada diputado, solo en las votaciones nominales (unas 50 al año) | Lista oficial del [Bundestag](https://www.bundestag.de/parlament/plenum/abstimmung/liste) (XLSX) cruzada con la API de [abgeordnetenwatch.de](https://www.abgeordnetenwatch.de/api) (CC0) |
| Argentina, Diputados y Senado | `arg` | 2019– | Voto de cada diputado y senador | Diputados: espejo diario de [¿Cómo Votó?](https://github.com/rquiroga7/como_voto) (la web oficial bloquea); Senado: actas de senado.gob.ar; títulos de los datos abiertos de la HCDN |
| Brasil, Cámara y Senado | `bra` | 2019– | Voto de cada diputado y senador en las votaciones nominales | Ficheros anuales de [dadosabertos.camara.leg.br](https://dadosabertos.camara.leg.br) y API del Senado |
| Canadá, Cámara de los Comunes | `can` | 2019– | Voto de cada diputado | XML y CSV de [ourcommons.ca](https://www.ourcommons.ca/members/en/votes), títulos de LEGISinfo |
| Chequia, Cámara de Diputados | `cze` | 2019– | Voto de cada diputado | ZIP de [datos abiertos de psp.cz](https://www.psp.cz/sqw/hp.sqw?k=1300); qué se vota, del estenograma |
| Chile, Cámara y Senado | `chl` | 2019– | Voto de cada diputado y senador | Servicios de opendata.camara.cl y tramitacion.senado.cl; militancia de los senadores, de la BCN |
| Dinamarca, Folketing | `dnk` | 2019– | Voto de cada diputado | [OData oda.ft.dk](https://oda.ft.dk) |
| Estonia, Riigikogu | `est` | 2019– | Voto de cada diputado | [API del Riigikogu](https://api.riigikogu.ee) (una petición por segundo) |
| Finlandia, Eduskunta | `fin` | 2019– | Voto de cada diputado | [API del Eduskunta](https://api.eduskunta.fi) |
| Francia, Asamblea Nacional | `fra` | 2019– | Voto de cada diputado en los scrutins publics | [Datos abiertos de la Asamblea](https://data.assemblee-nationale.fr), legislaturas XV a XVII |
| Irlanda, Dáil y Seanad | `irl` | 2019– | Voto de cada miembro en cada división | [API del Oireachtas](https://api.oireachtas.ie) |
| Israel, Knesset | `isr` | 2019– | Voto de cada diputado | [OData de la Knesset](https://knesset.gov.il/OdataV4/ParliamentInfo/). **Inactivo**: sin probar de principio a fin (ver abajo) |
| México, Cámara de Diputados | `mex` | 2019– | Voto de cada diputado | [Gaceta Parlamentaria](https://gaceta.diputados.gob.mx) (el SITL no sirve su cadena de certificados; el Senado tiene un reto anti-robots) |
| Noruega, Storting | `nor` | 2019– | Voto de cada diputado (las unánimes sin pulsadores, solo el resultado) | [API data.stortinget.no](https://data.stortinget.no) (unas 100 peticiones por minuto) |
| Países Bajos, Tweede Kamer | `nld` | 2019– | Voto de cada grupo (nominal en las pocas votaciones hoofdelijk) | [OData de la Tweede Kamer](https://opendata.tweedekamer.nl) (CC0) |
| Suecia, Riksdag | `swe` | 2019– | Voto de cada diputado en las votaciones con recuento | Descargas por periodo de sesiones de [data.riksdagen.se](https://data.riksdagen.se); un asunto por punto de informe |
| Suiza, Consejo Nacional | `che` | 2019– | Voto de cada diputado | [OData del Parlamento](https://ws.parlament.ch/odata.svc/) |
| Ucrania, Verjovna Rada | `ukr` | 2019 (agosto)– | Voto de cada diputado | Ficheros diarios de [data.rada.gov.ua](https://data.rada.gov.ua/open/data/) (CC BY 4.0), IX convocatoria |
| Parlamento Europeo | `eup` | 2019 (julio)– | Voto de cada eurodiputado en las votaciones nominales, con su grupo europeo y su país | CSV semanal de [HowTheyVote.eu](https://github.com/HowTheyVote/data/releases) (ODbL), sacado de las actas oficiales. Origen de sus relaciones: la Unión Europea (`EUU`) |

La tabla de cobertura con las cifras al día está en la ayuda de la web (`#/ayuda`), que la calcula con lo
que hay cargado.

**La ONU después de septiembre de 2023.** La fuente oficial y actualizada es el fichero «General Assembly
voting data» de la [Biblioteca Digital de la ONU](https://digitallibrary.un.org/record/4060887), del que el
conector importa todo lo posterior a septiembre de 2023 (ahora, hasta diciembre de 2025). Su web responde a
los programas con un reto anti-robots (AWS WAF), igual que press.un.org: si la descarga directa no pasa, el
conector abre un Chrome de verdad con [Playwright](https://playwright.dev/python/) (dependencia opcional:
`pip install playwright` y `playwright install chromium`; en GitHub Actions va con `xvfb-run`), saca el
enlace al CSV y lo descarga con sus cookies. Sin Playwright, o si falla, basta descargar el CSV desde el
navegador, dejarlo en `data/raw/onu/undl/` y ejecutar `python -m concordia actualizar --fuente onu`; los CSV
que haya en esa carpeta tienen prioridad sobre la descarga.

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

El 29 de septiembre de 2026 se añadieron 18 parlamentos más. Lo que difiere del estudio o de la fuente
oficial:

- **Argentina.** votaciones.hcdn.gob.ar no completa la conexión TLS desde fuera del país y desde julio de
  2026 pide reCAPTCHA; el dataset de votaciones nominales de datos.hcdn.gob.ar se queda en 2019. Diputados
  sale del espejo de ¿Cómo Votó? (todas las actas oficiales en un JSON, MIT, actualizado a diario); si ese
  espejo se para, Diputados se para. El Senado sí publica el voto nominal en HTML (no solo en PDF).
- **Alemania.** abgeordnetenwatch solo tiene 4 de cada 5 votaciones nominales; la lista oficial tiene todas
  desde mediados de 2019 (las de enero a junio de 2019 son XLS binario y salen de abgeordnetenwatch). Las
  votaciones a mano alzada no tienen voto por grupo estructurado (DIP lo da en texto libre y pide clave).
- **Brasil.** Solo las votaciones nominales tienen votos; de las simbólicas se guardan, sin votos, las que
  deciden un tratado (casi todos se aprueban así) o un asunto que ya tiene alguna nominal.
- **Chile y Noruega.** Sus servidores usan raíces (emSign, Buypass) que el almacén de Windows no tiene hasta
  que las descarga: en Windows hay que poner `SSL_CERT_FILE` en `.env` (ver `.env.ejemplo`). En Linux y en
  Actions no hace falta. El servidor de la Cámara de Chile tarda unos 4 s por petición.
- **Finlandia.** Se usa la API nueva (api.eduskunta.fi), que sustituye a avoindata.eduskunta.fi antes de que
  acabe 2026 y da cada votación completa en una búsqueda.
- **Israel.** El identificador de diputado de los votos sí coincide con el de KNS_Person. Durante la
  exploración, el cortafuegos de knesset.gov.il bloqueó la IP con HTTP 474; el conector queda inactivo
  (`activa=False`) hasta que `python -m concordia probar isr --desde 2026` termine bien.
- **México.** El SITL no envía el certificado intermedio y el Senado está tras un reto anti-robots; la Gaceta
  Parlamentaria da el voto de cada diputado (sin identificador: se usa el nombre).
- **Suecia.** Solo hay votación nominal cuando algún grupo mantiene su reserva: casi todo son puntos de
  informes de comisión que rechazan mociones, y en ellos «aprobado» es el rechazo (el título lo dice).
- **Suiza.** El Consejo de los Estados no publica su voto nominal en el servicio de datos. En el Consejo
  Nacional se vota a menudo la propuesta de la mayoría de rechazar un objeto; el conector da la vuelta a esos
  votos para que «sí» sea siempre a favor del objeto, y el texto de la votación lo dice.
- **Ucrania.** rada4you ya no existe. La facción de cada diputado es la actual, no la del día de la
  votación, porque la Rada la recodifica en todo el histórico.
- **Corea del Sur y Australia** piden una clave (gratuita); **Italia** bloqueaba con CAPTCHA en el estudio.
  Quedan para más adelante.

**El Parlamento Europeo** se añadió el mismo día, con los datos de HowTheyVote.eu:

- **Qué se descarga.** Cada sábado sale una versión en GitHub con un CSV por tabla. `member_votes.csv.gz`
  (68 MB, unos 18 millones de votos desde julio de 2019) trae el país y el grupo de cada eurodiputado en cada
  votación; `votes.csv.gz`, el procedimiento del Observatorio Legislativo (OEIL), el título en inglés y el
  resultado, y `geo_area_votes.csv.gz`, los países de los que trata cada votación. La API solo lista las
  votaciones finales y va de una en una, así que no se usa. Sin versión nueva no se descarga nada; con una
  nueva se vuelven a guardar los dos últimos meses.
- **Cómo encaja en el modelo.** El asunto es el procedimiento OEIL («2026/2874(RSP)») y el partido, el grupo
  europeo. El país de cada eurodiputado va en su id (`eup:ESP:257043`): así se ve cómo vota cada delegación
  nacional sin cambiar el esquema. Las relaciones «por ley» salen de la **Unión Europea** (`EUU`, el código
  del Banco Mundial), que está en el catálogo de países solo como origen: no tiene alias (las reglas no la
  buscan en los títulos), la validación de la IA la rechaza como destino y en el mapa es un punto en
  Estrasburgo. Lo que el PE vota sobre un Estado miembro (el Estado de derecho en Hungría) es una relación
  UE → Hungría.
- **Lo que difiere de lo esperado.** El resultado solo viene desde 2024: antes se calcula con los totales.
  Lo que se vota viene en francés (las actas nominales) y se traduce lo más frecuente. El número de enmienda
  vale «§» en las votaciones por partes de un párrafo, que no son enmiendas. La Izquierda aparece con dos
  códigos (`GUE_NGL_1995_0` hasta 2021).
- **Los países de HowTheyVote** (`geo_area_votes`, en `asunto.extra.paises`) entran en las relaciones: en las
  reglas, como neutros si el título no los orienta, y en la IA, como pista. En 577 de los 803 asuntos que los
  tienen coinciden con los que las reglas sacan del título; en el resto añaden sobre todo países que el título
  no nombra (China en Hong Kong, Rusia en la ayuda a Ucrania) o nombra de forma ambigua (Georgia, Jordania).
- **Tamaño.** De 7 a 10 MB por año en `data/bd/eup/` con unas 2.500 votaciones (2020 y 2021 tienen más de
  5.000: unos 15 MB) y cerca de 1,4 GB en la base de trabajo. En la web, 1 MB por cada 2.500 votaciones. La
  primera recogida completa tarda unos cuartos de hora; las semanales, poco más que la descarga.

## La web

Abre `web/index.html` (con doble clic, o publicada en GitHub Pages). Igual que en Escrutinio, el navegador
carga SQLite compilado a WebAssembly ([sql.js](https://github.com/sql-js/sql.js), MIT) y la página hace
sus consultas SQL sobre la base en memoria. El mapa usa [d3-geo](https://d3js.org/d3-geo) y
topojson-client (ISC) con la geometría de [world-atlas](https://github.com/topojson/world-atlas) (Natural
Earth, dominio público), todo en `web/vendor/`.

El mapa se centra en el país de origen (o en el de referencia) para que las flechas vayan por el camino
corto, amplía con Ctrl + rueda, el doble clic o el pellizco (la rueda sola desplaza la página), se acerca
al par elegido cuando hay origen y destino, rotula los países principales sin que se solapen y resalta las
relaciones del país o la flecha que hay bajo el puntero. La portada ofrece preguntas para empezar, y el
detalle de una votación o de una flecha va en la URL (`v=`, `par=`) para poder enlazarlo.

La cabecera tiene dos selectores que valen para todas las vistas y van en la URL: el **país** (`p=ESP`) y
los **años** (`a=2021-2026`). Se filtra por años naturales y no por legislaturas, porque cada país tiene
las suyas.

| Sección | Qué responde |
| --- | --- |
| Mundo · Orientación | Mapa con flechas origen → destino: lo que el parlamento de un país aprueba sobre otro y cómo vota cada Estado en la ONU las resoluciones sobre otro. Color por saldo (azul positivo, rojo negativo, gris repartido), grosor por número de asuntos o votos. Filtros de origen, destino (varios, o pulsando en el mapa), vía (leyes u ONU), orientación, tema, tipo de relación y años. Cada flecha abre los asuntos que hay detrás |
| Mundo · Afinidad en la ONU | Coropletas de cuánto coincide el voto de un país con el de cada uno de los demás, flechas hacia los más y los menos afines, y evolución año a año |
| Mundo · Línea de tiempo | Debajo del mapa, en los dos modos: todo el periodo, año a año o acumulado, con reproducción (▶) y un histograma de relaciones positivas, neutras y negativas por año. El grosor y los colores son comparables entre años |
| Resumen | Cifras del parlamento del país, temas, qué vota sobre otros países, qué votan otros sobre él y con quién vota en la ONU. Si no tiene conector, qué datos publica su parlamento según el estudio de fuentes |
| Votaciones | Buscador de lo votado (por defecto, un asunto por fila con su votación decisiva; los puntos votados por separado se agrupan) con ficha, relaciones con otros países, voto por partido y voto nominal |
| Partidos | Afinidad entre partidos del país (en general y por tema, ordenados por bloques), cómo vota cada partido sobre otros países y apoyo por tema frente a su media |
| En la ONU | El voto del país en la Asamblea: cifras, más y menos afines, evolución frente a otros países y buscador de sus votos |
| En el PE | Cómo votan los eurodiputados del país: participación, unidad de la delegación, coincidencia con el resultado, voto por grupo europeo y con su grupo, delegaciones más y menos afines, cada eurodiputado y buscador de votaciones con el voto de la delegación. Con «Unión Europea» elegida, todas las delegaciones comparadas; la UE tiene además Resumen, Votaciones y Partidos (los grupos) como cualquier parlamento |
| Ayuda | Qué es, cómo se lee, fuentes y cobertura, cómo se calcula, qué datos hay de cada país y limitaciones |

## Cómo se relacionan los países

La tabla `relacion` guarda aristas dirigidas **origen → destino** con orientación +1 (positiva), −1
(negativa) o 0 (neutra), y por qué vía:

- **Por ley.** Un asunto del parlamento del país de origen (ley, resolución, moción, tratado) cuya ficha
  dice que otro país es objeto del asunto. La orientación es la del asunto hacia ese país: una ley de
  sanciones es negativa para el sancionado; un convenio para evitar la doble imposición, positiva para el
  otro firmante; una ley de ayuda militar, positiva para quien la recibe. Se toma su votación decisiva y se
  marca si se aprobó (el mapa, por defecto, solo cuenta lo aprobado). Lo que aprueba el Parlamento Europeo
  tiene como origen la Unión Europea (`EUU`), también cuando trata de un Estado miembro; la UE nunca es
  destino (`paises.solo_origen`).
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
   Ucrania», «ofensiva de Israel en Gaza»), apoyo explícito («Standing with Israel»), conflictos conocidos
   (Rusia–Ucrania, Rusia–Georgia, Israel–Palestina: «abduction of children from Ukraine» o «genocidio en
   Gaza» son favorables a la víctima y contrarios al agresor aunque no se le nombre) y patrones propios de
   los títulos de la ONU («Situation of human rights in X», «embargo imposed by X against Y», prácticas
   israelíes en los territorios ocupados…). Los títulos sobre Hamás o Hezbolá no cuentan como relación con
   Palestina o el Líbano. Los títulos en polaco no se leen con reglas.

Si la fuente dice de qué países trata cada asunto (`asunto.extra["paises"]`; hoy, HowTheyVote en el
Parlamento Europeo), esos países se suman a los del título como neutros: la fuente dice de qué país trata,
no en qué sentido, y el título manda si también lo nombra. La IA los recibe como `paises_fuente` y decide su
orientación.

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
python -m concordia fichas-deepseek --limite 100 --hilos 4    # fichas IA (DEEPSEEK_API_KEY), varias llamadas a la vez
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
| `actualizar.yml` | Cada día a las 05:10 UTC; el domingo, además, guarda la base | `actualizar`, commit de `data/llm` (y los domingos y a mano, de `data/bd` y `web/datos`) y publicación de la web con los datos del día. Entre semana la base de trabajo pasa de un día al siguiente en la caché de Actions; se reconstruye desde `data/bd` cuando este cambia |
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

Un conector sin probar se puede registrar con `activa=False` en su `FUENTE`: la recogida diaria se lo
salta, pero `probar` y `recoger --fuente <código>` lo ejecutan. Las descargas comunes (`ctx.json`, `ctx.fetch`, `ctx.cache`)
hacen GET y POST (`formulario=` o `post_json=`), reintentan, esperan lo que pida un 429 y, con
`http_util.ritmo(host, segundos)`, reparten las peticiones a una API con límite entre todos los hilos.

Un organismo con parlamento propio, como el Parlamento Europeo, necesita un «país» de origen en
`concordia/datos/paises.json` con `"organismo": 1` y sin alias (se añade en `ORGANISMOS` de
`herramientas/generar_paises.py`). Si sus miembros son de varios países, el país va en el id del miembro y la
fuente se añade a `PLURINACIONALES` en `concordia/exportar_web.py`, para que la web sepa quién tiene miembros.

Los siguientes candidatos: Corea del Sur y Australia (API con clave gratuita), Eslovenia y Luxemburgo (descargas abiertas), Italia (dati.camera.it) y Japón
(Cámara de Consejeros). La ayuda de la web tiene la tabla completa por país.

## Limitaciones

- Solo cuenta lo que se vota con votación registrada: lo aprobado por consenso o a mano alzada no aparece.
- La relación «por ley» solo tiene como origen los países con conector (y la Unión Europea); el resto
  aparece como destino y en la ONU.
- En el Parlamento Europeo solo están las votaciones nominales. Lo que votan los eurodiputados de un país no
  es la posición de su Gobierno ni de su parlamento: por eso no genera relaciones con origen en ese país.
- La ONU llega hasta diciembre de 2025, lo que traía el fichero oficial en la última recogida. Descargarlo
  exige pasar un reto anti-robots con un navegador real; si falla, hay que bajarlo a mano (ver arriba).
- La orientación sale del título: la IA puede equivocarse con títulos poco informativos y las reglas solo
  ven lo que el título dice. Cada relación dice quién la decidió y enlaza al texto oficial.
- En EEUU, «aprobado» es aprobado en la votación final de al menos una cámara, no que sea ley.
- En el Reino Unido, un proyecto de ley cuyas votaciones cruzan el cambio de año cuenta como dos asuntos.
- Las reglas deterministas solo leen títulos en inglés y en español. En los demás parlamentos (Alemania,
  Brasil, Chequia, Dinamarca, Estonia, Finlandia, Francia, Israel, Noruega, Países Bajos, Polonia, Suecia,
  Suiza y Ucrania), las relaciones con otros países salen solo de la ficha de la IA, que se hace poco a poco
  (las pendientes se reparten por turnos entre fuentes, con los tratados primero).
- En varios parlamentos lo que se vota es la propuesta de la comisión de rechazar una moción (Suecia,
  Alemania, iniciativas ciudadanas en Finlandia, propuestas de diputados en Noruega): «aprobado» es entonces
  el rechazo. El título o el texto de la votación lo dicen, y la ficha de la IA lo tiene en cuenta.

## Licencia

Código bajo licencia MIT (`LICENSE`). sql.js es MIT; d3-geo, d3-array, topojson-client y world-atlas son
ISC; los datos de Natural Earth son de dominio público. Los datos de votaciones proceden de sus fuentes,
enlazadas desde cada votación: Voeten et al. (CC0), Voteview, UK Parliament (Open Parliament Licence),
Sejm RP y Congreso de los Diputados vía Escrutinio. Los del Parlamento Europeo son de HowTheyVote.eu, bajo
licencia Open Database License (ODbL): quien reutilice la base derivada debe citarlo y compartirla con la
misma licencia.
