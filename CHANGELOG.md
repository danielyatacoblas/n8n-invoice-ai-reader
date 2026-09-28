# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y versionado [SemVer](https://semver.org/lang/es/).

## [1.0.0]

### Añadido
- Lectura de facturas electrónicas peruanas desde el texto del PDF, con etiquetas de distintos sistemas de facturación.
- Validación: dígito verificador del RUC, RUC del cliente, fecha, IGV al 18 % y total.
- Detección de duplicados por RUC + serie + número.
- Lectura con IA solo cuando al PDF le falta un dato, validada con las mismas reglas.
- Workflow demo sin credenciales y workflow de producción con Gmail, IA y Google Sheets.
- Generador de 32 facturas PDF ficticias con casos de error y evaluación contra lo esperado.
- Test de paridad entre los nodos JavaScript y la lógica Python.
