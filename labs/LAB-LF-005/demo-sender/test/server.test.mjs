import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import test from 'node:test';
import { createDemoServer, sanitizeResult } from '../server.mjs';

const basePayload = { event_id: 'demo-lf009-001', source: 'website', lead: { first_name: 'Ana', email: 'ana@example.com', company: 'Empresa Sintética' } };

async function fixture(t, handler = (_req, res) => {
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ ok: true, status: 'success', execution_id: 'lf_1', crm_action: 'created' }));
}) {
  const upstream = createServer(handler).listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  t.after(() => upstream.close());
  const demo = createDemoServer({ webhookUrl: `http://127.0.0.1:${upstream.address().port}/leadflow`, webhookKey: 'fixture', allowedInterests: ['producto_a', 'asesoria'] }).listen(0, '127.0.0.1');
  await once(demo, 'listening');
  t.after(() => demo.close());
  return `http://127.0.0.1:${demo.address().port}`;
}

async function post(url, payload) {
  const response = await fetch(`${url}/api/send`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
  return { status: response.status, body: await response.json() };
}

test('sanitiza success, duplicate y processing recuperable', () => {
  assert.deepEqual(sanitizeResult(200, { ok: true, status: 'success', execution_id: 'lf_1', crm_action: 'created', token: 'never' }), { ok: true, status: 'success', execution_id: 'lf_1', crm_action: 'created' });
  assert.deepEqual(sanitizeResult(200, { status: 'duplicate', execution_id: 'lf_2', original_execution_id: 'lf_1', headers: {} }), { ok: true, status: 'duplicate', execution_id: 'lf_2', original_execution_id: 'lf_1' });
  assert.deepEqual(sanitizeResult(202, { status: 'processing', recoverable: true, execution_id: 'lf_3', error: { type: 'ambiguous_interaction', detail: 'hidden' } }), { ok: true, status: 'processing', execution_id: 'lf_3', recoverable: true, message: 'LeadFlow está confirmando la interacción. El proceso puede recuperarse de forma segura.' });
});

test('falla cerrado sin URL o clave', () => assert.throws(() => createDemoServer({}), /required/));

test('acepta V1 y propaga variantes válidas de interaction', async (t) => {
  const seen = [];
  const url = await fixture(t, async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    seen.push(JSON.parse(raw));
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, status: 'success', execution_id: `lf_${seen.length}` }));
  });
  for (const interaction of [undefined, { interest: 'producto_a', message: ' Consulta sintética ' }, { interest: 'asesoria' }, { message: 'Mensaje sintético' }, { interest: '  ', message: '\n ' }]) {
    const payload = { ...basePayload, event_id: `${basePayload.event_id}-${seen.length + 1}` };
    if (interaction) payload.interaction = interaction;
    assert.equal((await post(url, payload)).status, 200);
  }
  assert.equal(seen[0].interaction, undefined);
  assert.deepEqual(seen[1].interaction, { interest: 'producto_a', message: 'Consulta sintética' });
  assert.deepEqual(seen[2].interaction, { interest: 'asesoria' });
  assert.deepEqual(seen[3].interaction, { message: 'Mensaje sintético' });
  assert.equal(seen[4].interaction, undefined);
});

test('rechaza interaction inválida, límites y valor fuera de allowlist', async (t) => {
  let calls = 0;
  const url = await fixture(t, (_req, res) => { calls += 1; res.end('{}'); });
  const invalid = [null, [], 'texto', { interest: 7 }, { message: false }, { interest: 'x'.repeat(101) }, { message: 'x'.repeat(2001) }, { interest: 'no_configurado' }];
  for (const interaction of invalid) {
    const response = await post(url, { ...basePayload, interaction });
    assert.equal(response.status, 400);
    assert.deepEqual(response.body, { ok: false, status: 'error', message: 'Revisa los campos requeridos.' });
  }
  assert.equal(calls, 0);
});

test('conserva HTTP 202 recuperable y solo su respuesta pública', async (t) => {
  const url = await fixture(t, async (req, res) => {
    for await (const _ of req) { /* consume */ }
    res.writeHead(202, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ status: 'processing', recoverable: true, execution_id: 'lf_202', error: { type: 'ambiguous_interaction', internal: 'hidden' }, interaction: { message: 'hidden' } }));
  });
  const response = await post(url, { ...basePayload, interaction: { interest: 'producto_a' } });
  assert.equal(response.status, 202);
  assert.deepEqual(response.body, { ok: true, status: 'processing', execution_id: 'lf_202', recoverable: true, message: 'LeadFlow está confirmando la interacción. El proceso puede recuperarse de forma segura.' });
});

test('proxy CRM conserva solo contactos e interactions permitidas', async (t) => {
  const crm = createServer((_req, res) => {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ contacts: [{ id: 'c1', first_name: 'Sofía', last_name: 'Navarro', email: 'sofia@example.com', company: 'Compañía Demo', token: 'hidden', interactions: [{ id: 'i1', contact_id: 'c1', interest: 'producto_a', message: 'Mensaje sintético', operation_key: 'hidden' }] }] }));
  }).listen(0, '127.0.0.1');
  await once(crm, 'listening');
  t.after(() => crm.close());
  const webhook = createServer((_req, res) => res.end('{}')).listen(0, '127.0.0.1');
  await once(webhook, 'listening');
  t.after(() => webhook.close());
  const demo = createDemoServer({ webhookUrl: `http://127.0.0.1:${webhook.address().port}`, webhookKey: 'fixture', crmUrl: `http://127.0.0.1:${crm.address().port}/crm/contacts` }).listen(0, '127.0.0.1');
  await once(demo, 'listening');
  t.after(() => demo.close());
  const result = await fetch(`http://127.0.0.1:${demo.address().port}/api/crm/contacts`).then((r) => r.json());
  assert.deepEqual(result, { ok: true, contacts: [{ id: 'c1', first_name: 'Sofía', last_name: 'Navarro', email: 'sofia@example.com', company: 'Compañía Demo', interactions: [{ interest: 'producto_a', message: 'Mensaje sintético' }] }] });
});

test('UI y configuración cargan correctamente', async (t) => {
  const url = await fixture(t);
  const [page, script, crm, config] = await Promise.all([
    fetch(`${url}/`).then((r) => Promise.all([r.status, r.text()])),
    fetch(`${url}/app.js`).then((r) => Promise.all([r.status, r.text()])),
    fetch(`${url}/crm`).then((r) => Promise.all([r.status, r.text()])),
    fetch(`${url}/api/config`).then((r) => r.json())
  ]);
  assert.equal(page[0], 200);
  assert.match(page[1], /name="interest"/);
  assert.match(page[1], /name="message"/);
  assert.match(script[1], /demo-lf009-/);
  assert.equal(crm[0], 200);
  assert.match(crm[1], /CRM Demo View/);
  assert.deepEqual(config, { ok: true, allowed_interests: ['producto_a', 'asesoria'] });
});
