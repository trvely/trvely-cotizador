# Cotizador Trvely — tablero interno del asesor

Herramienta interna para cotizar rápido: buscar plan, ver el precio real por cada fecha
de salida y copiar la cotización lista para pegar en WhatsApp del cliente.

- **Uso:** interno (asesores). `noindex`. Precios de venta por persona en doble.
- **Datos:** `snapshot` generado desde el motor de costeo (fn_costeo, PROD) — precio por fecha
  + inclusiones reales por plan. Debe regenerarse a diario (los precios caducan a 24h).
- Publica en `cotizador.trvely.com.co` (GitHub Pages).
