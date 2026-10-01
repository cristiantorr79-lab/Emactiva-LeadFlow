import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('./public/', import.meta.url));
const MAX_BODY_BYTES = 16_384;
const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };

function json(res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(JSON.stringify(body));
}

export function sanitizeResult(statusCode, value) {
  const input = value && typeof value === 'object' ? value : {};
  const status = input.status === 'duplicate' || input.duplicate === true
    ? 'duplicate'
    : input.status === 'success' || input.ok === true
      ? 'success'
      : 'error';
  const result = { ok: status !== 'error', status };
  if (typeof input.execution_id === 'string') result.execution_id = input.execution_id.slice(0, 200);
  if (input.crm_action === 'created' || input.crm_action === 'updated') result.crm_action = input.crm_action;
  if (status === 'duplicate' && typeof input.original_execution_id === 'string') {
    result.original_execution_id = input.original_execution_id.slice(0, 200);
  }
  if (status === 'error') {
    result.ok = false;
    result.message = statusCode >= 500 ? 'LeadFlow no pudo procesar la solicitud.' : 'Revisa los datos de demostración.';
  }
  return result;
}

function sanitizeContacts(value) {
  const contacts = Array.isArray(value?.contacts) ? value.contacts : [];
  const fields = ['id', 'first_name', 'last_name', 'email', 'company'];
  return contacts.slice(0, 100).map((contact) => Object.fromEntries(
    fields
      .filter((field) => typeof contact?.[field] === 'string')
      .map((field) => [field, contact[field].slice(0, field === 'email' ? 254 : 200)])
  ));
}

function validLead(body) {
  return body && typeof body === 'object'
    && typeof body.event_id === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(body.event_id)
    && /[0-9._:-]/.test(body.event_id)
    && !/^\d+$/.test(body.event_id)
    && typeof body.source === 'string' && /^[a-z][a-z0-9_-]{0,63}$/.test(body.source)
    && body.lead && typeof body.lead === 'object'
    && typeof body.lead.first_name === 'string' && body.lead.first_name.length > 0 && body.lead.first_name.length <= 200
    && typeof body.lead.email === 'string' && body.lead.email.length <= 254
    && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.lead.email)
    && typeof body.lead.company === 'string' && body.lead.company.length > 0 && body.lead.company.length <= 200
    && ['first_name', 'last_name', 'company'].every((key) => body.lead[key] === undefined || (typeof body.lead[key] === 'string' && body.lead[key].length <= 200));
}

async function readJson(req) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (Buffer.byteLength(raw) > MAX_BODY_BYTES) throw new Error('body_too_large');
  }
  return JSON.parse(raw);
}

export function createDemoServer(config) {
  if (!config.webhookUrl || !config.webhookKey) throw new Error('DEMO_WEBHOOK_URL and DEMO_WEBHOOK_KEY are required');
  const target = new URL(config.webhookUrl);
  if (!['http:', 'https:'].includes(target.protocol)) throw new Error('DEMO_WEBHOOK_URL must use http or https');
  const crmTarget = new URL(config.crmUrl ?? 'http://127.0.0.1:5683/crm/contacts');
  if (!['http:', 'https:'].includes(crmTarget.protocol)) throw new Error('DEMO_CRM_URL must use http or https');

  return createServer(async (req, res) => {
    try {
      if (req.method === 'POST' && req.url === '/api/send') {
        const body = await readJson(req);
        if (!validLead(body)) return json(res, 400, { ok: false, status: 'error', message: 'Revisa los campos requeridos.' });
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), config.timeoutMs ?? 20_000);
        try {
          const upstream = await fetch(target, {
            method: 'POST',
            headers: { 'content-type': 'application/json', 'x-leadflow-key': config.webhookKey },
            body: JSON.stringify(body),
            signal: controller.signal
          });
          let value = {};
          try { value = await upstream.json(); } catch { value = {}; }
          return json(res, upstream.ok ? 200 : 502, sanitizeResult(upstream.status, value));
        } finally {
          clearTimeout(timer);
        }
      }

      if (req.method === 'GET' && req.url === '/api/crm/contacts') {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), config.timeoutMs ?? 20_000);
        try {
          const upstream = await fetch(crmTarget, { signal: controller.signal });
          if (!upstream.ok) return json(res, 502, { ok: false, message: 'No fue posible consultar el CRM de demostración.' });
          let value = {};
          try { value = await upstream.json(); } catch { value = {}; }
          return json(res, 200, { ok: true, contacts: sanitizeContacts(value) });
        } finally {
          clearTimeout(timer);
        }
      }

      if (req.method !== 'GET') return json(res, 405, { ok: false, status: 'error', message: 'Operación no permitida.' });
      const pathname = req.url === '/' ? 'index.html' : req.url === '/crm' ? 'crm.html' : req.url?.slice(1);
      if (!pathname || !['index.html', 'styles.css', 'app.js', 'crm.html', 'crm.css', 'crm.js'].includes(pathname)) return json(res, 404, { ok: false, status: 'error', message: 'Recurso no encontrado.' });
      const content = await readFile(join(ROOT, pathname));
      res.writeHead(200, { 'content-type': MIME[extname(pathname)], 'cache-control': 'no-store' });
      res.end(content);
    } catch {
      json(res, 502, { ok: false, status: 'error', message: 'No fue posible contactar LeadFlow.' });
    }
  });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const port = Number.parseInt(process.env.DEMO_PORT ?? '8095', 10);
  const host = process.env.DEMO_HOST ?? '127.0.0.1';
  const server = createDemoServer({
    webhookUrl: process.env.DEMO_WEBHOOK_URL,
    webhookKey: process.env.DEMO_WEBHOOK_KEY,
    crmUrl: process.env.DEMO_CRM_URL,
    timeoutMs: 20_000
  });
  server.listen(port, host, () => console.log(`LeadFlow Demo Sender: http://${host}:${port}`));
}
