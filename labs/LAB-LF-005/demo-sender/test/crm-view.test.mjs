import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer as createNetServer } from 'node:net';
import test from 'node:test';
import { createDemoServer } from '../server.mjs';

async function freePort() {
  const server = createNetServer().listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = server.address().port;
  server.close();
  await once(server, 'close');
  return port;
}

async function waitFor(url) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try { if ((await fetch(url)).ok) return; } catch { /* startup pending */ }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Mock did not start: ${url}`);
}

async function startMock(port) {
  const child = spawn('python', ['mocks/server.py'], {
    cwd: process.cwd(),
    env: { ...process.env, MOCK_KIND: 'crm', MOCK_PORT: String(port) },
    stdio: 'ignore',
    windowsHide: true
  });
  await waitFor(`http://127.0.0.1:${port}/healthz`);
  return child;
}

async function stopMock(child) {
  if (child.exitCode !== null) return;
  child.kill();
  await once(child, 'exit');
}

test('CRM Demo View refleja el mock, es solo lectura y deja cleanup limpio', async (t) => {
  const mockPort = await freePort();
  let mock = await startMock(mockPort);
  t.after(async () => stopMock(mock));
  const mockBase = `http://127.0.0.1:${mockPort}`;

  const demo = createDemoServer({
    webhookUrl: 'http://127.0.0.1:9/unused',
    webhookKey: 'fixture',
    crmUrl: `${mockBase}/crm/contacts`,
    timeoutMs: 1_000
  }).listen(0, '127.0.0.1');
  await once(demo, 'listening');
  t.after(() => demo.close());
  const demoBase = `http://127.0.0.1:${demo.address().port}`;

  const page = await fetch(`${demoBase}/crm`);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /CRM Demo View/);

  const empty = await fetch(`${demoBase}/api/crm/contacts`).then((response) => response.json());
  assert.deepEqual(empty, { ok: true, contacts: [] });

  const lead = { first_name: 'Sofía', last_name: 'Navarro', email: 'sofia.crm.demo@example.com', company: 'Compañía Demo', phone: '+56000000000' };
  const created = await fetch(`${mockBase}/crm/contacts`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ lead, operation_key: 'demo-crm-view-001' })
  }).then((response) => response.json());
  assert.equal(created.created, true);

  const lookup = await fetch(`${mockBase}/crm/lookup`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: lead.email })
  }).then((response) => response.json());
  assert.deepEqual(lookup, { found: true, contact: { id: created.contact_id, email: lead.email } });
  const individual = await fetch(`${mockBase}/crm/contacts/${created.contact_id}`).then((response) => response.json());
  assert.equal(individual.contact.company, lead.company);

  const statsBefore = await fetch(`${mockBase}/stats`).then((response) => response.json());
  const listed = await fetch(`${demoBase}/api/crm/contacts`).then((response) => response.json());
  const statsAfter = await fetch(`${mockBase}/stats`).then((response) => response.json());
  assert.deepEqual(listed, { ok: true, contacts: [{ id: created.contact_id, first_name: 'Sofía', last_name: 'Navarro', email: 'sofia.crm.demo@example.com', company: 'Compañía Demo' }] });
  assert.deepEqual(statsAfter, statsBefore);
  assert.equal(JSON.stringify(listed).includes('phone'), false);

  const writeAttempt = await fetch(`${demoBase}/api/crm/contacts`, { method: 'POST' });
  assert.equal(writeAttempt.status, 405);

  await stopMock(mock);
  mock = await startMock(mockPort);
  const clean = await fetch(`${mockBase}/crm/contacts`).then((response) => response.json());
  assert.deepEqual(clean, { contacts: [] });
});
