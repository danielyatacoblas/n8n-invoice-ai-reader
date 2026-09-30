# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y versionado [SemVer](https://semver.org/lang/es/).

## [1.1.1]

### Añadido
- Diagrama gitGraph del historial en el README, generado por `scripts/diagrama_git.py` a partir de las ramas y tags reales.

## [1.1.0]

### Añadido
- Imagen de arquitectura en el README: problema, entradas, pasos dentro de n8n y salidas.
- Imagen de pruebas en el README: tests por archivo y verificaciones hechas en n8n real.

## [1.0.0]

### Añadido
- Lectura de facturas electrónicas peruanas desde el texto del PDF, con etiquetas de distintos sistemas de facturación.
- Validación: dígito verificador del RUC, RUC del cliente, fecha, IGV al 18 % y total.
- Detección de duplicados por RUC + serie + número.
- Lectura con IA solo cuando al PDF le falta un dato, validada con las mismas reglas.
- Workflow demo sin credenciales y workflow de producción con Gmail, IA y Google Sheets.
- Generador de 32 facturas PDF ficticias con casos de error y evaluación contra lo esperado.
- Test de paridad entre los nodos JavaScript y la lógica Python.
