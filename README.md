<h1 align="center">Lectura automática de facturas con n8n</h1>

<p align="center"><i>La factura llega por correo y termina registrada y validada, sin que nadie la digite</i></p>

<p align="center">
  <img alt="tests" src="https://img.shields.io/badge/tests-64%20passed-brightgreen">
  <img alt="lectura" src="https://img.shields.io/badge/lectura-256%2F256%20campos-brightgreen">
  <img alt="n8n" src="https://img.shields.io/badge/n8n-self--hosted-EA4B71">
  <img alt="python" src="https://img.shields.io/badge/python-3.12-3776AB">
  <img alt="licencia" src="https://img.shields.io/badge/licencia-MIT-blue">
</p>

---

## Para qué existe este repositorio

Los proveedores mandan sus facturas en PDF a un correo. Alguien de contabilidad abre cada una, copia RUC, serie, fecha y montos a una hoja, y revisa a ojo si el IGV está bien calculado. Es lento, se cuelan errores de tipeo y una factura reenviada se puede registrar dos veces.

**Este flujo lee cada PDF que llega al correo, extrae los datos, los valida con las reglas de SUNAT y los registra en Google Sheets. Solo le llegan a una persona las facturas que tienen un problema, con el motivo escrito.**

```mermaid
flowchart TD
    G["Correo con<br/>factura PDF"] --> X
    subgraph N ["n8n"]
        X["Extraer texto<br/>del PDF"] --> L["Leer campos<br/>RUC, serie, fecha, montos"]
        L --> V{"Validar"}
        L -->|"falta un dato"| IA["IA lee la factura"]
        IA -->|"se valida igual"| V
    end
    V -->|"todo cuadra"| R["Registrada<br/>en Google Sheets"]
    V -->|"hay un problema"| RV["Pestaña Revisión<br/>+ correo a contabilidad"]
    V -->|"ya estaba"| D["Duplicada<br/>se ignora"]
```

---

## Arquitectura

<p align="center"><img src="docs/arquitectura.png" alt="Arquitectura: entradas, pasos dentro de n8n y salidas" width="900"></p>

---

## El workflow en n8n

<p align="center"><img src="docs/workflow_n8n.png" alt="Workflow de producción abierto en el editor de n8n" width="900"></p>

<p align="center"><i>Captura del editor de n8n 2.40 con <code>workflows/facturas_produccion.json</code> importado.
Los triángulos rojos solo indican credenciales por conectar (Google, Telegram, IA).</i></p>

### Paso a paso: una factura con una etiqueta faltante: el texto no alcanza y entra la IA

```mermaid
sequenceDiagram
    autonumber
    participant G as Gmail Trigger
    participant X as Extract from File
    participant H as Sheets · Leer facturas
    participant L as Code · Leer y validar
    participant IA as Information Extractor
    participant V as Code · Validar lectura de la IA
    participant R as Sheets / Gmail
    G->>X: correo con factura.pdf
    X->>H: texto del PDF
    H->>L: facturas ya registradas (Execute Once)
    L->>L: RUC, serie, fecha, montos por etiquetas
    L-->>IA: falta el IGV → estado faltan_datos
    IA->>V: campos leídos por el modelo (sin calcular nada)
    V->>V: dígito del RUC, IGV = 18 %, total = base + IGV, ¿duplicada?
    alt todo cuadra
        V->>R: pestaña Facturas
    else algo no cuadra o la IA falló
        V->>R: pestaña Revisión + correo a contabilidad con el motivo
    end
```

### Técnicas de n8n que usa

**Lectura de facturas · producción** · 14 nodos

| Técnica de n8n | Para qué se usa aquí |
| --- | --- |
| Disparo por eventos (webhook o trigger de la app) | reacciona al instante, sin revisar cada tanto |
| Extract from File | lee PDFs o archivos de texto dentro del flujo |
| Execute Once | lee una hoja completa una sola vez aunque lleguen varios items |
| Always Output Data | una hoja vacía no corta el flujo |
| Lectura de otros nodos por nombre ($('Nodo')) | usa datos de pasos anteriores aunque $input traiga otra cosa |
| Switch con salidas con nombre | cada decisión tiene su rama legible en el canvas |
| Salida de error del nodo (On Error → error output) | si un servicio falla, el flujo sigue por otra rama |
| Nodos de IA de n8n (LangChain) | la IA es un paso del flujo, con su modelo conectado aparte |
| Modelo de IA como sub-nodo intercambiable | se cambia de proveedor sin tocar el resto del flujo |

<details><summary>Nodo por nodo</summary>

| Nodo | Tipo | Configuración |
| --- | --- | --- |
| Gmail · Factura recibida | Gmail Trigger | Conviene usar una casilla o etiqueta solo para facturas (por ejemplo facturas@empresa.pe). |
| Extraer texto del PDF | Extract from File | operación `pdf` |
| Sheets · Leer facturas | Google Sheets | pestaña `Facturas`, Execute Once, Always Output Data. Solo para saber qué facturas ya están registradas. |
| Leer y validar factura | Code (JavaScript) | 226 líneas generadas desde `workflows/src/` |
| ¿Resultado? | Switch | — |
| Fila · registrada | Edit Fields (Set) | — |
| Sheets · Registrar factura | Google Sheets | operación `append`, pestaña `Facturas` |
| Fila · revisión | Edit Fields (Set) | — |
| Sheets · Anotar para revisión | Google Sheets | operación `append`, pestaña `Revision` |
| Gmail · Avisar a contabilidad | Gmail | — |
| Ya registrada · ignorar | No Operation | — |
| IA · Leer factura | Information Extractor | salida de error. Solo se usa cuando el PDF no trae alguna etiqueta. Si la IA falla, la factura va a revisión manual. Lo que lee se vuelve a validar con las mismas reglas. |
| Modelo de IA | OpenAI Chat Model | — |
| Validar lectura de la IA | Code (JavaScript) | 226 líneas generadas desde `workflows/src/` |

</details>

<sub>Tablas generadas del JSON del workflow con <code>python scripts/documentar_workflow.py workflows/facturas_produccion.json</code>.</sub>

---

## Demo

<!-- VIDEO: arrastra aquí el .mp4 al editar el README en GitHub y deja solo la URL que genera. -->

<p align="center"><img src="docs/demo_facturas.png" alt="Demo: dos facturas procesadas por n8n" width="700"></p>

<p align="center"><i>Dos PDFs enviados al workflow de n8n: uno se registra y el otro va a
revisión porque el total no es la base más el IGV.</i></p>

---

## Qué valida

Términos que conviene conocer:

- **RUC:** número de 11 dígitos que identifica a cada contribuyente en el Perú. El último es un **dígito verificador** calculado con el algoritmo módulo 11 de SUNAT, así que un RUC mal tipeado o inventado se detecta sin consultar a nadie.
- **Base imponible** (en la factura: "Op. Gravada", "Valor de venta" o "Subtotal"): el monto sobre el que se calcula el impuesto.
- **IGV:** el impuesto general a las ventas, 18 % de la base.
- **Serie y número:** por ejemplo `F001-00001234`. Junto con el RUC del emisor, identifican una factura de forma única.

| Regla | Si falla |
| --- | --- |
| El RUC del emisor tiene el dígito verificador correcto | A revisión: "RUC del emisor inválido" |
| La factura está a nombre de nuestra empresa | A revisión: "factura emitida a otro RUC" |
| La fecha de emisión no es futura | A revisión |
| El IGV es el 18 % de la base (±1 céntimo por redondeo) | A revisión |
| El total es base + IGV | A revisión |
| RUC + serie + número no están ya registrados | Duplicada: no se registra otra vez |

Una factura con problemas **no entra al registro**. Si el proveedor la corrige y la reenvía, se registra normalmente.

---

## Dónde entra la IA

Cada proveedor usa su propio sistema de facturación: uno escribe "Op. Gravada", otro "Valor de venta", otro "SUB TOTAL". La lectura por etiquetas cubre esas variantes sin costo.

Solo cuando al PDF le falta alguna etiqueta, el flujo le pasa el texto a un modelo de IA (nodo **Information Extractor** de n8n). Lo que devuelve la IA **pasa por las mismas validaciones**: si inventa un monto, el IGV o el total no cuadran y la factura va a revisión. Además, el prompt le prohíbe calcular datos que no aparecen.

Si la IA falla o no hay saldo, la factura va a revisión con ese motivo. Nunca se registra una factura a medias.

---

## Pruebas

<p align="center"><img src="docs/pruebas.png" alt="Resultados de las pruebas automáticas y de la verificación en n8n real" width="900"></p>

La integración continua corre todos los tests en cada push. Lo de la columna
derecha se verificó importando los workflows en n8n 2.40 con Docker.

---

## Probarlo en 2 minutos

```bash
pip install pytest
python scripts/generar_facturas.py   # 32 facturas PDF ficticias
python scripts/evaluar_lectura.py    # lectura y decisión de cada una
python -m pytest -v                  # 64 tests
```

**Con n8n de verdad** (Docker):

```bash
docker compose up -d
docker exec facturas_n8n n8n import:workflow --input=/workflows/facturas_demo.json
docker exec facturas_n8n n8n update:workflow --id=facturasdemo --active=true
docker restart facturas_n8n
```

Abre `demo/index.html` y arrastra PDFs de `data/facturas/`. Si subes el
mismo archivo dos veces, la segunda sale como duplicada. La configuración de
producción (Gmail, Google Sheets y modelo de IA) está en [`GUIA.md`](GUIA.md).

---

## Cómo se mide que funciona

`scripts/generar_facturas.py` crea 32 facturas con semilla fija, en 3
formatos de proveedor distintos, y anota qué debe pasar con cada una. Incluye
a propósito los casos difíciles: RUC con dígito verificador equivocado, IGV
inflado, total que no cuadra, fecha futura, factura a nombre de otra empresa,
montos en dólares, reenvíos duplicados y PDFs sin la etiqueta del IGV o del total.

| Resultado | |
| --- | --- |
| Campos bien leídos | 256 de 256 |
| Decisiones correctas (con el motivo correcto) | 32 de 32 |
| Registradas / a revisión / duplicadas / pasan a la IA | 23 / 5 / 2 / 2 |

Son facturas generadas, no reales: prueban que cada regla funciona, no que
se lea cualquier PDF del mercado. Un PDF escaneado como imagen, por ejemplo,
no tiene texto que extraer (ver [`GUIA.md`](GUIA.md)).

---

### El detalle que más cuesta ver

Los montos nunca se manejan con decimales, sino en **céntimos enteros**. En JavaScript `0.1 + 0.2` no da `0.3`, y la misma lógica corre en Python (para probarla) y en JavaScript (dentro de n8n). Con decimales, una factura podía pasar la validación en un lado y fallar en el otro.

Un test **ejecuta el código de los nodos de n8n fuera de n8n** y compara factura por factura contra Python, incluidos textos con símbolos como `º`. Por eso las expresiones regulares usan *lookarounds* en vez de `\b`: en Python `\b` reconoce letras Unicode y en JavaScript no.

---

## Estructura

```
├── data/
│   ├── facturas/                 # 32 PDFs ficticios y su texto
│   └── esperado.csv              # qué debe leer y decidir el flujo en cada una
├── src/facturas.py               # lectura, validación y decisión
├── workflows/
│   ├── src/validar_factura.js    # el código de los dos nodos Code
│   ├── facturas_demo.json        # importable, corre SIN credenciales
│   └── facturas_produccion.json  # Gmail + IA de respaldo + Google Sheets
├── demo/index.html               # sube PDFs al webhook y muestra el resultado
├── scripts/                      # generador de facturas, build y evaluación
├── tests/                        # 64 tests (incluye paridad JS ↔ Python)
└── docker-compose.yml            # n8n self-hosted
```

---

## Flujo de trabajo con Git

El repositorio sigue **Git Flow**: `main` siempre desplegable, `develop` como
integración, y una rama por cambio. Los merges son `--no-ff` para que cada
funcionalidad quede como un bloque legible en el historial, y cada versión
lleva su tag.

```mermaid
gitGraph
   commit id: "chore: set up the repository"
   branch develop
   checkout develop
   branch feature/lectura-facturas
   checkout feature/lectura-facturas
   commit id: "feat: read Peruvian e-invoice fields from the..."
   commit id: "test: cover reading, SUNAT rules and every de..."
   checkout develop
   merge feature/lectura-facturas
   branch feature/facturas-de-prueba
   checkout feature/facturas-de-prueba
   commit id: "feat: generate 32 fictitious invoice PDFs wit..."
   commit id: "feat: evaluate field reading and decisions ag..."
   commit id: "test: every generated invoice must produce it..."
   checkout develop
   merge feature/facturas-de-prueba
   branch feature/nodos-n8n
   checkout feature/nodos-n8n
   commit id: "feat: port reading and validation to the n8n ..."
   commit id: "test: run the n8n nodes outside n8n and compa..."
   checkout develop
   merge feature/nodos-n8n
   branch feature/workflows
   checkout feature/workflows
   commit id: "feat: build the demo and production workflows"
   commit id: "test: check the workflows import cleanly and ..."
   checkout develop
   merge feature/workflows
   branch feature/demo-web
   checkout feature/demo-web
   commit id: "feat: add a page to drop PDFs on the demo web..."
   commit id: "docs: add a screenshot of two invoices proces..."
   checkout develop
   merge feature/demo-web
   branch chore/ci
   checkout chore/ci
   commit id: "chore: run tests and the invoice evaluation o..."
   checkout develop
   merge chore/ci
   branch docs/documentacion
   checkout docs/documentacion
   commit id: "docs: explain the problem, the rules and wher..."
   commit id: "docs: add the production guide and known limits"
   checkout develop
   merge docs/documentacion
   branch release/v1.0.0
   checkout release/v1.0.0
   commit id: "chore(release): prepare v1.0.0"
   checkout main
   merge release/v1.0.0 tag: "v1.0.0"
   checkout develop
   merge release/v1.0.0
   branch docs/imagenes-readme
   checkout docs/imagenes-readme
   commit id: "docs: add architecture and test result images..."
   checkout develop
   merge docs/imagenes-readme
   branch release/v1.1.0
   checkout release/v1.1.0
   commit id: "chore(release): prepare v1.1.0"
   checkout main
   merge release/v1.1.0 tag: "v1.1.0"
   checkout develop
   merge release/v1.1.0
   branch feature/diagrama-git
   checkout feature/diagrama-git
   commit id: "feat: draw the Git Flow history as a Mermaid ..."
   checkout develop
   merge feature/diagrama-git
   branch docs/diagrama-git-flow
   checkout docs/diagrama-git-flow
   commit id: "docs: show the branch history as a gitGraph i..."
   checkout develop
   merge docs/diagrama-git-flow
   branch release/v1.1.1
   checkout release/v1.1.1
   commit id: "chore(release): prepare v1.1.1"
   checkout main
   merge release/v1.1.1 tag: "v1.1.1"
   checkout develop
   merge release/v1.1.1
   branch feature/canvas-ordenado
   checkout feature/canvas-ordenado
   commit id: "feat: lay out the canvas from the workflow co..."
   checkout develop
   merge feature/canvas-ordenado
   branch feature/documentar-workflow
   checkout feature/documentar-workflow
   commit id: "feat: document the n8n techniques each workfl..."
   checkout develop
   merge feature/documentar-workflow
```

<p align="center"><i>Historial real del repositorio, generado con
<code>python scripts/diagrama_git.py</code>.</i></p>

| Rama | Para qué |
| --- | --- |
| `main` | Solo versiones liberadas. Cada merge lleva su tag. |
| `develop` | Integración de todo lo terminado. |
| `feature/*` | Una funcionalidad nueva. |
| `fix/*` | Una corrección concreta. |
| `release/*` | Preparación de la versión; luego se fusiona a `main` y `develop`. |

Los mensajes siguen [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `test:`, `docs:`, `chore:`, con el porqué del cambio en el cuerpo.

---

## Documentación

| Documento | Contenido |
| --- | --- |
| [`GUIA.md`](GUIA.md) | Puesta en producción, arquitectura, límites y problemas de n8n encontrados al probar |
| [`CHANGELOG.md`](CHANGELOG.md) | Cambios por versión |

---

## Licencia

[MIT](LICENSE) · Daniel Yataco Blas

> Proyecto de demostración construido con **datos ficticios**. Las empresas,
> RUC y facturas no existen; los RUC tienen dígito verificador válido solo
> para poder probar la validación.
