// Where to send someone who wants to get to the venue.
//
// Google is not embedded anywhere in this app: the map is drawn from
// OpenStreetMap, which costs nothing and needs no key, and the navigation is
// handed to whichever app the visitor already has on their phone. That link is
// the whole of the Google dependency here — a URL, no script, no key, nothing
// to load and nothing to consent to.

// True when there is somewhere to put a pin. A venue can be in the database
// without coordinates, and a map asked to draw one shows an empty grey box.
export function hasCoordinates(venue) {
  return Number.isFinite(venue?.lat) && Number.isFinite(venue?.lng)
}

// The /maps/search/ form with api=1 is the documented way to link out of a web
// page into the app: on a phone it opens the installed app, on a desktop it
// opens the site, and the same link works for both.
//
// Coordinates come first. The address on the venue record is typed by whoever
// set the venue up, and a street name is not a place: "Jl. Demo No. 1" resolves
// against whatever Google's geocoder thinks that string means, which can be a
// different street, a different number, or a different city. The pin on our own
// map is drawn from lat/lng, so sending the navigation app somewhere the pin
// does not agree with would be sending them to the wrong building.
//
// The address is only used for a venue with no coordinates at all, where a name
// is still better than a dead link.
export function directionsUrl(venue = {}) {
  if (hasCoordinates(venue)) {
    return `https://www.google.com/maps/search/?api=1&query=${coordinates(venue.lat, venue.lng)}`
  }
  const query = String(venue.address || venue.name || '').trim()
  if (!query) return null
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`
}

// Six decimals is about 10cm, which is finer than any door on a street. Five is
// a metre and is what a phone's own location gives you, so anything past that
// is noise pretending to be precision.
export function coordinates(lat, lng) {
  return `${Number(lat).toFixed(6)},${Number(lng).toFixed(6)}`
}

// A link to the place on openstreetmap.org itself, for the attribution and for
// anyone who wants the data rather than the photograph.
export function osmLink({ osmId, lat, lng } = {}) {
  if (osmId) return `https://www.openstreetmap.org/${osmId}`
  if (hasCoordinates({ lat, lng })) {
    return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`
  }
  return null
}