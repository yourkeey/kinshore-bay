const arrivalHours = {checkin: '15:00', checkout: '11:00'};
const poolHours = '09:00–19:00';
const inclusions = 'Linen, final cleaning, guest parking, access to both pools and a pool towel from Reception.';

const morningStretch = {title: 'Morning stretch', start: '08:30', end: '09:00', place: '9',
  detail: 'Bring a towel or mat. Drop in, weather permitting.'};
const shoreWalk = {title: 'Pine & Shore Walk', start: '10:00', end: '10:45', meeting: '09:50', place: '9',
  detail: 'Ages 6+. Guests with a confirmed stay can book in My stay.'};
const familyGames = {title: 'Family court games', start: '15:30', end: '16:15', place: '12',
  detail: 'Drop in with your family. Children take part with a grown-up.'};
const saturday = [morningStretch, shoreWalk, familyGames];

const placeGroups = [
  {id: 'arrival', label: 'Arrival & parking', places: [
    {key: '1', name: 'Arrival gate', x: 9.3, y: 53.8,
      directions: 'Enter from the access road on the west side. Follow the driveway to the parking areas, then walk to Reception.',
      link: ['#reception', 'Find reception']},
    {key: '2', name: 'Covered parking', x: 11.6, y: 23,
      directions: 'Bear left after the arrival gate to reach the timber-roof carport. Use the open guest lot if the covered area is full.',
      note: 'Covered bays are first come, first served.', link: ['#guest-parking', 'Find open parking']},
    {key: '3', name: 'Guest parking', x: 11.1, y: 76,
      directions: 'The open-air lot is on the lower branch of the entrance drive. Follow the paved footpath towards Reception.',
      link: ['#reception', 'Find reception']},
    {key: '4', name: 'Reception', x: 20.5, y: 49, overview: true,
      directions: 'Collect your keys at the pavilion at the start of Garden path. Have your stay reference handy.',
      note: `Check-in from ${arrivalHours.checkin} · Check-out by ${arrivalHours.checkout}`, link: ['./miniapp.html#my-stay', 'Open My stay']},
  ]},
  {id: 'apartments', label: 'Apartments', places: [
    {key: 'A', name: 'Building A', x: 24.5, y: 71, directions: 'Building A is beside Reception, at the entrance end of Garden path.'},
    {key: 'B', name: 'Building B', x: 39.7, y: 73, directions: 'Follow Garden path from Reception. Building B is on the Main pool side, before Pine terrace.'},
    {key: 'C', name: 'Building C', x: 37.2, y: 32, directions: 'Follow Garden path from Reception. Building C is on the Garden pool side, before Pine terrace.'},
    {key: 'D', name: 'Building D', x: 64.9, y: 31.5, directions: 'Continue beyond Pine terrace towards Beach gate. Building D is on the Garden pool side.'},
    {key: 'E', name: 'Building E', x: 68.6, y: 71, directions: 'Continue beyond Pine terrace towards Beach gate. Building E is on the Main pool side.'},
  ]},
  {id: 'food', label: 'Eat & shop', places: [
    {key: '5', name: 'Terrace café', id: 'terrace-cafe', x: 49.3, y: 13.1, overview: true,
      directions: 'Coffee, pastries and light lunch at the terrace in the upper gardens.',
      note: '08:00–16:00'},
    {key: '6', name: 'Bay Kitchen', x: 78.5, y: 28.1,
      directions: 'The dining terrace behind the dunes serves dinner. Ask at Reception about a table.',
      note: '18:00–21:00', link: ['#reception', 'Find reception']},
    {key: '7', name: 'Club shop', x: 60.1, y: 12.8,
      directions: 'The small shop beside Terrace café carries snacks, water and a few self-catering essentials.',
      note: '08:00–19:00'},
    {key: '8', name: 'Beach kiosk', x: 89.9, y: 40.5,
      directions: 'Find drinks and ice cream at the kiosk on the sand, just past Beach gate.',
      note: '11:00–17:00 · Weather permitting'},
    {key: '19', name: 'Grill pergolas', x: 73.5, y: 16.3,
      directions: 'Two covered tables sit off the upper garden path, just before Bay Kitchen. Bring your own food and ask Reception for a grill slot.',
      note: '17:00–21:00 · Weather permitting · Use the club grills', link: ['#reception', 'Ask at Reception']},
  ]},
  {id: 'family', label: 'Family & sport', places: [
    {key: '9', name: 'Pine terrace', x: 51.6, y: 54, overview: true,
      directions: 'Follow Garden path from Reception to the terrace between the pools. Meet here for Pine & Shore Walk.',
      note: `Saturday · Stretch at ${morningStretch.start} · Walk meets at ${shoreWalk.meeting}`, link: ['#saturday', 'See the Saturday programme']},
    {key: '10', name: 'Play garden', x: 24.2, y: 35.6, overview: true,
      directions: 'Follow the upper path from Reception to the play structures beside the sports court.',
      note: 'Children stay with their accompanying adult.'},
    {key: '11', name: 'Games room', x: 34.9, y: 12.2,
      directions: 'The clubhouse next to the court has board games and a table for a rainy afternoon.',
      note: '10:00–20:00'},
    {key: '12', name: 'Sports court', x: 24.4, y: 19.4,
      directions: 'The multi-use court is between the carport and the play garden. Ask Reception about equipment.',
      note: `09:00–20:00 · Saturday family games at ${familyGames.start}`, link: ['#saturday', 'See the Saturday programme']},
    {key: '13', name: 'Garden pergola', x: 78.3, y: 44.7,
      directions: 'Take a break in the shade beside the path to Beach gate, below Bay Kitchen.'},
  ]},
  {id: 'water', label: 'Pools & beach', places: [
    {key: '14', name: 'Garden pool', x: 51.5, y: 38.5,
      directions: 'The family pool sits between Buildings C and D. Look for the shallow area and shaded seats. Children stay with their accompanying adult.',
      note: `${poolHours} · Pool towels at Reception`, link: ['#reception', 'Find Reception for towels']},
    {key: '15', name: 'Main pool', x: 52.9, y: 69.7,
      directions: 'The larger pool has room for swimming lengths. Follow the path from Pine terrace between Buildings B and E. Shaded loungers are at the far end.',
      note: `${poolHours} · Pool towels at Reception`, overview: true, link: ['#pool-pergolas', 'Find shaded loungers']},
    {key: '16', name: 'Pool pergolas', x: 53.2, y: 85,
      directions: 'The shaded loungers are at the far end of Main pool.',
      note: 'First come, first served.'},
    {key: '17', name: 'Beach gate', x: 85.3, y: 54, overview: true,
      directions: 'Continue straight from Pine terrace along Garden path. The timber gate marks the way onto the sand.',
      link: ['#beach-loungers', 'Find beach loungers']},
    {key: '18', name: 'Beach loungers', x: 91.2, y: 68.4,
      directions: 'From Beach gate, turn right along the sand for loungers and parasols.',
      note: 'Availability depends on weather.', link: ['#beach-kiosk', 'Find the beach kiosk']},
  ]},
];
const places = placeGroups.flatMap(group => group.places.map(place => ({...place, group: group.id})));
const placeId = place => place.id || place.name.toLowerCase().replaceAll(' ', '-');

function agendaItem(activity, fromPlanner = false) {
  const place = places.find(place => place.key === activity.place);
  const mapPage = fromPlanner ? './index.html' : '';
  return `
    <li>
      <span class="agenda-time"><time datetime="${activity.start}">${activity.start}</time>–<time datetime="${activity.end}">${activity.end}</time></span>
      <strong>${escapeText(activity.title)}</strong>
      <a href="${mapPage}#${placeId(place)}">${escapeText(place.name)}</a>
      <p>${activity.meeting ? `Meet at ${activity.meeting}. ` : ''}${escapeText(activity.detail)}</p>
      ${activity.meeting ? '<a href="./miniapp.html#my-stay">Open My stay</a>' : ''}
    </li>`;
}
