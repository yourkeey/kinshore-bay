const cards = document.querySelector('#apartment-cards');
const catalogStatus = document.querySelector('#catalog-status');
const retryCatalog = document.querySelector('#retry-catalog');
const rate = new Intl.NumberFormat('en-IE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 2});

async function loadCatalog() {
  catalogStatus.textContent = 'Loading apartments…';
  retryCatalog.disabled = true;
  try {
    const response = await fetch('../content/en.json');
    if (!response.ok) throw new Error('Content unavailable');
    const content = await response.json();
    cards.innerHTML = content.apartments.map(room => {
      const name = escapeText(room.name);
      const url = './miniapp.html?room=' + encodeURIComponent(room.id);
      const image = /^[a-z0-9-]+\.webp$/.test(room.image || '') ? room.image : 'kinshore-apartment.webp';
      return `
        <article class="room-card">
          <img class="room-image" src="./assets/${image}" loading="lazy" width="640" height="420" alt="Concept interior for ${name}">
          <div class="room-card-body">
            <p class="room-meta">Up to ${room.guests} guests <span aria-hidden="true">·</span> ${room.size} m²</p>
            <h3>${name}</h3>
            <p>${escapeText(room.sleeping)}</p>
            ${room.outlook ? `<p class="room-outlook">${escapeText(room.outlook)}</p>` : ''}
            ${apartmentDetails(room)}
            <div class="room-card-footer">
              <p><strong>${rate.format(room.price)}</strong> / night</p>
              <a class="room-link" href="${url}" aria-label="Check dates for ${name}">Check dates <span aria-hidden="true">↗</span></a>
            </div>
          </div>
        </article>`;
    }).join('');
    if (!retryCatalog.hidden) cards.querySelector('a')?.focus();
    catalogStatus.textContent = content.apartments.length ? '' : 'There are no apartments in the demo catalog yet.';
    retryCatalog.hidden = true;
  } catch {
    catalogStatus.textContent = 'Could not load the apartments. Try again in a moment.';
    retryCatalog.hidden = false;
  } finally {
    retryCatalog.disabled = false;
  }
}
retryCatalog.addEventListener('click', loadCatalog);
loadCatalog();

document.querySelectorAll('[data-checkin]').forEach(node => { node.textContent = arrivalHours.checkin; });
document.querySelectorAll('[data-checkout]').forEach(node => { node.textContent = arrivalHours.checkout; });
document.querySelector('[data-walk-meeting]').textContent = shoreWalk.meeting;
document.querySelector('[data-inclusions]').textContent = inclusions;
document.querySelector('#saturday-agenda').innerHTML = saturday.map(activity => agendaItem(activity)).join('');

const allLayers = [{id: 'overview', label: 'Overview'}, ...placeGroups];
const pins = document.querySelector('#map-markers');
const keyList = document.querySelector('#map-key');
const layers = document.querySelector('#map-layers');
const mapPlan = document.querySelector('.map-plan');
const walkRoute = document.querySelector('#walk-route');
const routeButton = document.querySelector('#toggle-walk-route');
const mapNote = document.querySelector('#map-note');
const placeLink = document.querySelector('#map-place-link');
const directions = document.querySelector('#directions');
directions.textContent = `Meet at Pine terrace at ${shoreWalk.meeting} on Saturday. The guided walk runs from ${shoreWalk.start} to ${shoreWalk.end}. Ages 6 and up.`;

const keyChip = place => `<span class="map-chip ${place.group}-chip" aria-hidden="true">${place.key}</span>`;
pins.innerHTML = places.map(place => `
  <button class="map-pin${place.overview ? ' overview-pin' : ''}" type="button" data-place="${place.key}" data-group="${place.group}"
    aria-label="${place.name}" aria-pressed="false" id="${placeId(place)}" style="--place-x: ${place.x}%; --place-y: ${place.y}%">
    ${keyChip(place)}
  </button>`).join('');
keyList.innerHTML = placeGroups.map(group => `
  <div class="map-key-group" data-group="${group.id}">
    <h3>${group.label}</h3>
    <ul>${group.places.map(place => `
      <li><button type="button" data-place="${place.key}" aria-label="Show ${place.name} on map" aria-pressed="false">
        ${keyChip({...place, group: group.id})} <span>${place.name}</span>
      </button></li>`).join('')}</ul>
  </div>`).join('');
layers.innerHTML = allLayers.map(layer =>
  `<button type="button" data-layer="${layer.id}" aria-pressed="${layer.id === 'overview'}">${layer.label}</button>`).join('');

const locationButtons = document.querySelectorAll('[data-place]');
const layerButtons = layers.querySelectorAll('button');
const mapGroups = document.querySelectorAll('.map-pin, .map-key-group');

function showLayer(layer) {
  mapPlan.dataset.layer = layer;
  for (const button of layerButtons) button.setAttribute('aria-pressed', button.dataset.layer === layer);
  for (const item of mapGroups) item.hidden = layer !== 'overview' && item.dataset.group !== layer;
}

function showPlace(key) {
  const place = places.find(place => place.key === key);
  if (!place) return;
  for (const button of locationButtons) {
    const selected = button.dataset.place === key;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', selected);
  }
  document.querySelector('#map-place').textContent = place.name;
  directions.textContent = place.directions;
  mapNote.textContent = place.note || '';
  mapNote.hidden = !place.note;
  placeLink.hidden = !place.link;
  if (place.link) {
    placeLink.href = place.link[0];
    placeLink.textContent = place.link[1];
  }
}

function showWalkRoute(show) {
  routeButton.setAttribute('aria-pressed', show);
  routeButton.textContent = show ? 'Hide walk route' : 'Show walk route';
  walkRoute.hidden = !show;
  if (show) {
    showLayer('overview');
    showPlace('9');
  }
}

for (const button of locationButtons) {
  button.addEventListener('click', () => showPlace(button.dataset.place));
}
for (const button of layerButtons) {
  button.addEventListener('click', () => {
    showWalkRoute(false);
    showLayer(button.dataset.layer);
    const selectedGroup = placeGroups.find(group => group.id === button.dataset.layer);
    if (selectedGroup) showPlace(selectedGroup.places[0].key);
  });
}
routeButton.addEventListener('click', () => showWalkRoute(walkRoute.hidden));
function followMapLink() {
  const place = places.find(place => location.hash === '#' + placeId(place));
  if (!place) return;
  if (place.key === '9') showWalkRoute(true);
  else {
    showWalkRoute(false);
    showLayer(place.group);
    showPlace(place.key);
  }
  const marker = document.getElementById(placeId(place));
  marker.focus({preventScroll: true});
  marker.scrollIntoView({block: 'center'});
}
window.addEventListener('hashchange', followMapLink);
followMapLink();
