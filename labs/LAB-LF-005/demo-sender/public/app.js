const form = document.querySelector('#lead-form');
const result = document.querySelector('#result');
const send = document.querySelector('#send');
const demoSession = `${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${crypto.randomUUID().slice(0, 6)}`;
let demoSequence = 0;

function newEventId() {
  demoSequence += 1;
  return `demo-lf005-${demoSession}-${demoSequence}`;
}

function resetDefaults() {
  form.elements.first_name.value = 'Sofía';
  form.elements.last_name.value = 'Navarro';
  form.elements.email.value = `sofia.navarro.${Date.now()}@example.com`;
  form.elements.company.value = 'Compañía Demo';
  form.elements.source.value = 'website';
  form.elements.event_id.value = newEventId();
}

function show(data) {
  const status = ['success', 'duplicate'].includes(data.status) ? data.status : 'error';
  result.className = `result ${status}`;
  const headline = status === 'success' ? 'Lead procesado (Lead processed)' : status === 'duplicate' ? 'Duplicado detectado (Duplicate detected)' : 'Error controlado (Controlled error)';
  const details = [];
  if (data.execution_id) details.push(`execution_id: ${data.execution_id}`);
  if (data.crm_action) details.push(`crm_action: ${data.crm_action}`);
  if (data.original_execution_id) details.push(`original_execution_id: ${data.original_execution_id}`);
  if (data.message) details.push(data.message);
  result.replaceChildren(Object.assign(document.createElement('strong'), { textContent: headline }), Object.assign(document.createElement('span'), { textContent: details.join(' · ') || 'Respuesta sanitizada (Sanitized response).' }));
}

document.querySelector('#new-id').addEventListener('click', () => { form.elements.event_id.value = newEventId(); });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  send.disabled = true;
  result.className = 'result idle';
  result.textContent = 'Enviando… (Sending…)';
  const values = Object.fromEntries(new FormData(form));
  const lead = { first_name: values.first_name, email: values.email, company: values.company };
  if (values.last_name) lead.last_name = values.last_name;
  try {
    const response = await fetch('/api/send', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ event_id: values.event_id, source: values.source, lead }) });
    show(await response.json());
  } catch { show({ status: 'error', message: 'No fue posible contactar el Demo Sender. (The Demo Sender could not be reached.)' }); }
  finally { send.disabled = false; }
});

resetDefaults();
