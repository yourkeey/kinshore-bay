const escapeText = value => String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));

function apartmentDetails(room) {
  const plan = room.layout || [];
  if (!plan.length) return '';
  const style = ['studio', 'one', 'family'].includes(room.id) ? ` floor-plan-${room.id}` : '';
  return `
    <details class="room-plan">
      <summary>Floor plan &amp; kitchen</summary>
      <figure>
        <dl class="floor-plan${style}">${plan.map(([space, feature]) =>
          `<div><dt>${escapeText(space)}</dt><dd>${escapeText(feature)}</dd></div>`).join('')}</dl>
        <figcaption>Illustrative layout · Approximate room positions</figcaption>
      </figure>
      ${room.kitchen ? `<p class="room-kitchen"><strong>Kitchen equipment</strong> ${escapeText(room.kitchen)}</p>` : ''}
    </details>`;
}
