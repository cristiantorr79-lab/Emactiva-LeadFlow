const container = document.querySelector('#contacts');

function text(tag, value, className) {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  return element;
}

function detail(list, label, value) {
  if (!value) return;
  list.append(text('dt', label), text('dd', value));
}

function contactCard(contact) {
  const card = document.createElement('article');
  card.className = 'contact';
  const fullName = [contact.first_name, contact.last_name].filter(Boolean).join(' ') || 'Contacto de demostración';
  const details = document.createElement('dl');
  detail(details, 'Email', contact.email);
  detail(details, 'Empresa (Company)', contact.company);
  const interactions = Array.isArray(contact.interactions) ? contact.interactions : [];
  const interactionSection = document.createElement('section');
  interactionSection.className = 'interactions';
  interactionSection.append(text('h4', `Interacciones (${interactions.length})`));
  if (interactions.length === 0) interactionSection.append(text('p', 'Sin interacciones registradas.', 'no-interactions'));
  interactions.forEach((interaction, index) => {
    const item = document.createElement('article');
    item.className = 'interaction';
    const interactionDetails = document.createElement('dl');
    detail(interactionDetails, 'Interés (Interest)', interaction.interest);
    detail(interactionDetails, 'Mensaje (Message)', interaction.message);
    item.append(text('h5', `Interaction ${index + 1}`), interactionDetails);
    interactionSection.append(item);
  });
  card.append(text('p', 'Contacto registrado (Contact registered)', 'status'), text('h3', fullName, 'name'), details, interactionSection);
  return card;
}

async function loadContacts() {
  try {
    const response = await fetch('/api/crm/contacts', { headers: { accept: 'application/json' } });
    const data = await response.json();
    if (!response.ok || !data.ok || !Array.isArray(data.contacts)) throw new Error('controlled_error');
    if (data.contacts.length === 0) {
      container.replaceChildren(text('p', 'No hay contactos registrados todavía. (No contacts registered yet.)', 'empty'));
      return;
    }
    container.replaceChildren(...data.contacts.map(contactCard));
  } catch {
    container.replaceChildren(text('p', 'No fue posible consultar el CRM de demostración. (The demo CRM could not be reached.)', 'empty error'));
  }
}

loadContacts();
