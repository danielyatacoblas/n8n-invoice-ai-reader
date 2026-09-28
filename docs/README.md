# docs

Material de apoyo del repositorio.

- `demo_facturas.png`: dos facturas procesadas por el workflow de n8n desde la página de demo.

## Grabar el video de la demo

1. `docker compose up -d` e importa y activa `workflows/facturas_demo.json` (ver README).
2. Abre `demo/index.html` y, a un lado, n8n en la pestaña *Executions*.
3. Arrastra en este orden y comenta cada resultado:
   - `factura_01.pdf` → registrada.
   - `factura_23.pdf` → revisión por RUC inválido.
   - `factura_25.pdf` → revisión porque el total no cuadra.
   - `factura_01.pdf` otra vez → duplicada.
   - `factura_29.pdf` → le falta una etiqueta; en producción la lee la IA.
4. Guarda el archivo como `docs/video.mp4`. Luego, al editar el README en
   GitHub, arrastra el video donde dice `VIDEO` para que se reproduzca en la página.
