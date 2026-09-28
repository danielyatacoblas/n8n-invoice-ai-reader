// Nodos Code de n8n: "Leer y validar factura" y "Validar lectura de la IA".
// Espejo en JavaScript de src/facturas.py (misma lógica, misma salida).
// La paridad entre ambos la verifica tests/test_paridad_js.py.
//
// El mismo archivo genera los dos nodos. scripts/build_workflow.py fija:
//   MODO      'texto' → lee el texto del PDF;  'ia' → valida lo que leyó el modelo
//   REGISTRO  'memoria' (demo) o 'sheets' (producción) para detectar duplicados

const MODO = '__MODO__';
const REGISTRO = '__REGISTRO__';

const RUC_EMPRESA = '20601234565';
const TASA_IGV = 18;
const TOLERANCIA = 1;
const FACTORES_RUC = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
const CAMPOS = ['ruc_emisor', 'serie', 'numero', 'fecha', 'moneda', 'base', 'igv', 'total'];

const ETIQUETAS = {
  base: ['op. gravada', 'op gravada', 'operacion gravada', 'valor de venta',
    'sub total', 'subtotal'],
  igv: ['igv', 'i.g.v.'],
  total: ['importe total', 'total a pagar', 'total'],
};
const MONTO = '(?:s/|us\\$|\\$|pen|usd)?\\s*(\\d[\\d,]*(?:\\.\\d{1,2})?)';

// ── utilidades ──

const plano = (texto) =>
  (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

const escaparRegex = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function aCentimos(valor) {
  if (valor === null || valor === undefined) return null;
  const t = String(valor).trim().replace(/,/g, '');
  let m = t.match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!m) {
    m = t.match(/^(\d+)\.(\d+)$/);         // 1180.004 de un modelo de IA
    if (!m) return null;
  }
  const decimales = (m[2] || '').padEnd(2, '0').slice(0, 2);
  return parseInt(m[1], 10) * 100 + parseInt(decimales, 10);
}

function rucValido(ruc) {
  if (!/^\d{11}$/.test(ruc || '') || !['10', '15', '17', '20'].includes(ruc.slice(0, 2))) {
    return false;
  }
  let suma = 0;
  for (let i = 0; i < 10; i++) suma += Number(ruc[i]) * FACTORES_RUC[i];
  const resto = 11 - (suma % 11);
  const verificador = resto === 10 ? 0 : resto === 11 ? 1 : resto;
  return Number(ruc[10]) === verificador;
}

function fechaIso(texto) {
  const t = (texto || '').trim();
  let d, mes, a;
  let m = t.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) {
    [d, mes, a] = [Number(m[1]), Number(m[2]), Number(m[3])];
  } else {
    m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    [a, mes, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  }
  const f = new Date(Date.UTC(a, mes - 1, d));
  if (a < 1 || f.getUTCFullYear() !== a || f.getUTCMonth() !== mes - 1 || f.getUTCDate() !== d) {
    return null;
  }
  return String(a).padStart(4, '0') + '-' + String(mes).padStart(2, '0') + '-' +
    String(d).padStart(2, '0');
}

function clave(f) {
  if (!f.ruc_emisor || !f.serie || !f.numero) return '';
  return f.ruc_emisor + '-' + f.serie + '-' + f.numero;
}

// ── lectura del texto del PDF ──

function monto(textoPlano, etiquetas) {
  for (const etiqueta of etiquetas) {
    const patron = new RegExp('(?:^|\\n)[ \\t]*' + escaparRegex(etiqueta) +
      '[^\\n\\d]*?(?:\\(\\s*18\\s*%\\s*\\))?[ \\t]*:?[ \\t]*' + MONTO);
    const m = textoPlano.match(patron);
    if (m) return aCentimos(m[1]);
  }
  return null;
}

function leerTexto(texto) {
  const p = plano(texto);
  const rucs = [...p.matchAll(/r\.?\s*u\.?\s*c\.?[^\d\n]{0,6}(\d{11})/g)].map((m) => m[1]);
  const serie = p.match(/(?<![a-z0-9])([fe][a-z0-9]{3})\s*-\s*(\d{1,8})(?![0-9])/);
  const fecha = p.match(/fecha\s*(?:de\s*)?emision[^\d\n]*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2})/);
  let moneda = null;
  if (/dolar|us\$|(?<![a-z])usd(?![a-z])/.test(p)) moneda = 'USD';
  else if (/(?<![a-z])soles(?![a-z])|s\/|(?<![a-z])pen(?![a-z])/.test(p)) moneda = 'PEN';
  return {
    ruc_emisor: rucs.length ? rucs[0] : null,
    ruc_cliente: rucs.length > 1 ? rucs[1] : null,
    serie: serie ? serie[1].toUpperCase() : null,
    numero: serie ? serie[2].padStart(8, '0') : null,
    fecha: fecha ? fechaIso(fecha[1]) : null,
    moneda,
    base: monto(p, ETIQUETAS.base),
    igv: monto(p, ETIQUETAS.igv),
    total: monto(p, ETIQUETAS.total),
  };
}

function desdeIa(salida) {
  const texto = (k) => {
    const v = salida[k];
    return (v === null || v === undefined || v === '') ? null : String(v).trim();
  };
  const moneda = (texto('moneda') || '').toUpperCase();
  const numero = (texto('numero') || '').replace(/\D/g, '');
  const rucE = (texto('ruc_emisor') || '').replace(/\D/g, '');
  const rucC = (texto('ruc_cliente') || '').replace(/\D/g, '');
  return {
    ruc_emisor: rucE || null,
    ruc_cliente: rucC || null,
    serie: (texto('serie') || '').toUpperCase() || null,
    numero: numero ? numero.padStart(8, '0') : null,
    fecha: fechaIso(texto('fecha') || ''),
    moneda: ['PEN', 'USD'].includes(moneda) ? moneda : null,
    base: aCentimos(texto('base')),
    igv: aCentimos(texto('igv')),
    total: aCentimos(texto('total')),
  };
}

// ── validación ──

function validar(f, hoy) {
  const errores = [];
  if (!rucValido(f.ruc_emisor)) errores.push('RUC del emisor inválido');
  if (f.ruc_cliente && f.ruc_cliente !== RUC_EMPRESA) errores.push('factura emitida a otro RUC');
  if (f.fecha > hoy) errores.push('fecha de emisión en el futuro');
  const igvEsperado = Math.floor((f.base * TASA_IGV + 50) / 100);
  if (Math.abs(f.igv - igvEsperado) > TOLERANCIA) errores.push('el IGV no es el 18 % de la base');
  if (Math.abs(f.base + f.igv - f.total) > TOLERANCIA) errores.push('el total no es base + IGV');
  return errores;
}

function procesar(f, registro, hoy, origen) {
  const faltantes = CAMPOS.filter((c) => f[c] === null || f[c] === undefined || f[c] === '');
  const resultado = { estado: '', origen, factura: f, clave: clave(f), faltantes, errores: [] };

  if (faltantes.length) {
    if (origen === 'texto') {
      resultado.estado = 'faltan_datos';
    } else {
      resultado.estado = 'revision';
      resultado.errores = ['faltan datos: ' + faltantes.join(', ')];
    }
    return resultado;
  }

  if (registro.includes(resultado.clave)) {
    resultado.estado = 'duplicada';
    return resultado;
  }

  const errores = validar(f, hoy);
  resultado.errores = errores;
  resultado.estado = errores.length ? 'revision' : 'registrada';
  if (!errores.length) registro.push(resultado.clave);
  return resultado;
}

function filaHoja(r) {
  const f = r.factura;
  const soles = (c) => (c === null || c === undefined) ? ''
    : Math.floor(c / 100) + '.' + String(c % 100).padStart(2, '0');
  return {
    clave: r.clave, estado: r.estado,
    ruc_emisor: f.ruc_emisor || '', serie: f.serie || '',
    numero: f.numero || '', fecha: f.fecha || '',
    moneda: f.moneda || '', base: soles(f.base),
    igv: soles(f.igv), total: soles(f.total),
    leida_por: r.origen, observaciones: r.errores.join('; '),
  };
}

// ── Ejecución en n8n ──

function leerRegistro() {
  if (REGISTRO === 'sheets') {
    // alwaysOutputData deja un item vacío cuando la hoja no tiene filas
    return $('Sheets · Leer facturas').all().map((i) => String(i.json.clave || '')).filter(Boolean);
  }
  const memoria = $getWorkflowStaticData('global');
  if (!Array.isArray(memoria.registro)) memoria.registro = [];
  return memoria.registro;
}

const registro = leerRegistro();
const hoy = $now.toISODate();

// En modo texto se lee del nodo que extrajo el PDF (en producción, $input trae
// las filas de la hoja). En modo IA, $input es la salida del extractor.
if (MODO === 'texto') {
  return $('Extraer texto del PDF').all().map((item) => {
    const texto = String(item.json.text || '');
    const r = procesar(leerTexto(texto), registro, hoy, 'texto');
    return { json: Object.assign(r, { fila: filaHoja(r), texto }) };
  });
}

return $input.all().map((item, i) => {
  // Si falla el modelo (sin credencial, sin saldo, caído), n8n entrega el
  // error por la salida normal del extractor, no por la de error. Sin esto la
  // factura llegaría a revisión como "faltan todos los datos".
  if (!item.json.output) {
    const previo = $('Leer y validar factura').itemMatching(i).json;
    const r = Object.assign({}, previo, {
      estado: 'revision', origen: 'ia', errores: ['la IA no pudo leer la factura'],
    });
    return { json: Object.assign(r, { fila: filaHoja(r), texto: '' }) };
  }
  const r = procesar(desdeIa(item.json.output), registro, hoy, 'ia');
  return { json: Object.assign(r, { fila: filaHoja(r), texto: '' }) };
});
