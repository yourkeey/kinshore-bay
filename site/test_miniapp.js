// Exercise the real browser script against a minimal DOM, without external packages.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const content = JSON.parse(fs.readFileSync(path.join(root, 'content', 'en.json'), 'utf8'));
const elements = {};
for (const id of ['request-message', 'stay-list', 'my-stay-title', 'refresh-stay', 'category', 'finder', 'mini-cards', 'result-count', 'result-summary', 'results-title', 'checkin', 'checkout', 'guests', 'budget', 'calendar-dialog', 'calendar-grid', 'calendar-month', 'calendar-instructions', 'calendar-prev', 'calendar-next', 'open-calendar', 'calendar-close', 'calendar-reset', 'checkin-display', 'checkout-display']) {
  elements[id] = {value: '', textContent: '', innerHTML: '', handlers: {}, addEventListener(name, fn) { this.handlers[name] = fn; }, querySelector() { return null; }, focus() {}, showModal() { this.open = true; }, close() { this.open = false; }};
}
elements.category.add = () => {};
for (const id of ['trip-details', 'trip-close', 'trip-dialog', 'trip-children', 'trip-pet', 'trip-car']) {
  elements[id] = {addEventListener() {}};
}
elements.guests.value = '2';
elements.budget.value = 'any';
const button = {disabled: false};
elements.finder.querySelector = () => button;
const context = {URLSearchParams, location: {search: ''}, Option: function() {}, document: {querySelector: selector => elements[selector.slice(1)]}, fetch: async url => ({ok: true, json: async () => {
  if (url.includes('/stays/')) return {stays: [], csrf: 'test'};
  if (!url.includes('/quotes/')) return content;
  const p = new URLSearchParams(url.split('?')[1]);
  const nights = (Date.parse(p.get('checkout')) - Date.parse(p.get('checkin'))) / 86400000;
  return {rooms: content.apartments.filter(a => a.guests >= Number(p.get('guests'))).map(a =>
    ({...a, nightly_cents: a.price * 100, total_cents: nights * a.price * 100}))};
}}), Date, Number, String, Infinity};
vm.createContext(context);
for (const file of ['apartment-details.js', 'club-guide.js', 'miniapp.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
}

setImmediate(async () => {
  try {
    assert.equal(button.disabled, false);
    assert.match(elements['mini-cards'].innerHTML, /Garden Studio/);
    assert.match(elements['mini-cards'].innerHTML, /garden-studio-warm\.webp/);
    const today = new Date();
    const localISO = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const start = new Date(today.getFullYear(), today.getMonth() + 2, 10);
    const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 4);
    elements.checkin.value = localISO(start);
    elements.checkout.value = localISO(end);
    elements.guests.value = '4';
    elements.budget.value = '160';
    await elements.finder.handlers.submit({preventDefault() {}});
    assert.match(elements['mini-cards'].innerHTML, /Poolside One Bedroom/);
    assert.match(elements['mini-cards'].innerHTML, /€540 for 4 nights/);
    assert.doesNotMatch(elements['mini-cards'].innerHTML, /Family Two Bedroom/);
    elements.guests.value = '6';
    elements.budget.value = '120';
    await elements.finder.handlers.submit({preventDefault() {}});
    assert.match(elements['mini-cards'].innerHTML, /No sample stays match/);
    elements.checkout.value = elements.checkin.value;
    await elements.finder.handlers.submit({preventDefault() {}});
    assert.match(elements['result-summary'].textContent, /valid dates/);
    elements.checkout.value = localISO(end);
    elements['open-calendar'].handlers.click();
    assert.equal(elements['calendar-dialog'].open, true);
    assert.match(elements['calendar-grid'].innerHTML, /data-date=/);
    const clickDay = date => elements['calendar-grid'].handlers.click({target: {closest: () => ({disabled: false, dataset: {date}})}});
    clickDay(localISO(start));
    assert.match(elements['calendar-instructions'].textContent, /select check-out/);
    clickDay(localISO(end));
    assert.equal(elements['calendar-dialog'].open, false);
    assert.equal(elements.checkin.value, localISO(start));
    assert.equal(elements.checkout.value, localISO(end));
    assert.notEqual(elements['checkin-display'].textContent, 'Select date');
    console.log('Mini app: calendar, filtering, totals, empty state and date validation OK');
  } catch (error) { console.error(error); process.exitCode = 1; }
});
