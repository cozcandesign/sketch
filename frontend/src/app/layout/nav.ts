import { tr } from '@/i18n/tr'

export const NAV_ITEMS = [
  { to: '/', label: tr.nav.dashboard, key: '1', end: true },
  { to: '/coin', label: tr.nav.coin, key: '2', end: false },
  { to: '/news', label: tr.nav.news, key: '3', end: false },
  { to: '/predictions', label: tr.nav.predictions, key: '4', end: false },
  { to: '/calibration', label: tr.nav.calibration, key: '5', end: false },
  { to: '/settings', label: tr.nav.settings, key: '6', end: false },
  { to: '/costs', label: tr.nav.costs, key: '7', end: false },
] as const
