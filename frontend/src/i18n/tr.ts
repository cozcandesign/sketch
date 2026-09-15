// Tüm arayüz metinleri burada. JSX içinde çıplak Türkçe string yok (CLAUDE.md §7).
// Bu dosya yasak kelime testinden geçer (backend/tests/unit/test_banned_words.py).
export const tr = {
  app: {
    name: 'MarketPulse',
    tagline: 'Yön olasılığı ve piyasa durumu. İşlem yapmaz.',
  },
  nav: {
    dashboard: 'Panel',
    coin: 'Coin detay',
    news: 'Haber akışı',
    predictions: 'Tahmin geçmişi',
    calibration: 'Kalibrasyon',
    settings: 'Ayarlar',
    costs: 'Maliyet',
  },
  status: {
    connected: 'bağlı',
    connecting: 'bağlanıyor',
    disconnected: 'kopuk',
    engineAlive: 'engine çalışıyor',
    engineStale: 'engine yanıt vermiyor',
    engineUnknown: 'engine durumu bilinmiyor',
    lastUpdate: 'son güncelleme',
    never: 'hiç',
    noCollectors: 'Henüz collector yok (Faz 1 ile gelir).',
    health: {
      ok: 'çalışıyor',
      degraded: 'aksıyor',
      down: 'kopuk',
      disabled: 'kapalı',
      budget_exhausted: 'bütçe doldu',
    },
  },
  placeholder: {
    phase: 'Bu ekran Faz {phase} ile dolacak.',
  },
  common: {
    loading: 'yükleniyor…',
    error: 'hata',
    retry: 'yeniden dene',
    version: 'sürüm',
  },
} as const

export type Tr = typeof tr
