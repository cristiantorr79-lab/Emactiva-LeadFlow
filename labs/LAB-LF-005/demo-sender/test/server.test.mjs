import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import test from 'node:test';
import { createDemoServer, sanitizeResult } from '../server.mjs';

test('sanitiza resultados y no propaga campos internos', () => {
  const value = sanitizeResult(200, { ok: true, status: 'success', execution_id: 'lf_1', crm_action: 'created', token: 'never', headers: { secret: true } });
  assert.deepEqual(value, { ok: true, status: 'success', execution_id: 'lf_1', crm_action: 'created' });
});

test('falla cerrado sin URL o clave', () => {
  assert.throws(() => createDemoServer({}), /required/);
});

test('envía sintético y permite observar success y duplicate', async (t) => {
  let calls = 0;
  let seenKey;
  const upstream = createServer(async (req, res) => {
    seenKey = req.headers['x-leadflow-key'];
    for await (const _ of req) { /* consume request */ }
    calls += 1;
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify(calls === 1
      ? { ok: true, status: 'success', execution_id: 'lf_demo_1', crm_action: 'created', internal: 'hidden' }
      : { ok: true, status: 'duplicate', duplicate: true, execution_id: 'lf_demo_2', original_execution_id: 'lf_demo_1' }));
  }).listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  t.after(() => upstream.close());

  const endpoint = `http://127.0.0.1:${upstream.address().port}/leadflow`;
  const demo = createDemoServer({ webhookUrl: endpoint, webhookKey: 'fixture' }).listen(0, '127.0.0.1');
  await once(demo, 'listening');
  t.after(() => demo.close());
  const url = `http://127.0.0.1:${demo.address().port}/api/send`;
  const payload = { event_id: 'demo-001', source: 'website', lead: { first_name: 'Ana', email: 'ana@example.com', company: 'Empresa Sintética' } };

  const page = await fetch(`http://127.0.0.1:${demo.address().port}/`).then((r) => Promise.all([r.status, r.text()]));
  assert.equal(page[0], 200);
  assert.match(page[1], /Emactiva LeadFlow — Demo/);

  const invalid = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...payload, event_id: '123456' }) });
  assert.equal(invalid.status, 400);
  assert.deepEqual(await invalid.json(), { ok: false, status: 'error', message: 'Revisa los campos requeridos.' });
  assert.equal(calls, 0);

  const first = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) }).then((r) => r.json());
  const second = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) }).then((r) => r.json());
  assert.deepEqual(first, { ok: true, status: 'success', execution_id: 'lf_demo_1', crm_action: 'created' });
  assert.deepEqual(second, { ok: true, status: 'duplicate', execution_id: 'lf_demo_2', original_execution_id: 'lf_demo_1' });
  assert.equal(seenKey, 'fixture');
  assert.equal(calls, 2);
});
