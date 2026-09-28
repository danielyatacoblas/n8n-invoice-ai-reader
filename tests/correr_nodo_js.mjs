// Ejecuta el código de los nodos Code de n8n fuera de n8n, simulando sus globals.
// Uso:  node tests/correr_nodo_js.mjs <texto|ia> <entrada.json> <hoy AAAA-MM-DD>
//   texto: la entrada es una lista de textos de PDF
//   ia:    la entrada es una lista de salidas del extractor de IA (o null si falló)
// Salida: JSON por stdout con el resultado de cada factura.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const [modo, rutaEntrada, hoy] = process.argv.slice(2);

const jsCode = readFileSync(join(ROOT, 'workflows', 'src', 'validar_factura.js'), 'utf8')
  .replace("'__MODO__'", `'${modo}'`)
  .replace("'__REGISTRO__'", "'memoria'");

const entrada = JSON.parse(readFileSync(rutaEntrada, 'utf8'));

const staticData = {};
const $getWorkflowStaticData = () => staticData;
const $now = { toISODate: () => hoy };

const nodos = {
  'Extraer texto del PDF': entrada.map((text) => ({ json: { text } })),
  'Leer y validar factura': entrada.map(() => ({
    json: { estado: 'faltan_datos', origen: 'texto', clave: '', faltantes: ['total'],
            errores: [], factura: { ruc_emisor: '20555666773', serie: 'F001', numero: '00000001',
            fecha: '2026-09-01', moneda: 'PEN', base: 1000, igv: 180, total: null } },
  })),
};
const $ = (nombre) => ({
  all: () => nodos[nombre],
  itemMatching: (i) => nodos[nombre][i],
});
const $input = { all: () => entrada.map((output) => ({ json: output ? { output } : { error: 'sin credencial' } })) };

const ejecutarNodo = new Function('$', '$input', '$getWorkflowStaticData', '$now', jsCode);
const salida = ejecutarNodo($, $input, $getWorkflowStaticData, $now);

process.stdout.write(JSON.stringify(salida.map((s) => s.json)));
