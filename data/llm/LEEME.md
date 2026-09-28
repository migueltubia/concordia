# Fichas de la IA

Lo que devuelve la IA se guarda aquí y se versiona: es la fuente de verdad de esa parte, así que
reconstruir la base (`python -m concordia unir`) no vuelve a llamar a la IA.

| Carpeta | Contenido |
| --- | --- |
| `fichas/<fuente>/<AAAA-MM>.jsonl` | Una ficha completa por línea: `id` del asunto, `resumen`, `tema_principal`, `temas_secundarios`, `etiquetas`, `relaciones` y `confianza`, con el modelo que la hizo en `_modelo` |
| `relaciones/<fuente>/<AAAA-MM>.jsonl` | Solo `id` y `relaciones`, para asuntos que ya tienen resumen y tema de otra parte (las fichas de Escrutinio del Congreso de España) |
| `pendientes/` | Lo que deja `fichas-exportar` para procesarlo con otro modelo o por otra vía (no se versiona) |

Cada relación es `{"pais": ISO3, "orientacion": "positiva" | "negativa" | "neutra", "tipo": ..., "motivo": ...}`,
con `tipo` de la lista cerrada de `concordia/catalogos.py` (TIPOS_RELACION). Todo se valida al importar:
temas y tipos de las listas cerradas, códigos ISO del catálogo y nunca el país de la propia cámara.

Si una línea de un asunto se repite, vale la última.
