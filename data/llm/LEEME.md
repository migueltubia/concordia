# Fichas de la IA

Lo que devuelve la IA se guarda aquí y se versiona: es la fuente de verdad de esa parte, así que
reconstruir la base (`python -m concordia unir`) no vuelve a llamar a la IA.

| Carpeta | Contenido |
| --- | --- |
| `fichas/<fuente>/<AAAA-MM>.jsonl` | Una ficha completa por línea: `id` del asunto, `resumen`, `tema_principal`, `temas_secundarios`, `etiquetas`, `relaciones` y `confianza`, con el modelo que la hizo en `_modelo` |
| `relaciones/<fuente>/<AAAA-MM>.jsonl` | Solo `id` y `relaciones`, para asuntos que ya tienen resumen y tema de otra parte (las fichas de Escrutinio del Congreso de España) o cuyas relaciones se corrigieron aparte; se cargan después de las fichas y mandan sobre ellas |
| `pendientes/` | Lo que deja `fichas-exportar` para procesarlo con otro modelo o por otra vía (no se versiona) |

Cada relación es `{"pais": ISO3, "orientacion": "positiva" | "negativa" | "neutra", "tipo": ..., "motivo": ...}`,
con `tipo` de la lista cerrada de `concordia/catalogos.py` (TIPOS_RELACION). Todo se valida al importar:
temas y tipos de las listas cerradas, códigos ISO del catálogo y nunca el país de la propia cámara.

Si una línea de un asunto se repite, vale la última.

Desde noviembre de 2026 cada línea lleva también `_version` (la versión del prompt, `VERSION_PROMPT` de
`concordia/llm/prompt.py`) y `_creado` (fecha UTC). Las líneas con `_limpieza` son fichas anteriores a las que
`herramientas/limpiar_resumenes.py` quitó frases de relleno, sin IA. Las de `_modelo` `claude:…` las hizo o
revisó Claude a partir de los lotes de `herramientas/exportar_revision.py`.
