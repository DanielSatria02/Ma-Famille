import { describe, expect, it } from 'vitest'

import { coordinates, directionsUrl, hasCoordinates, osmLink } from './maps.js'

describe('hasCoordinates', () => {
  it('needs both halves', () => {
    expect(hasCoordinates({ lat: -6.2615, lng: 106.8106 })).toBe(true)
    expect(hasCoordinates({ lat: -6.2615 })).toBe(false)
    expect(hasCoordinates({ lng: 106.8106 })).toBe(false)
  })

  // The column is nullable, so the API sends null rather than leaving it out.
  it('rejects nulls and non-numbers', () => {
    expect(hasCoordinates({ lat: null, lng: null })).toBe(false)
    expect(hasCoordinates({ lat: 'abc', lng: 'def' })).toBe(false)
    expect(hasCoordinates(null)).toBe(false)
  })

  // Zero is a real coordinate: the Gulf of Guinea, not the missing value.
  it('accepts zero', () => {
    expect(hasCoordinates({ lat: 0, lng: 0 })).toBe(true)
  })
})

describe('directionsUrl', () => {
  const jakarta = { lat: -6.2615, lng: 106.8106, name: 'Agora Padel', address: 'Jalan Kota Bumi' }

  // The pin on our own map comes from these two numbers. Handing the navigation
  // app a street name instead can drop someone at a different number, or a
  // different street entirely, while our map shows one place and theirs shows
  // another.
  it('uses the coordinates when the venue has them', () => {
    expect(directionsUrl(jakarta)).toBe(
      'https://www.google.com/maps/search/?api=1&query=-6.261500,106.810600',
    )
  })

  it('ignores the address when there are coordinates', () => {
    expect(directionsUrl(jakarta)).not.toContain('Jl.')
    expect(directionsUrl(jakarta)).not.toContain('Demo')
  })

  it('rounds to six decimals and keeps the sign', () => {
    expect(directionsUrl({ lat: -6.26151234, lng: 106.81059876 })).toContain(
      '-6.261512,106.810599',
    )
  })

  it('uses the api=1 form so a phone opens the app and a desktop opens the site', () => {
    expect(directionsUrl(jakarta)).toContain('/maps/search/?api=1&query=')
  })

  // A venue with no pin yet is better served by its name than by no link.
  it('falls back to the address, then the name, with no coordinates', () => {
    expect(directionsUrl({ address: 'Jl. Demo No. 1', name: 'GOR' })).toContain('Jl.%20Demo%20No.%201')
    expect(directionsUrl({ name: 'GOR Senayan' })).toContain('GOR%20Senayan')
  })

  // Half a pair is not a place. Falling through to the name here would send
  // someone to a street search when the record plainly meant to have a pin.
  it('does not use one coordinate on its own', () => {
    expect(directionsUrl({ lat: -6.2615, name: 'GOR Senayan' })).toContain('GOR%20Senayan')
    expect(directionsUrl({ lng: 106.8106, name: 'GOR Senayan' })).toContain('GOR%20Senayan')
  })

  // An unencoded "&" starts a second query parameter, so a search that ends up
  // on Google's own page instead of on the venue.
  it('escapes characters that would break the query string', () => {
    expect(directionsUrl({ address: 'Jl. A & B, Lt. 3' })).toBe(
      'https://www.google.com/maps/search/?api=1&query=Jl.%20A%20%26%20B%2C%20Lt.%203',
    )
  })

  it('returns nothing for a venue with no address and no name', () => {
    expect(directionsUrl({})).toBeNull()
    expect(directionsUrl()).toBeNull()
    expect(directionsUrl({ address: '   ' })).toBeNull()
  })
})

describe('coordinates', () => {
  it('keeps six decimals and no more', () => {
    expect(coordinates(-6.2615, 106.8106)).toBe('-6.261500,106.810600')
    expect(coordinates(0, 0)).toBe('0.000000,0.000000')
  })
})

describe('osmLink', () => {
  it('uses the relation or way id when the venue has one', () => {
    expect(osmLink({ osmId: 'way/12345' })).toBe('https://www.openstreetmap.org/way/12345')
  })

  it('falls back to a coordinate link', () => {
    expect(osmLink({ lat: -6.2615, lng: 106.8106 })).toBe(
      'https://www.openstreetmap.org/?mlat=-6.2615&mlon=106.8106#map=17/-6.2615/106.8106',
    )
  })

  it('returns nothing without a complete pair', () => {
    expect(osmLink({})).toBeNull()
    expect(osmLink({ lat: null, lng: null })).toBeNull()
    expect(osmLink({ lat: -6.2615 })).toBeNull()
  })
})