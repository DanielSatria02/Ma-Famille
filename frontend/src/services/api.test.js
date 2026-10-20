import { describe, expect, it } from 'vitest'

import { errorDetail } from './api.js'

// The manager dashboard showed "The server is not reachable." while the
// server was answering 500 to one endpoint. Two things were wrong with that:
// the message said the server was gone when it was not, and the reference
// that ties the crash to the server log never reached the screen.

describe('errorDetail', () => {
  it('uses the reason the backend gave', () => {
    const error = { response: { status: 422, data: { detail: 'That slot is taken.' } } }
    expect(errorDetail(error)).toBe('That slot is taken.')
  })

  it('says the server could not be reached only when there is no answer', () => {
    const error = { request: {}, message: 'Network Error' }
    expect(errorDetail(error)).toBe('The server is not reachable.')
  })

  it('does not claim the server is gone when it answered with an error', () => {
    const error = { response: { status: 500, data: {} } }
    expect(errorDetail(error, 'Could not load the facilities.')).toBe(
      'Could not load the facilities.',
    )
  })

  it('shows the request id so the crash can be found in the log', () => {
    const error = {
      response: {
        status: 500,
        data: { detail: 'The server ran into a problem.', request_id: 'abc123' },
      },
    }
    expect(errorDetail(error)).toBe('The server ran into a problem. (reference abc123)')
  })

  it('asks for the manager login on a 401', () => {
    const error = { response: { status: 401, data: {} } }
    expect(errorDetail(error)).toBe('Please log in as manager first.')
  })
})
