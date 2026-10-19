// Money, the way it is written in Indonesia: a period as the thousands
// separator and "Rp" in front.
//
// The raw number is not a price. `90000` reads as ninety thousand, but a
// player looking at what a court costs per hour needs to see that it is
// ninety thousand rupiah and not ninety thousand of something else.

const withThousands = (value) => {
  const [whole, cents] = String(value).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return cents ? `${grouped},${cents}` : grouped
}

export function formatRupiah(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return 'Rp 0'
  return `Rp ${withThousands(Math.abs(amount))}`
}

// The same, without the currency mark, for places that already say "Rp" or
// that put the rate in a table of its own.
export function formatAmount(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '0'
  return withThousands(Math.abs(amount))
}
