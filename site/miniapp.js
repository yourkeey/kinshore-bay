const roomImageStyle = room => /^[a-z0-9-]+\.webp$/.test(room.image || '') ? ` style="background-image: url('./assets/${room.image}')"` : '';
const form = document.querySelector('#finder');
const cards = document.querySelector('#mini-cards');
const summary = document.querySelector('#result-summary');
const checkin = document.querySelector('#checkin');
const checkout = document.querySelector('#checkout');
const dialog = document.querySelector('#calendar-dialog');
const calendarGrid = document.querySelector('#calendar-grid');
const calendarMonth = document.querySelector('#calendar-month');
const calendarInstructions = document.querySelector('#calendar-instructions');
const previousMonth = document.querySelector('#calendar-prev');
const nextMonth = document.querySelector('#calendar-next');
const calendarTrigger = document.querySelector('#open-calendar');
const resultsTitle = document.querySelector('#results-title');
const stayTitle = document.querySelector('#my-stay-title');
const refreshButton = document.querySelector('#refresh-stay');
const submitButton = form.querySelector('.finder-submit');
let apartments = [];
const category = document.querySelector('#category');
const guestsField = document.querySelector('#guests');
const budgetField = document.querySelector('#budget');
const draftKey = 'kinshore.stay.v1';
const arrivalDraftKey = 'kinshore.arrival.v1';

function remember() {
  const draft = {room: category.value, guests: guestsField.value, budget: budgetField.value,
    start: checkin.value, end: checkout.value};
  try { sessionStorage.setItem(draftKey, JSON.stringify(draft)); } catch { /* Storage is optional. */ }
}

function restore() {
  let draft = {};
  try { draft = JSON.parse(sessionStorage.getItem(draftKey)) || {}; } catch { /* Start fresh. */ }
  const requested = new URLSearchParams(location.search).get('room') ?? draft.room;
  category.value = apartments.some(room => room.id === requested) ? requested : '';
  if (['1','2','3','4','5','6'].includes(draft.guests)) guestsField.value = draft.guests;
  if (['any','120','160','220'].includes(draft.budget)) budgetField.value = draft.budget;
  if (typeof draft.start === 'string' && typeof draft.end === 'string' &&
      /^\d{4}-\d{2}-\d{2}$/.test(draft.start) && /^\d{4}-\d{2}-\d{2}$/.test(draft.end) &&
      draft.start >= checkin.min && draft.start <= checkin.max &&
      draft.end > draft.start && draft.end <= plusDays(draft.start, 90)) {
    checkin.value = draft.start;
    checkout.value = draft.end;
  }
  updateDateDisplay();
}

function localDate(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
const today = new Date(new Date().toISOString().slice(0, 10) + 'T12:00:00');
const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
checkin.min = localDate(today);
const maximumCheckin = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 730);
checkin.max = localDate(maximumCheckin);
checkin.value = localDate(today);
checkout.value = localDate(tomorrow);
let shownMonth = new Date(today.getFullYear(), today.getMonth(), 1);
let draftStart = '', draftEnd = '', selecting = 'start';
const displayDate = value => value ? new Intl.DateTimeFormat('en', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'}).format(new Date(`${value}T00:00:00Z`)) : 'Select date';
const plusDays = (value, days) => { const d = new Date(`${value}T12:00:00`); d.setDate(d.getDate() + days); return localDate(d); };
function updateDateDisplay() {
  document.querySelector('#checkin-display').textContent = displayDate(checkin.value);
  document.querySelector('#checkout-display').textContent = displayDate(checkout.value);
}
function renderCalendar(preferredDate) {
  const year = shownMonth.getFullYear(), month = shownMonth.getMonth();
  calendarMonth.textContent = new Intl.DateTimeFormat('en', {month: 'long', year: 'numeric'}).format(shownMonth);
  calendarInstructions.textContent = selecting === 'start' ? 'Select your check-in date.' : `Check-in ${displayDate(draftStart)} · now select check-out.`;
  const startOffset = (new Date(year, month, 1).getDay() + 6) % 7;
  const days = new Date(year, month + 1, 0).getDate();
  const lastDate = selecting === 'start' ? checkin.max : plusDays(draftStart, 90);
  const firstDate = selecting === 'start' ? checkin.min : plusDays(draftStart, 1);
  const minMonth = firstDate.slice(0, 7), maxMonth = lastDate.slice(0, 7), currentMonth = localDate(shownMonth).slice(0, 7);
  const firstInMonth = currentMonth === minMonth ? firstDate : localDate(shownMonth);
  const activeDate = preferredDate?.startsWith(currentMonth) && preferredDate >= firstDate && preferredDate <= lastDate
    ? preferredDate : firstInMonth;
  previousMonth.disabled = currentMonth <= minMonth;
  nextMonth.disabled = currentMonth >= maxMonth;
  let html = '<span class="calendar-blank"></span>'.repeat(startOffset);
  for (let day = 1; day <= days; day++) {
    const value = localDate(new Date(year, month, day));
    const disabled = value < firstDate || value > lastDate;
    const selected = value === draftStart || value === draftEnd;
    const between = draftStart && draftEnd && value > draftStart && value < draftEnd;
    const state = selected ? ' selected' : between ? ' in-range' : '';
    html += `<button type="button" class="calendar-day${state}" data-date="${value}" aria-label="${displayDate(value)}" aria-pressed="${selected}" tabindex="${value === activeDate ? 0 : -1}" ${disabled ? 'disabled' : ''}>${day}</button>`;
  }
  calendarGrid.innerHTML = html;
}
function focusCalendarDay() {
  calendarGrid.querySelector('[tabindex="0"]')?.focus();
}

calendarTrigger.addEventListener('click', () => {
  selecting = 'start'; draftStart = checkin.value; draftEnd = checkout.value;
  const date = new Date(`${checkin.value || checkin.min}T12:00:00`);
  shownMonth = new Date(date.getFullYear(), date.getMonth(), 1);
  renderCalendar(checkin.value);
  dialog.showModal();
  focusCalendarDay();
});
document.querySelector('#calendar-close').addEventListener('click', () => dialog.close());
document.querySelector('#calendar-reset').addEventListener('click', () => {
  draftStart = ''; draftEnd = ''; selecting = 'start'; shownMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  renderCalendar();
  focusCalendarDay();
});
function shiftMonth(direction, button) {
  shownMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + direction, 1);
  renderCalendar();
  if (button.disabled) focusCalendarDay();
}
previousMonth.addEventListener('click', () => shiftMonth(-1, previousMonth));
nextMonth.addEventListener('click', () => shiftMonth(1, nextMonth));
calendarGrid.addEventListener('keydown', event => {
  const offset = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
  const currentDate = event.target.dataset.date;
  if (!offset || !currentDate) return;
  event.preventDefault();
  const newDate = plusDays(currentDate, offset);
  const firstDate = selecting === 'start' ? checkin.min : plusDays(draftStart, 1);
  const lastDate = selecting === 'start' ? checkin.max : plusDays(draftStart, 90);
  if (newDate < firstDate || newDate > lastDate) return;
  const day = new Date(`${newDate}T12:00:00`);
  shownMonth = new Date(day.getFullYear(), day.getMonth(), 1);
  renderCalendar(newDate);
  focusCalendarDay();
});
calendarGrid.addEventListener('click', event => {
  const button = event.target.closest('button[data-date]');
  if (!button || button.disabled) return;
  const selected = button.dataset.date;
  if (selecting === 'start') {
    draftStart = selected; draftEnd = ''; selecting = 'end';
    const nextDay = new Date(`${plusDays(selected, 1)}T12:00:00`);
    if (nextDay.getMonth() !== shownMonth.getMonth()) shownMonth = new Date(nextDay.getFullYear(), nextDay.getMonth(), 1);
    renderCalendar(localDate(nextDay));
    focusCalendarDay();
  } else {
    if (selected <= draftStart || selected > plusDays(draftStart, 90)) return;
    draftEnd = selected; checkin.value = draftStart; checkout.value = draftEnd;
    updateDateDisplay(); dialog.close(); calculate();
  }
});
updateDateDisplay();

let quoteSequence = 0;
let offers = [];
let csrf = '';
let sending = false;
const message = document.querySelector('#request-message');
const stayList = document.querySelector('#stay-list');
const tripDialog = document.querySelector('#trip-dialog');
const tripForm = document.querySelector('#trip-details');
const tripChildren = document.querySelector('#trip-children');
const tripPet = document.querySelector('#trip-pet');
const tripCar = document.querySelector('#trip-car');
let requestPayload;
const euros = cents => new Intl.NumberFormat('en-IE', {style: 'currency', currency: 'EUR',
  minimumFractionDigits: cents % 100 ? 2 : 0}).format(cents / 100);

function renderWalk(stay, walk) {
  const reference = escapeText(stay.reference);
  const walkId = `walk-${reference}-${walk.id}`;
  const action = walk.booking ? 'cancel' : 'book';
  const maxParty = Math.min(stay.guests, walk.remaining);
  const status = walk.cancelled ? 'Cancelled by the club'
    : walk.booking ? `Booked · ${walk.booking.seats} ${walk.booking.seats === 1 ? 'place' : 'places'}`
    : walk.remaining ? `${walk.remaining} of ${walk.capacity} places available` : 'Fully booked';
  const fields = walk.booking ? '' : `
    <p id="${walkId}-rules">Ages 6 and up. Participants under 16 must be accompanied by an adult.</p>
    <div class="walk-party">
      <label>Adults 18+ <input type="number" name="adults" min="0" max="${maxParty}" value="1" required aria-describedby="${walkId}-rules"></label>
      <label>Ages 16–17 <input type="number" name="teens" min="0" max="${maxParty}" value="0" required aria-describedby="${walkId}-rules"></label>
      <label>Ages 6–15 <input type="number" name="children" min="0" max="${maxParty - 1}" value="0" required aria-describedby="${walkId}-rules"></label>
    </div>`;
  const bookable = walk.open && (walk.booking || maxParty > 0);
  return `<section class="stay-walk" aria-labelledby="${walkId}">
    <h4 id="${walkId}" tabindex="-1">${escapeText(walk.title)}</h4>
    <p>${displayDate(walk.day)} · ${escapeText(walk.starts_at)}–${escapeText(walk.ends_at)}</p>
    <p>Meet at <a href="./index.html#pine-terrace">${escapeText(walk.meeting_point)}</a> at ${escapeText(walk.meeting_at)}.</p>
    <p><strong>${status}</strong></p>
    ${bookable ? `<form class="walk-form" data-reference="${reference}" data-walk="${walk.id}" data-action="${action}" data-max="${maxParty}">
      ${fields}
      <p class="walk-feedback" role="status"></p>
      <button type="submit" class="${walk.booking ? 'secondary-action' : 'button button-dark'}">${walk.booking ? 'Cancel walk booking' : 'Book the walk'}</button>
    </form>` : ''}
  </section>`;
}

function renderStayGuide(stay) {
  if (!['confirmed', 'checked_in'].includes(stay.status)) return '';
  const building = String(stay.building || '');
  const buildingStep = building ?
    `<li><a class="stay-map-link" href="./index.html#building-${encodeURIComponent(building.toLowerCase())}">Find Building ${escapeText(building)} on the map</a></li>` : '';
  const entryStep = stay.by_car === false
    ? '<li>Walk through the <a href="./index.html#arrival-gate">arrival gate</a> and follow the path to Reception.</li>'
    : `<li>Use the <a href="./index.html#arrival-gate">arrival gate</a>.</li>
       <li>Try <a href="./index.html#covered-parking">covered parking</a> first. If it’s full, use the <a href="./index.html#guest-parking">open guest lot</a>.</li>`;
  return `
    <details class="stay-arrival"${stay.status === 'confirmed' ? ' open' : ''}>
      <summary>Arrival &amp; what's included</summary>
      <ol>
        ${entryStep}
        <li>Collect your keys at <a href="./index.html#reception">Reception</a> from ${arrivalHours.checkin}. Have your stay reference handy.</li>
        ${buildingStep}
      </ol>
      <p><strong>Included</strong> ${inclusions}</p>
      <p>Return your keys by ${arrivalHours.checkout} on check-out day.</p>
    </details>
    <p class="stay-leisure"><a href="./index.html#garden-pool">Family pool</a> · <a href="./index.html#games-room">Games room</a> · <a href="./index.html#bay-kitchen">Bay Kitchen</a> · <a href="./index.html#grill-pergolas">Grill pergolas</a></p>`;
}

function renderArrivalDetails(stay) {
  const details = [];
  if (Number.isInteger(stay.children)) details.push(`${stay.children} under 18`);
  if (stay.with_pet === true) details.push('Bringing a pet');
  if (stay.by_car === true) details.push('Arriving by car');
  return details.length ? `<p class="stay-trip-labels">${details.join(' · ')}</p>` : '';
}

function renderGrills(grills) {
  if (!grills?.length) return '';
  return `<section class="stay-walk">
    <h4><a href="./index.html#grill-pergolas">Grill pergolas</a></h4>
    <ul>${grills.map(booking => `<li>${displayDate(booking.day)} · ${escapeText(booking.time)} · Table ${escapeText(booking.table)}</li>`).join('')}</ul>
    <p>Ask Reception if you need to change your time.</p>
  </section>`;
}

function renderSaturdayDropIns(stay) {
  if (!['confirmed', 'checked_in'].includes(stay.status)) return '';
  const day = new Date(`${stay.checkin}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + (6 - day.getUTCDay()));
  const firstArrival = `${stay.checkin}T${arrivalHours.checkin}`;
  const lastDeparture = `${stay.checkout}T${arrivalHours.checkout}`;
  const dropIns = saturday.filter(activity => !activity.meeting);
  const days = [];
  for (let key = day.toISOString().slice(0, 10); key <= stay.checkout; key = day.toISOString().slice(0, 10)) {
    const activities = dropIns.filter(activity => `${key}T${activity.start}` >= firstArrival && `${key}T${activity.end}` <= lastDeparture);
    if (activities.length) days.push(`
      <p><time datetime="${key}">${displayDate(key)}</time></p>
      <ol class="agenda">${activities.map(activity => agendaItem(activity, true)).join('')}</ol>`);
    day.setUTCDate(day.getUTCDate() + 7);
  }
  return days.length ? `
    <details class="stay-arrival">
      <summary>Saturday drop-ins</summary>
      ${days.join('')}
      <p>Rainy afternoon? Head to the <a href="./index.html#games-room">Games room</a> for board games.</p>
    </details>` : '';
}

async function loadStays() {
  const result = await fetch('/api/guest/stays/');
  if (!result.ok) throw new Error();
  const data = await result.json();
  csrf = data.csrf;
  const labels = {requested: 'Awaiting confirmation', confirmed: 'Confirmed', checked_in: 'Checked in',
    checked_out: 'Checked out', cancelled: 'Cancelled'};
  stayList.innerHTML = data.stays.length ? data.stays.map(stay =>
    `<article><h3>${escapeText(stay.room)}</h3><strong>${escapeText(labels[stay.status] || stay.status)}</strong>
    <p>${escapeText(stay.checkin)} → ${escapeText(stay.checkout)} · ${stay.guests} guest(s) · ${euros(stay.total_cents)}</p>
    <p>Reference · ${escapeText(stay.reference)}</p>
    ${renderArrivalDetails(stay)}
    ${renderStayGuide(stay)}
    ${renderGrills(stay.grills)}
    ${(stay.walks || []).map(walk => renderWalk(stay, walk)).join('')}
    ${renderSaturdayDropIns(stay)}</article>`).join('') : '<p>Your demo requests will appear here.</p>';
}
function refreshStays() {
  refreshButton.disabled = true;
  return loadStays().catch(() => {
    document.querySelector('#stay-list').textContent = 'Could not load your requests. Try refreshing again.';
  }).finally(() => { refreshButton.disabled = false; });
}
refreshButton.addEventListener('click', refreshStays);
const sessionReady = refreshStays();

stayList.addEventListener('submit', async event => {
  const walkForm = event.target;
  if (!walkForm.matches('.walk-form')) return;
  event.preventDefault();
  const {reference, walk, action, max} = walkForm.dataset;
  const button = walkForm.querySelector('button');
  if (button.disabled) return;
  const feedback = walkForm.querySelector('.walk-feedback');
  const booking = action === 'book';
  let body;
  if (booking) {
    const values = new FormData(walkForm);
    const adults = Number(values.get('adults')), teens = Number(values.get('teens')), children = Number(values.get('children'));
    if (adults + teens + children > Number(max)) {
      feedback.textContent = `Choose at most ${max} participants in total for this walk.`;
      return;
    }
    body = JSON.stringify({adults, teens, children});
  }
  button.disabled = true;
  feedback.textContent = booking ? 'Booking your places…' : 'Cancelling your places…';
  try {
    const result = await fetch(`/api/guest/stays/${encodeURIComponent(reference)}/walks/${walk}/`, {
      method: booking ? 'POST' : 'DELETE',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body,
    });
    const data = await result.json();
    if (!result.ok) {
      feedback.textContent = data.error || 'Could not update your walk booking.';
      return;
    }
    await loadStays();
    message.textContent = booking ? 'Walk booked.' : 'Walk booking cancelled.';
    document.getElementById(`walk-${reference}-${walk}`)?.focus();
  } catch {
    feedback.textContent = 'Could not check the result. Refresh My stay or try again.';
  } finally {
    button.disabled = false;
  }
});

function openTripDetails(button) {
  const offer = offers.find(room => room.id === button.dataset.request);
  if (!offer || sending) return;
  const guests = Number(guestsField.value);
  requestPayload = {category_id: offer.id, nightly_cents: offer.nightly_cents, checkin: checkin.value, checkout: checkout.value, guests};
  document.querySelector('#trip-summary').textContent =
    `${offer.name} · ${displayDate(checkin.value)} to ${displayDate(checkout.value)} · ${guests} ${guests === 1 ? 'guest' : 'guests'} · ${euros(offer.total_cents)}`;
  tripChildren.textContent = '';
  for (let count = 0; count < guests; count++) tripChildren.add(new Option(String(count), String(count)));
  let draft = {};
  try { draft = JSON.parse(sessionStorage.getItem(arrivalDraftKey)) || {}; } catch { /* Storage is optional. */ }
  tripChildren.value = String(Number.isInteger(draft.children) && draft.children < guests ? draft.children : 0);
  tripPet.checked = draft.with_pet === true;
  tripCar.checked = draft.by_car === true;
  tripDialog.showModal();
}

document.querySelector('#trip-close').addEventListener('click', () => tripDialog.close());
tripForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (sending || !requestPayload) return;
  const arrival = {children: Number(tripChildren.value), with_pet: tripPet.checked, by_car: tripCar.checked};
  const payload = {...requestPayload, ...arrival};
  try { sessionStorage.setItem(arrivalDraftKey, JSON.stringify(arrival)); } catch { /* Storage is optional. */ }
  tripDialog.close();
  sending = true;
  updateSendButtons();
  message.textContent = 'Sending your demo request…';
  try {
    await sessionReady;
    if (!csrf) await loadStays();
    const result = await fetch('/api/guest/stays/', {method: 'POST', headers: {'Content-Type': 'application/json',
      'X-CSRFToken': csrf}, body: JSON.stringify(payload)});
    const data = await result.json();
    if (!result.ok) {
      message.textContent = data.error || 'Could not send your request. Recalculate and try again.';
      await calculate();
    } else {
      message.textContent = 'Demo request received · ' + data.reference;
      await refreshStays();
    }
  } catch { message.textContent = 'Delivery uncertain. Refresh My stay or retry the same request.'; }
  finally {
    sending = false;
    updateSendButtons();
    stayTitle.focus();
  }
});

function updateSendButtons() {
  for (const button of cards.querySelectorAll('[data-request]')) button.disabled = sending;
}

function render(rooms, nights, hasAlternatives) {
  if (!rooms.length) {
    const reason = hasAlternatives ? 'No sample stays match these filters.' : 'No sample stays match these dates and guest count.';
    cards.innerHTML = `<div class="empty-state"><p>${reason}</p><div class="empty-actions">
      ${hasAlternatives ? '<button class="secondary-action" type="button" id="broaden">Clear apartment and budget filters</button>' : ''}
      <button class="secondary-action" type="button" id="change-dates">Choose other dates</button>
    </div></div>`;
    return;
  }
  cards.innerHTML = rooms.map(room => `
    <article class="mini-card">
      <div class="mini-card-image" role="img" aria-label="Concept illustration of ${escapeText(room.name)}"${roomImageStyle(room)}></div>
      <div class="mini-card-content">
        <p class="mini-card-top">Up to ${room.guests} guests · ${room.size} m²</p>
        <h3>${escapeText(room.name)}</h3>
        <p>${escapeText(room.sleeping)}</p>
        ${room.outlook ? `<p class="room-outlook">${escapeText(room.outlook)}</p>` : ''}
        ${apartmentDetails(room)}
        <div class="mini-card-price">
          <strong>${euros(room.total_cents)} for ${nights} ${nights === 1 ? 'night' : 'nights'}</strong>
          <span>${euros(room.nightly_cents)} / night</span>
        </div>
        <button class="button button-dark" type="button" data-request="${escapeText(room.id)}" aria-haspopup="dialog" aria-controls="trip-dialog" ${sending ? 'disabled' : ''}>Review request</button>
      </div>
    </article>`).join('');
}

async function calculate() {
  if (submitButton.disabled) return;
  const sequence = ++quoteSequence;
  offers = [];
  cards.textContent = '';
  const start = checkin.value, end = checkout.value;
  if (!start || !end || end <= start || start < checkin.min || start > checkin.max) { summary.textContent = 'Please choose valid dates, with check-out after check-in.'; return; }
  const nights = (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000;
  if (nights > 90) { summary.textContent = 'Please choose a stay of 90 nights or fewer.'; return; }
  const guests = Number(document.querySelector('#guests').value);
  const budgetValue = document.querySelector('#budget').value;
  const budget = budgetValue === 'any' ? Infinity : Number(budgetValue);
  remember();
  summary.textContent = 'Checking your dates…';
  try {
    const params = new URLSearchParams({checkin: start, checkout: end, guests});
    const result = await fetch('/api/guest/quotes/?' + params);
    if (!result.ok) throw new Error();
    const data = await result.json();
    if (sequence !== quoteSequence) return;
    offers = data.rooms.filter(room => (!category.value || room.id === category.value) &&
      room.nightly_cents <= budget * 100).map(room => ({
        ...apartments.find(item => item.id === room.id), ...room}));
    summary.textContent = `${displayDate(start)} – ${displayDate(end)} · ${guests} ${guests === 1 ? 'guest' : 'guests'} · ${offers.length} ${offers.length === 1 ? 'match' : 'matches'}`;
    render(offers, nights, data.rooms.length > 0);
  } catch {
    if (sequence !== quoteSequence) return;
    cards.textContent = '';
    summary.textContent = 'Could not check availability.';
    cards.innerHTML = '<button class="secondary-action" type="button" id="retry-quote">Try availability again</button>';
  }
}
form.addEventListener('change', () => {
  const url = new URL(location.href);
  if (category.value) url.searchParams.set('room', category.value);
  else url.searchParams.delete('room');
  history.replaceState(null, '', url);
  calculate();
});
cards.addEventListener('click', event => {
  if (event.target.dataset.request) { openTripDetails(event.target); return; }
  if (event.target.id === 'change-dates') { calendarTrigger.focus(); calendarTrigger.click(); return; }
  if (event.target.id === 'retry-quote') { resultsTitle.focus(); calculate(); return; }
  if (event.target.id === 'retry-catalog') { resultsTitle.focus(); loadCatalog(); return; }
  if (event.target.id !== 'broaden') return;
  category.value = '';
  budgetField.value = 'any';
  form.dispatchEvent(new Event('change'));
  category.focus();
});
form.addEventListener('submit', event => {
  event.preventDefault();
  resultsTitle.focus();
  return calculate();
});

async function loadCatalog() {
  summary.textContent = 'Loading apartments…';
  cards.textContent = '';
  submitButton.disabled = true;
  try {
    const response = await fetch('../content/en.json');
    if (!response.ok) throw new Error('Content unavailable');
    const content = await response.json();
    apartments = content.apartments;
    for (const room of apartments) category.add(new Option(room.name, room.id));
    restore();
    submitButton.disabled = false;
    calculate();
  } catch {
    summary.textContent = 'Could not load the apartments.';
    cards.innerHTML = '<button class="secondary-action" type="button" id="retry-catalog">Try loading apartments again</button>';
  }
}

loadCatalog();
