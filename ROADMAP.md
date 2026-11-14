# Roadmap — de pieza de portfolio a herramienta para comprar casa

Auditoría del 2026-11-13. Todo lo de "Estado" se comprobó ejecutando (warehouse,
Actions, app local), no leyendo código.

## Estado

| Qué | Cómo está |
|---|---|
| Pipeline semanal (Prefect + Actions) | Corre cada lunes desde el 22-sep, 0 fallos en ~600 ejecuciones horarias |
| Tests | 132 pytest en verde, 162/162 dbt |
| App en vivo | Responde; `docs/status.json` al día (9-nov, 1.233 listings) |
| Scrapfly | 1.000 créditos/mes, ~800 gastados por 4 lunes × 200 |
| Volumen | 537 pisos en venta + 694 en alquiler puntuados, solo València ciudad |

## Problemas encontrados

1. **El "chollo" es solo €/m² contra la mediana del barrio.** Un bajo interior sin
   ascensor a reformar sale como "Great deal". Los 4 mejores de la portada están
   al -35/-56% de su barrio: casi seguro son pisos distintos, no baratos.
2. **Las tarjetas de Idealista ya traen planta, exterior/interior, ascensor, garaje
   y la marca de precio rebajado, y no se guardan.** Coste en créditos: cero.
3. **Semanas parciales que cuentan como éxito.** 28-sep sin venta, 5-oct sin
   alquiler, 12-oct 30 de venta, 19-oct sin venta, 9-nov 90 de alquiler. El
   bloqueo anti-bot entre operaciones deja el run en verde con la mitad de datos.
4. **Señales de vendedor casi vacías.** El 95% de los anuncios se ha visto una
   sola vez (efecto de ordenar por más recientes, ADR-0010): 31 bajadas de precio
   detectadas en 537 pisos.
5. **Ciudad fantasma "Piso En"** en la app en vivo: 2 filas con título truncado
   llegan hasta gold; la portada dice "cities 2" y las menciona en el pie.
6. **La tira de frescura dice "neighbourhood 36.4%" en aviso** y Deals dice 84%.
   El 36% mezcla alquiler, que por diseño nunca puntúa a nivel barrio.
7. **Sin baños ni coordenadas** (0 de 2.507 filas): columnas siempre nulas.
8. **Solo València ciudad.** Nada de l'Horta Nord ni del resto del área
   metropolitana.

## Fase 0 — Arreglos (sin decisiones pendientes)

| # | Tarea | Modelo | Estado |
|---|---|---|---|
| 0.1 | Rechazar títulos truncados; quitar "Piso En" de gold y de la portada; tira de frescura con el % de barrio solo de venta | Sonnet | hecha (#51, prod reconstruido 13-nov) |
| 0.2 | Capturar de la tarjeta: planta, exterior, ascensor, garaje, rebaja, descripción → raw → bronze → gold | Opus | hecha (#52); revisar `raw_floor_text` tras el scrape del 16-nov |
| 0.3 | Scrape parcial = aviso visible: páginas pedidas vs obtenidas por operación en `status.json`; alternar qué operación va primero cada semana | Sonnet | hecha (#53); mirar `scrape_coverage` el 16-nov |
| 0.4 | `_extract_size` lee "1.674 m²" como 1,674 m² (el punto es separador de miles): toda vivienda de más de 999 m² se rechaza | Sonnet | hecha (#53) |
| 0.5 | "Keep app awake" no despierta nada: recibe un 303 y lo da por bueno. El 13-nov la app estaba dormida; hay que pulsar el botón de despertar (Playwright) o al menos comprobar `api/v2/app/status` | Sonnet | pendiente |

## Fase 1 — Que el score sirva para comprar

| # | Tarea | Modelo | Depende de |
|---|---|---|---|
| 1.1 | Comparables de verdad: benchmark ajustado por planta/ascensor/exterior/tamaño (regresión hedónica por barrio, en dbt o Python) y ADR | Opus | 0.2 + 3-4 semanas de datos |
| 1.2 | Ficha del piso: mostrar atributos y por qué puntúa lo que puntúa ("barato, pero bajo sin ascensor") | Sonnet | 0.2 |
| 1.3 | Filtros de comprador en Deals: habitaciones, m², ascensor, planta, barrios | Sonnet | 0.2 |
| 1.4 | Recuperar días en mercado y bajadas: 1 de las 4 páginas semanales en orden de relevancia, o re-visita de los favoritos | Opus | decisión de créditos |

## Fase 2 — Uso personal

| # | Tarea | Modelo | Depende de |
|---|---|---|---|
| 2.1 | Zona objetivo real (municipios de l'Horta, no solo València): URLs, seed de barrios/municipios, reparto de créditos | Opus | dónde quieres comprar |
| 2.2 | Lista de seguimiento: marcar pisos, notas, estado (visto/visitado/descartado), historial de precio | Sonnet | — |
| 2.3 | Alerta semanal (email o Telegram) con los pisos nuevos que cumplen tu perfil | Sonnet | 1.3, perfil |
| 2.4 | Budget con tu caso guardado y enlazado desde cada piso ("este piso: entrada X, cuota Y") | Sonnet | — |
| 2.5 | Precios de cierre reales: valor tasado del MITMA / notarios por municipio, para estimar el descuento de negociación sobre el precio de oferta | Opus | — |

## Fase 3 — Portfolio

| # | Tarea | Modelo |
|---|---|---|
| 3.1 | README, capturas y caso de estudio del portfolio al día con las fases 0-1 | Sonnet |
| 3.2 | Página de salud del pipeline: cobertura por semana, páginas bloqueadas, créditos | Sonnet |
| 3.3 | Fotocasa como segunda fuente (único punto abierto del roadmap del README) | Opus |

## Decisiones tuyas

- **Dónde y qué**: València ciudad o también l'Horta Nord; piso o casa; presupuesto.
  Con 40 páginas al mes, cada municipio que se añade resta profundidad al resto.
- **Créditos**: seguir en el plan gratuito (1.000/mes) o pagar durante los meses
  de búsqueda activa.
- **Perfil privado**: la lista de seguimiento y las alertas son personales; la app
  es pública. Hace falta decidir si viven en una página protegida o en local.
