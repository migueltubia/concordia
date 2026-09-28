# Votaciones parlamentarias en el mundo: qué datos hay por país

Sep 28, 2026 · @Miguel

## Conclusión

Hay unos 25 parlamentos nacionales donde se puede sacar el voto de cada legislador de forma razonable (API, descarga masiva o un proyecto cívico que ya lo hace). A ellos se suman otros seis que solo registran el voto por grupo y tres organismos supranacionales que, para un análisis geopolítico, valen más que cualquier parlamento suelto.

Lo más valioso para empezar no es un país, sino la **Asamblea General de la ONU**. Es un solo fichero con el voto de cada Estado en cada resolución desde 1946, y responde directamente a «quién se alinea con quién». Después vendrían el **Parlamento Europeo** (HowTheyVote.eu, voto de cada eurodiputado desde 2019) y **EEUU** (Voteview y la API de Congress.gov, con todo el histórico). Con esas tres fuentes ya se cubre buena parte de las decisiones de política exterior que interesan desde España.

Por países, el mapa sale muy desigual:

- **Europa del Norte y Central** es la mejor zona: Polonia, Suecia, Irlanda, Chequia, Francia, Dinamarca, Estonia, Eslovenia, Finlandia, Noruega, Suiza y Reino Unido tienen API o descargas con el voto de cada diputado.
- **América Latina** tiene tres casos muy buenos (Brasil, Chile y la Cámara de Diputados de Argentina) y México aceptable. El resto exige leer PDF.
- **Asia y Oriente Medio**: Corea del Sur e Israel tienen APIs oficiales con voto nominal. Japón y Taiwán son viables con trabajo.
- **África y el sur de Asia** casi no publican votos individuales: se vota a viva voz y solo se registran las divisiones, que son raras.

Hay un segundo grupo de países cuyo parlamento vota casi siempre por grupo: Alemania, Países Bajos, Austria, Portugal, Nueva Zelanda y la Cámara baja de Japón. Sirven igual que los parlamentos autonómicos de Escrutinio que solo dan el voto por grupo.

Y hay un tercer grupo donde los votos no significan nada porque el parlamento no es competitivo: China, Rusia, Bielorrusia, Cuba, Nicaragua, Venezuela y las monarquías del Golfo. Ahí no tiene sentido recoger votos. Lo que sí sirve es el texto de sus leyes para la dimensión exterior: una ley rusa de «agentes extranjeros» o de contramedidas a sanciones importa aunque se apruebe por unanimidad.

El cuello de botella son los votos, no los textos. Casi todos los países publican el texto de sus leyes en algún formato, así que la parte del LLM es viable prácticamente en todo el mundo.

Todo esto sale de una investigación con lectura automática de las webs. Bastantes portales la bloquearon, así que lo marcado como «sin verificar» hay que comprobarlo a mano antes de programar.

## Cómo leer las tablas

Para cada país se ha mirado lo mismo que en Escrutinio: qué detalle de voto se publica, dónde y en qué formato, desde cuándo, y si los textos de las leyes están disponibles. El detalle se resume en cuatro niveles, que son los mismos que ya usa Escrutinio:

- **Nominal**: el voto de cada legislador.
- **Por grupo**: solo qué votó cada partido. Suele pasar donde se vota levantándose o a mano alzada, y solo se registra el nombre en votaciones especiales.
- **Totales**: sí, no y abstenciones, sin reparto.
- **Nada**: solo «aprobado», o ni eso.

La dificultad va de 1 (API o descarga masiva con el voto nominal) a 5 (no hay datos o hay que leer PDF escaneados de una web que bloquea). Cuando el dato oficial es malo pero un proyecto cívico ya ha hecho el trabajo, la dificultad refleja esa vía y se indica.

Se cubre la cámara baja de cada país y la alta cuando tiene poder real sobre las leyes (EEUU, Italia, Brasil, Chile, Argentina, Rumanía, México, Japón). España no aparece porque ya está en Escrutinio.

## Organismos supranacionales

Aquí el que vota no es un diputado sino un Estado, y eso es justo lo que pide un análisis geopolítico.

| Organismo | Qué hay | Formato y licencia | Cobertura | Dificultad |
| --- | --- | --- | --- | --- |
| Asamblea General de la ONU (oficial) | [Voto de cada Estado](https://digitallibrary.un.org/record/4060887) en cada resolución adoptada, unas 916.000 filas | CSV, uso no comercial con atribución, actualización continua | 1946 a septiembre 2025 | 1 |
| Asamblea General de la ONU (UNGA-DM, Ginebra) | [Todas las decisiones](https://unvotes.unige.ch): también resoluciones rechazadas, enmiendas, votos por párrafo y consensos | CSV, SQL y API, CC BY 4.0 | 1946-2023, actualización anual | 2 |
| Consejo de Seguridad de la ONU | [Voto de cada miembro](https://digitallibrary.un.org/record/4055387) en cada resolución adoptada. Los vetos van aparte | CSV, no comercial | 1946 a enero 2026 | 1 |
| Parlamento Europeo | [HowTheyVote.eu](https://howtheyvote.eu/about): voto de cada eurodiputado en las votaciones nominales, unas 25.000 | CSV semanal en [GitHub](https://github.com/HowTheyVote/data), JSON por votación, ODbL | Desde 2019 | 1 |
| Consejo de la UE | [Voto de cada Estado](https://www.consilium.europa.eu/en/general-secretariat/corporate-policies/transparency/voting-results/) en actos legislativos. Hay una versión limpia en el [dataset SWP](https://www.swp-berlin.org/publikation/public-voting-data-of-the-council-of-the-eu) | Buscador sin API; el dataset SWP es CC BY 4.0 y estático | 2009 en adelante (SWP: 2010-2023) | 2-4 |
| Asamblea del Consejo de Europa (PACE) | Páginas de votación por sesión; el voto nominal está sin verificar | Scraping | Sin verificar | 4 |

La Asamblea General es la pieza central. Con ella se calcula para cada país con quién vota y cómo cambia eso con los años, sobre todo en los temas que dividen: Oriente Medio, Ucrania, desarme o derechos humanos. El dataset de Ginebra añade lo que no sale adelante, que muchas veces es lo más revelador (una enmienda hostil que un bloque intenta colar). Además, las resoluciones son textos cortos y el LLM las clasifica igual que una PNL.

El Consejo de la UE tiene una limitación importante: solo publica votos de actos legislativos. La política exterior común y las sanciones se deciden por unanimidad y no aparecen como votos.

El resto de asambleas regionales (Parlasur, Parlamento Panafricano, OEA) no publica votos nominales, o no se ha podido encontrar. La OEA adopta casi todo por consenso, con reservas en notas al pie.

## Unión Europea: parlamentos nacionales

Es la zona con mejores datos del mundo, aunque con una trampa: en Alemania, Países Bajos, Austria y Portugal casi todo se vota por grupo, y el voto individual solo existe en votaciones especiales. Ordenados de más fácil a más difícil:

| País | Voto | Fuente y formato | Desde | Dificultad |
| --- | --- | --- | --- | --- |
| Polonia | Nominal y club | [API del Sejm](https://api.sejm.gov.pl/), JSON, con impresos y adjuntos PDF | Legislaturas anteriores sin verificar | 1 |
| Suecia | Nominal (solo votaciones con recuento) | [data.riksdagen.se](https://data.riksdagen.se/voteringlista/), XML/JSON/CSV. Se vota por punto de informe de comisión, hay que enlazarlo con la ley | 1993 | 1 |
| Irlanda | Nominal, Dáil y Seanad | [API del Oireachtas](https://api.oireachtas.ie/), JSON, con proyectos y PDF | Hacia 2002, sin verificar | 1 |
| Francia | Nominal en scrutins publics; nada en mano alzada | [Datos abiertos de la Asamblea](https://data.assemblee-nationale.fr/travaux-parlementaires/votes), JSON/XML diario. Senado sin verificar | Legislatura XIV | 1-2 |
| Países Bajos | Por grupo, a veces nominal | [OData de la Tweede Kamer](https://opendata.tweedekamer.nl/documentatie/stemming) | 2008 | 1 (por grupo) |
| Chequia | Nominal | [ZIP diarios](https://www.psp.cz/sqw/hp.sqw?k=1300) en formato UNL, Windows-1250, con proyectos | 1993 | 2 |
| Dinamarca | Nominal | API OData [oda.ft.dk](https://oda.ft.dk/) con votos, asuntos y documentos | Hacia 2004, sin verificar | 2 |
| Estonia | Nominal | [API del Riigikogu](https://api.riigikogu.ee/), JSON | 2012 | 2 |
| Eslovenia | Nominal | [Dataset de votaciones](https://podatki.gov.si/dataset/dzglasovanja-dz), XML, CC BY | 2000 | 2 |
| Finlandia | Nominal | [API del Eduskunta](https://avoindata.eduskunta.fi/), JSON, con documentos en XML | Años 90, sin verificar | 2 |
| Luxemburgo | Nominal | [data.public.lu](https://data.public.lu/fr/datasets/la-liste-des-votes/), CSV/XML | Hacia 2018 | 2 |
| Italia | Nominal, Cámara y Senado | dati.camera.it y dati.senato.it, SPARQL y descargas. Bloquearon con CAPTCHA y 403 | Legislatura XIII, sin verificar | 2 |
| Alemania | Por grupo; nominal solo en votaciones nominales | [Listas de votaciones nominales](https://www.bundestag.de/parlament/plenum/abstimmung/liste) en XLSX, API DIP para proyectos. Proyecto cívico: abgeordnetenwatch, con API | 1949 (actas) | 2 por grupo, 3 nominal |
| Portugal | Por grupo | [Datos abiertos](https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx) JSON/XML con iniciativas y votaciones | Desde la Constituyente | 2 (por grupo) |
| Austria | Por grupo; nominal muy rara | [API de datos abiertos](https://www.parlament.gv.at/recherchieren/open-data), CC BY; las votaciones van en el acta | Legislatura XXII | 3 por grupo |
| Hungría | Nominal | parlament.hu con API oficial limitada; el proyecto cívico Parlamonitor hace scraping | Sin verificar | 3 |
| Rumanía | Nominal, Cámara y Senado | Páginas HTML por votación ([Senado](https://www.senat.ro/VoturiPlenDetaliu.aspx)), sin API | Sin verificar | 3 |
| Eslovaquia | Nominal | HTML en nrsr.sk y una API desde 2023, sin verificar | Sin verificar | 3 |
| Lituania | Nominal | Servicio XML en lrs.lt, bloqueado para la lectura automática | Sin verificar | 3 |
| Letonia | Nominal | titania.saeima.lv (bloqueada) y un dataset XML solo de 2016-2019 | 2016-2019 | 3-4 |
| Bélgica | Nominal | Anexo de votos nominales del acta, HTML/PDF. El portal de datos es una beta sin votos | Sin verificar | 4 |
| Bulgaria | Nominal y por grupo | Junto a las actas en parliament.bg, formato sin verificar | Sin verificar | 4 |
| Grecia | Por declaración de grupo; nominal rara | Actas PDF/DOC | — | 4-5 |
| Malta | Viva voz; divisiones raras | Actas, sin datos abiertos | — | 4-5 |
| Croacia | Totales | Actas del Sabor; el portal de datos no tiene votaciones | — | 5 |
| Chipre | Mano alzada | Sin datos | — | 5 |

En la mayoría hay proyectos cívicos que ya agregan estos datos y sirven para contrastar: Hlídač státu en Chequia, Openpolis en Italia, NosDéputés en Francia, Parlameter en Eslovenia u openAR en Portugal.

## Resto de Europa, Norteamérica y Oceanía

EEUU es el caso más completo del mundo: voto de cada congresista desde 1789 en ambas cámaras. Detrás, el mundo anglosajón, Suiza, Noruega y Ucrania. Los Balcanes, Turquía y el Cáucaso casi no publican.

| País | Voto | Fuente y formato | Desde | Dificultad |
| --- | --- | --- | --- | --- |
| EEUU | Nominal, Cámara y Senado | [Voteview](https://voteview.com/data), CSV/JSON (todo el histórico). [API de Congress.gov](https://blogs.loc.gov/law/2025/05/introducing-house-roll-call-votes-in-the-congress-gov-api/) con votaciones de la Cámara desde 2023, proyectos y textos. Senado en [XML](https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_1.xml). La API de ProPublica está cerrada | 1789 | 1 |
| Reino Unido | Nominal, Comunes y Lores | [Commons Votes API](https://commonsvotes-api.parliament.uk/swagger/docs/v1) y Lords Votes API, JSON/XML. Bills API con textos en PDF. [TheyWorkForYou Votes](https://votes.theyworkforyou.com/) como alternativa | Hacia 2016 oficial; 1997 en TheyWorkForYou | 1-2 |
| Suiza | Nominal | [OData del Parlamento](https://ws.parlament.ch/odata.svc/) con votos, asuntos y textos. Mensajes del Gobierno en Fedlex (SPARQL) | 2007 | 2 |
| Noruega | Nominal | [data.stortinget.no](https://data.stortinget.no/dokumentasjon-og-hjelp/voteringsresultat/), XML | 2011 | 2 |
| Canadá | Nominal | [ourcommons.ca](https://www.ourcommons.ca/members/en/votes/45/1/1) en XML/CSV, LEGISinfo en JSON/XML. Alternativa: [openparliament.ca](https://openparliament.ca/api/) con API y volcado | 2004 | 2 |
| Ucrania | Nominal | [Dataset de votaciones nominales](https://data.rada.gov.ua/open/data/plenary_vote_results-skl9) de la Rada (formato sin verificar, bloqueado). Alternativa: rada4you con API | 2001 | 2-3 |
| Islandia | Nominal | XML abierto del Althingi, bloqueado para la lectura automática | Sin verificar | 2-3 |
| Australia | Nominal (divisiones) | Sin API oficial. [TheyVoteForYou](https://theyvoteforyou.org.au/help/data), API JSON con clave | Hacia 2006 | 3 |
| Nueva Zelanda | Por partido; nominal solo en votos de conciencia | Sin API de votos; hay que leer el Hansard. La [API de legislación](https://api.legislation.govt.nz/docs/) sí es buena para textos | — | 4 |
| Serbia | Nominal en proyecto cívico | [Otvoreni Parlament](https://otvoreniparlament.rs/), sin API | Sin verificar | 4 |
| Georgia | Probablemente nominal | [Resultados por sesión](https://www.parliament.ge/en/legislation/voting-results/sessions/27608), cargados con JavaScript | Sin verificar | 4 |
| Turquía | Mano alzada; nominal solo en algunas votaciones | Actas (Tutanaklar), sin datos abiertos | — | 5 |
| Moldavia, Albania, Macedonia del Norte, Bosnia, Montenegro | Sin verificar | Sin datos abiertos de votaciones | — | 4-5 |
| Rusia | Nominal (técnicamente) | [API de la Duma](http://api.duma.gov.ru/pages/dokumentatsiya/svedeniya-o-golosovanii), inaccesible desde fuera. Parlamento no competitivo: solo interesan los textos | 2021 | 2-3, relevancia baja |
| Bielorrusia | Nada | — | — | Excluir |

Para los estados de EEUU hay dos fuentes que reúnen los 50 parlamentos: [LegiScan](https://www.legiscan.com/legiscan) (API gratuita hasta 30.000 consultas al mes, CC BY 4.0) y [OpenStates](https://open.pluralpolicy.com/data/) (dominio público). Legislan poco en política exterior, salvo leyes de desinversión o boicot, que sí tienen interés geopolítico.

## América Latina

Brasil y Chile tienen datos oficiales con el voto de cada legislador en las dos cámaras, al nivel de los mejores europeos. Argentina los tiene en Diputados. En el resto, el voto nominal existe con frecuencia, pero en PDF o en webs que bloquean, y a menudo es un medio o una ONG quien lo ha convertido en datos.

| País | Voto | Fuente y formato | Desde | Dificultad |
| --- | --- | --- | --- | --- |
| Brasil | Nominal y orientación de bancada, Cámara y Senado | [API de la Câmara](https://dadosabertos.camara.leg.br/swagger/api.html) con ficheros anuales CSV/JSON/XML; [servicios del Senado](https://www12.senado.leg.br/dados-abertos/legislativo/plenario/votacoes-nominais) en XML | Senado 2003; Cámara sin verificar | 1 |
| Chile | Nominal, Cámara y Senado | [Servicios SOAP/XML](https://opendata.congreso.cl/pages/votacion_detalle.aspx) de la Cámara y [del Senado](https://tramitacion.senado.cl/wspublico/invoca_votacion.html), unidos por número de boletín. Alternativa: [libre-camara](https://github.com/m73lab/libre-camara) en JSON | Sin verificar | 2 |
| Argentina | Nominal | Diputados: [dataset de votaciones nominales](https://datos.hcdn.gob.ar/dataset/votaciones_nominales) y [votaciones.hcdn.gob.ar](https://votaciones.hcdn.gob.ar/). Senado: [actas PDF](https://www.senado.gob.ar/votaciones/actas) por senador. Histórico en [votaciones-ar-datasets](https://github.com/nahuelhds/votaciones-ar-datasets) | 1983 (Senado), 1993 (Diputados) | 2 Diputados, 3 Senado |
| México | Nominal en Diputados; Senado sin verificar | [SITL](https://sitl.diputados.gob.mx/LXVI_leg/listados_votacionesnplxvi.php?partidot=1&votaciont=148) en HTML por legislatura, sin API | Legislatura LXIV, sin verificar | 3 |
| Costa Rica | Nominal (vía medio) | [Delfino.cr](https://delfino.cr/asamblea/votaciones) recoge el voto de cada diputado; la fuente oficial estaba bloqueada | 2018 | 3 |
| Guatemala | Probablemente nominal | [Páginas por votación](https://www.congreso.gob.gt/seccion_informacion_legislativa/votaciones_pleno), bloqueadas para la lectura | Sin verificar | 3 |
| Ecuador | Sin verificar | [Portal de votaciones](https://datos.asambleanacional.gob.ec/votaciones) dinámico, no se pudo leer | Sin verificar | 3 |
| Paraguay | Sin verificar | [API de SILpy](https://datos.congreso.gov.py/opendata/api); en 2016 no traía votaciones | Sin verificar | 3-4 |
| Colombia | Nominal por ley (Ley 1431 de 2011) | Cámara por sesión, formato sin verificar; Senado en actas PDF. [Congreso Visible](https://congresovisible.uniandes.edu.co/votaciones/) da totales | Sin verificar | 4 |
| Perú | Nominal y grupo | PDF escaneados del pleno. Bicameral desde 2026, Senado sin verificar | Sin verificar | 4 |
| Uruguay | Nominal en diarios de sesiones, sin verificar | Datos abiertos del Parlamento sin votaciones | — | 4 |
| Panamá, El Salvador, República Dominicana | Sin verificar | Datos abiertos sin votaciones; actas y decretos en PDF | — | 4 |
| Bolivia | Nada encontrado | Proyectos en PDF | — | 5 |
| Honduras | Mano alzada | Sistema electrónico prometido para 2026, todavía sin funcionar | — | 5 |
| Venezuela, Nicaragua, Cuba | Nada o unanimidad | Parlamentos no competitivos: solo interesan los textos | — | Excluir votos |

El patrón es parecido al de los parlamentos autonómicos de Escrutinio: donde no hay datos estructurados, el voto nominal suele estar en un PDF o en el diario de sesiones. Eso encaja con los conectores de tipo PDF con reglas o PDF con LLM que ya tienes.

## Asia, Oriente Medio y África

Corea del Sur e Israel tienen APIs oficiales con el voto de cada diputado. Fuera de esos dos, la norma en los parlamentos de tradición británica (India, Pakistán, Malasia, Kenia, Ghana, Nigeria) es votar a viva voz. Solo queda registro nominal cuando se pide una división, que es poco frecuente.

| País | Voto | Fuente y formato | Desde | Dificultad |
| --- | --- | --- | --- | --- |
| Corea del Sur | Nominal | [API de la Asamblea Nacional](https://open.assembly.go.kr/portal/data/service/selectServicePage.do/OPR1MQ000998LC12535), JSON/XML con clave gratuita. Textos en coreano | Sin verificar | 1-2 |
| Israel | Nominal | API OData V4 de la Knesset (tablas de votos del pleno). El identificador del voto no coincide con el de la persona y hay que cruzar por nombre. Textos en hebreo | Knesset actual; el servicio antiguo se paró en 2021 | 2 |
| Taiwán | Nominal en votaciones registradas | Gaceta del Yuan Legislativo y la API comunitaria [ly.govapi.tw](https://ly.govapi.tw/v2/) (g0v); votos estructurados sin verificar. Textos en chino | Sin verificar | 2-3 |
| Japón | Nominal en la Cámara de Consejeros; por partido en la de Representantes | [Resultados del Senado](https://www.sangiin.go.jp/japanese/touhyoulist/touhyoulist.html) en HTML; posición de partido de SmartNews en CSV/JSON (MIT). Actas por la [API kokkai](https://kokkai.ndl.go.jp/api.html) | 1998 | 3 |
| Tailandia | Nominal | PDF oficiales pasados a datos por [WeVis Parliament Watch](https://parliament-watch.pages.dev/about) (CC BY-NC, cobertura incompleta) | Sin verificar | 3 |
| Sudáfrica | Por partido; nominal en divisiones | Actas del Parlamento (web con certificado roto) y seguimiento de proyectos en PMG | Sin verificar | 3 |
| Filipinas | Nominal en tercera lectura (obligatorio por la Constitución) | Journals de las cámaras en PDF/HTML | Sin verificar | 3-4 |
| Kenia | Nominal en divisiones | Hansard en PDF; [Mzalendo](https://mzalendo.com/research-and-knowledge/voting-patterns/division/1082/) las extrae, a veces incompletas | Sin verificar | 3-4 |
| Túnez | Nominal en 2014-2021 | [Marsad Majles](https://www.data4tunisia.org/en/reuses/marsad-majles/) de Al Bawsala; después de 2023, menos transparencia | 2014-2021 | 3 (histórico) |
| Malasia | Viva voz; nominal en divisiones | Hansard en PDF | — | 4 |
| Marruecos | Totales y a veces por grupo | Web de la Cámara, árabe y francés | — | 4 |
| Indonesia | Consenso; posición de cada facción | Proyectos en PDF en indonesio | — | 4-5 |
| India | Viva voz; menos de 50 divisiones por legislatura | Sin datos de votos. Los textos, en inglés y bien seguidos por [PRS](https://prsindia.org/articles-by-prs-team/parliament-voting-ayes-vs-noes-and-road-from-manual-to-electronic-recording) | — | 5 votos, 1 textos |
| Pakistán, Bangladesh, Nigeria, Ghana, Egipto | Viva voz, totales o nada | Actas en PDF. En Bangladesh la Constitución prohíbe votar contra el partido | — | 5 |
| China, Irán, Arabia Saudí y el Golfo, Etiopía | Totales o nada | No competitivos o consultivos. En China, [NPC Observer](https://newsletter.npcobserver.com/p/npc-2026-collecting-documents-votes) recoge los totales; los textos sí son útiles | — | Excluir votos |

En el resto de África y Asia la situación es parecida. Los parlamentos de tradición británica (Uganda, Tanzania, Zambia, Sri Lanka, Nepal) votan a viva voz con divisiones raras. Los francófonos (Senegal, Costa de Marfil) publican totales o «adoptado». En Asia Central y en los regímenes de partido único no hay nada útil. Donde existen datos, la mejor fuente suele ser una organización cívica (Mzalendo, PMG, WeVis) y no la oficial.

Para todos estos países, la Asamblea General de la ONU es la forma práctica de incluirlos en el análisis: ahí sí hay un voto por país en cada resolución.

## Fuentes

Los enlaces de cada país están en su fila. Estas son las fuentes generales y los agregadores revisados:

- ONU: [votaciones de la Asamblea General](https://digitallibrary.un.org/record/4060887) · [guía de la biblioteca](https://research.un.org/en/docs/unvoting/undl) · [UNGA-DM](https://unvotes.unige.ch) y [su artículo](https://link.springer.com/article/10.1007/s11558-024-09580-1) · [Consejo de Seguridad](https://digitallibrary.un.org/record/4055387) · [datos de Voeten](https://erikvoeten.georgetown.domains/data/)
- UE: [HowTheyVote.eu](https://howtheyvote.eu/developers) · [notas del portal de datos del Parlamento Europeo](https://data.europarl.europa.eu/release-notes) · [votaciones del Consejo](https://www.consilium.europa.eu/en/general-secretariat/corporate-policies/transparency/voting-results/) · [dataset SWP](https://www.swp-berlin.org/publikation/public-voting-data-of-the-council-of-the-eu)
- Agregadores sin votos, útiles como apoyo: [ParlGov](https://www.parlgov.org/) (partidos y gobiernos de 37 países, sirve para clasificar partidos entre países) · [ParlaMint](https://www.clarin.si/repository/xmlui/handle/11356/2004) (discursos de unos 29 parlamentos) · [IPU Parline](https://data.ipu.org/) (estructura de parlamentos) · [Comparative Legislators Database](https://complegdatabase.com/about/) · [EveryPolitician](https://everypolitician.org/)
- EEUU: [Voteview](https://voteview.com/data) · [API de Congress.gov](https://api.congress.gov/) · [cierre de la API de ProPublica](https://projects.propublica.org/api-docs/congress-api/) · [LegiScan](https://www.legiscan.com/legiscan) · [OpenStates](https://open.pluralpolicy.com/data/)
