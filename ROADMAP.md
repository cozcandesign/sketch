# ROADMAP.md — MarketPulse

Fazlar sıralıdır; bir faz "Bitti sayılır" maddelerinin tamamı sağlanmadan sonraki faza geçilmez.
Görev kimlikleri `F<faz>-<no>` commit gövdesinde `Refs:` ile anılır. Biten görev `[x]` yapılır.
Faz içine ROADMAP'te olmayan iş eklenmez; gerekiyorsa önce buraya görev olarak yazılır.

**Sıra neden böyle:** Kullanıcı gereksinimi doğruluk takibinin tahmin motorundan önce gelmesi. Bu yüzden
Faz 1 veri omurgası + tahmin defteri + metriklerdir; gerçek sinyal modülleri Faz 2'den itibaren gelir ve
üretilen her tahmin ilk günden ölçülür. İleriye dönük veri (OI, likidasyon, haber) ancak sistem çalışırken
birikir; bu yüzden collector'lar erken fazlarda ayağa kalkar.

Tahmini oturum sayıları kabaca bir Claude Code oturumu = birkaç saatlik odaklı iş varsayımıyla verilmiştir.

---

## Faz 0 — İskelet (1–2 oturum)

**Amaç:** Boş ama çalışan monorepo. `make check` yeşil, `docker compose up` üç servisi ayağa kaldırıyor,
arayüz "bağlı" diyor.

Görevler
- [ ] F0-1 `backend/pyproject.toml` (uv, Python 3.12), bağımlılıklar: fastapi, uvicorn, pydantic v2,
      pydantic-settings, sqlalchemy 2, aiosqlite, alembic, httpx, websockets, pandas, numpy, loguru,
      anthropic, feedparser, yfinance, pyyaml. Dev: pytest, pytest-asyncio, respx, hypothesis, time-machine,
      ruff, mypy, pandas-stubs, honcho, pre-commit.
- [ ] F0-2 `ruff`, `mypy --strict`, `pytest` yapılandırması; `signals → storage` import yasağı (ruff banned-api).
- [ ] F0-3 `config.py` (pydantic-settings, `MP_` ön eki), `.env.example`, `core/` (Horizon, Symbol, Clock,
      FakeClock, utc_now, floor_to_minute, hata sınıfları) + testleri.
- [ ] F0-4 `storage/`: engine (WAL, busy_timeout), `tables.py` (tüm §6 tabloları), Alembic ilk migration,
      `Repository` protokolü ve `SqliteRepository` iskeleti, `Outbox` yazıcı/okuyucu + testleri.
- [ ] F0-5 `scheduler/main.py`: supervisor, heartbeat işi, `SIGTERM` ile temiz kapanış, çift örnek koruması.
- [ ] F0-6 `api/app.py`: FastAPI, CORS, `/api/v1/health`, `/ws` (subscribe/ping/pong), outbox relay görevi.
- [ ] F0-7 Frontend iskeleti: Vite + React + TS strict + Tailwind, `tokens.css` koyu tema, `Shell`
      (Sidebar/Topbar/StatusBar), 6 boş rota, `WsClient`, `i18n/tr.ts`, eslint/prettier/vitest.
- [ ] F0-8 `make gen-types` (openapi-typescript) ve ilk `types.gen.ts`.
- [ ] F0-9 `Makefile` (tüm hedefler), `Procfile.dev`, `docker-compose.yml`, iki Dockerfile, `nginx.conf`,
      `.gitignore`, `.dockerignore`, `pre-commit` (ruff, mypy, eslint).
- [ ] F0-10 `reporting/banned_words.py` + `templates.py` ve `i18n/tr.ts`'i tarayan test (liste boşken de
      koşar).

Bitti sayılır
- `make check` yeşil (backend + frontend).
- `make dev` üç süreci başlatır; arayüz StatusBar'da WS "bağlı" ve scheduler heartbeat'ini gösterir.
- `make up` ile aynı sonuç Docker'da; `http://localhost:3000` açılır.
- `.env` olmadan uygulama anlaşılır hata ile durur (hangi anahtar eksik).

---

## Faz 1 — Veri omurgası + tahmin defteri + doğruluk takibi (3–4 oturum)

**Amaç:** Mumlar akıyor, tahmin defteri ve resolver çalışıyor, metrikler hesaplanıyor. Gerçek motor henüz
yok; baseline tahminler defteri uçtan uca kullanıyor. Arayüzde fiyat kartları, tahmin geçmişi ve ilk
kalibrasyon grafiği var.

Görevler
- [ ] F1-1 `scheduler/ratelimit.py`: `exchangeInfo`'dan limit okuma, token bucket, `X-MBX-USED-WEIGHT-1M`
      senkronu, 429/418 davranışı + testleri (respx).
- [ ] F1-2 Binance HTTP istemcisi (httpx, retry/backoff, zaman damgası normalizasyonu) + testleri.
- [ ] F1-3 `collectors/spot_klines`: REST backfill (1m/5m/15m/1h/4h/1d, sayfalama), boşluk denetimi,
      yalnızca kapanmış mum yazma, idempotent upsert + testleri (kaydedilmiş yanıt fixture'ları).
- [ ] F1-4 `collectors/binance_ws` altyapısı: combined stream, yeniden bağlanma, 23. saat planlı yenileme,
      `kline_1m` işleyicisi (`x=true` filtresi) + sahte akış testleri.
- [ ] F1-5 `scheduler/jobs.py`: duvar saatine hizalı `Job`, `predict_*` tetikleri (+10 sn), `resolve`,
      `gap_check`, `retention`, `health_heartbeat`; `FakeClock` ile testler (tetik anları, kaçırılan tetik
      davranışı).
- [ ] F1-6 `tracking/ledger.py`: tahmin + modül skorları tek transaction; `non_overlapping` bayrağı; `source`
      ve `run_id` + testleri.
- [ ] F1-7 `tracking/resolver.py`: 1m mum ile çözümleme, REST backfill yolu, 24 saat sonra `unresolved`,
      `hit`/`brier`/`realized_return` + testleri (sınır: eşitlik, eksik mum, geç gelen mum).
- [ ] F1-8 `tracking/metrics.py`: Brier, BSS, kalibrasyon kovaları, isabet + Wilson CI, alt kümeler
      (all / non_overlapping / high_confidence), günlük seri; elle hesaplanmış örneklerle testler.
- [ ] F1-9 Baseline tahminciler (`climatology`, `momentum`), `predict_*` işlerine bağlanması
      (`source='baseline'`) + testleri.
- [ ] F1-10 `tests/lookahead/test_resolver_boundary` ve `test_truncation_invariance` (candles için; diğer veri
      setleri kendi fazında eklenir).
- [ ] F1-11 API: `GET /predictions`, `/predictions/{id}`, `/market/{symbol}` (fiyat + 24s Δ + baseline
      tahminler), `/market/{symbol}/candles`, `/calibration` (Brier serisi, kovalar, isabet), `/health`;
      `api/live_relay.py` (miniTicker → `price.*`); outbox `prediction.created`, `outcome.resolved`,
      `health.changed`.
- [ ] F1-12 Frontend: Dashboard (CoinCard: canlı fiyat + baseline olasılık placeholder'ı + DataHealthDot),
      Tahmin geçmişi tablosu (filtre + cursor sayfalama + Drawer), Kalibrasyon ekranının Brier serisi ve
      kalibrasyon eğrisi (baseline verisiyle), StatusBar sağlık özeti.
- [ ] F1-13 `make backfill` CLI (klines; ileride diğer setler eklenir).
- [ ] F1-14 Retention işi (candles 1m 90 gün, outbox 24 saat) + testi.

Bitti sayılır
- 3 sembol için 1m..1d mumlar canlı akıyor; WS kesilince boşluk 5 dk içinde REST ile dolmuş oluyor (test ve
  gerçek ortamda gözlem).
- Baseline tahminler dört ufukta üretiliyor, ufuk dolunca çözümleniyor; kalibrasyon ekranında Brier serisi
  ve kalibrasyon eğrisi doluyor.
- Look-ahead testleri (`resolver_boundary`, `truncation_invariance`) yeşil.
- Sistem 24 saat kesintisiz çalışmış, hiçbir supervisor sürekli yeniden başlamıyor (health tablosu temiz).

---

## Faz 2 — Teknik modül + Ensemble v0 + rapor (3 oturum)

**Amaç:** İlk gerçek sinyal modülü. Tahminler artık `source='live'` ile üretiliyor ve ölçülüyor. Coin
detay ekranı mum grafiği ve modül kırılımıyla açılıyor.

Görevler
- [ ] F2-1 `features/indicators.py`: EMA, SMA, RSI, MACD, ATR, Bollinger, ADX, swing high/low, volume profile
      (POC, değer alanı); her biri referans değer testi; `hypothesis` nedensellik testi (gelecek perturbasyonu).
- [ ] F2-2 `features/feature_store.py`: `FeatureSnapshot`, candles için kesme kuralı, geriye bakış pencereleri,
      `coverage` hesabı + testleri; `test_truncation_invariance` tüm candles interval'larına genişletilir.
- [ ] F2-3 `signals/base.py` (`SignalResult`, `SignalModule`, ufuk→TF eşlemesi) ve `signals/technical.py`
      (trend, momentum, volume, sr, vol_regime) + unit testleri (işaret, aralık, eksik veri, yasak kelime).
- [ ] F2-4 `ensemble/`: `combine.py` (ağırlıklı log-odds, `k_h`, K19 kırpma), `confidence.py`,
      `conflict.py`, `expected_range.py`; `weights.default.yaml` yükleyici; `weights` tablosu tohumu + testleri.
      Bu fazda yalnızca technical modülü aktif; diğerleri `coverage=0`.
- [ ] F2-5 `reporting/`: `templates.py` (teknik modül şablonları), `counter_argument.py`, `build_report()`
      + testleri; yasak kelime testi şablonları tarar.
- [ ] F2-6 `predict_*` işleri gerçek akışa geçer (snapshot → modüller → ensemble → rapor → ledger);
      modül istisnasında "veri yok" davranışı testi.
- [ ] F2-7 `tests/lookahead/test_future_perturbation` (technical için) ve `test_backtest_equivalence`
      iskeleti (motor Faz 7'de; şimdilik aynı fonksiyonun iki çağrısı).
- [ ] F2-8 API: `GET /signals/{symbol}`, `/market/{symbol}/levels`; `/market/{symbol}` canlı tahmin özetleri;
      outbox `signals.updated`.
- [ ] F2-9 Frontend: Coin detay ekranı — `CandleChart` (lightweight-charts; interval seçici; EMA/S-R/POC
      overlay toggle; tahmin işaretçileri sonuç rengiyle), ufuk sekmeleri, `ModuleBreakdown` +
      `RationaleList`, `ReportCard` (headline, gerekçe, karşıt argüman, beklenen aralık). Dashboard kartları
      gerçek olasılık + `ConfidenceBadge` + çelişki/veto rozetleri.
- [ ] F2-10 Kalibrasyon ekranına modül tablosu (şimdilik tek modül) ve baseline karşılaştırma çizgileri.

Bitti sayılır
- Dört ufukta canlı tahminler üretiliyor; her tahminin `prediction_signals` satırı, raporu ve karşıt
  argümanı var.
- Teknik modül unit testleri, gösterge referans testleri ve look-ahead testleri yeşil.
- Coin detay ekranında mum grafiği, işaretçiler ve modül kırılımı çalışıyor; sayfa yenilemeden yeni tahmin
  düşüyor.

---

## Faz 3 — Order flow (3 oturum)

**Amaç:** Funding, OI, L/S, taker, likidasyon, order book, CVD toplanıyor ve order flow modülü çalışıyor.
Kendi arşivimiz birikmeye başlıyor.

Görevler
- [ ] F3-1 `collectors/funding` (geçmiş + anlık), `open_interest` (hist + live), `long_short`, `taker_volume`
      + testleri; `make backfill`'e funding ve 30 günlük OI/LS/taker eklenir.
- [ ] F3-2 `collectors/binance_ws` futures akışları: `aggTrade`, `forceOrder`, `depth20@100ms`; 1 dk kova
      toplayıcı (`orderflow_1m`), `coverage_seconds`, `liquidations` ham kayıt; kapanışta flush + testleri.
- [ ] F3-3 `collectors/depth_snapshot` (REST 500 seviye, ±%1 derinlik) + testi.
- [ ] F3-4 `FeatureStore`: funding, OI, LS, taker, orderflow_1m, liquidations veri setleri; kesme ve kapsama
      + `truncation_invariance` genişletme.
- [ ] F3-5 `signals/orderflow.py`: funding_dev, oi_price (4 durum), liquidations, book_imbalance, cvd +
      unit testleri (her durum için sentetik seri) + `future_perturbation`.
- [ ] F3-6 Şablonlar: order flow gerekçeleri; ensemble'da orderflow aktif.
- [ ] F3-7 API: `GET /market/{symbol}/orderflow`; `/market/{symbol}` içine funding/OI/LS özetleri.
- [ ] F3-8 Frontend: Coin detay alt panelleri — `FundingPanel`, `OIPanel` (OI + fiyat, durum etiketi),
      `LiquidationPanel`, `OrderBookPanel`, `CVDPanel`; `ModuleBreakdown`'da orderflow bileşenleri.
- [ ] F3-9 Retention: orderflow_1m ve liquidations 90 gün.

Bitti sayılır
- WS akışları 24 saat kesintisiz; `coverage_seconds` ortalaması > 3500/3600.
- Order flow modülü tahminlere katılıyor; kalibrasyon ekranı modül tablosunda ayrı satırı var.
- Bir WS kesintisi simülasyonunda modül `coverage` düşürüyor, tahmin yine üretiliyor, güven düşüyor (test).

---

## Faz 4 — Haber + LLM + veto (3 oturum)

**Amaç:** RSS akışı toplanıyor, tekrarlar birleştiriliyor, Claude ile sınıflandırılıyor, haber modülü ve
veto çalışıyor, haber ekranı açık.

Görevler
- [ ] F4-1 `collectors/rss` (4 kaynak, koşullu istek, `published_at` normalizasyonu) + testleri (kaydedilmiş
      feed fixture'ları). `collectors/cryptopanic` (token varsa) + testi.
- [ ] F4-2 `llm/dedup.py`: URL kanonikleştirme, başlık token Jaccard, grup başı seçimi + testleri.
- [ ] F4-3 `llm/client.py` (`AsyncAnthropic`, `messages.parse`, sistem promptu + `cache_control`, hata
      sınıfları ayrımı), `llm/news_classifier.py` (parti, şema, `<item>` sarma, talimat yok sayma cümlesi),
      `llm/budget.py` (`llm_usage`, günlük tavan) + testleri (SDK çağrısı mock'lanır; gerçek API'ye çıkan
      test yok).
- [ ] F4-4 `collectors/news_classifier` işi (yeni haber → parti → sınıflandırma; miras kopyalama; bütçe
      aşımında durma; `budget_exhausted` health) + testleri.
- [ ] F4-5 `FeatureStore`: news veri seti (`published_at + gecikme` kesmesi) + `truncation_invariance`.
- [ ] F4-6 `signals/news.py`: decay, ilgi, kategori bileşenleri, veto bayrağı + unit testleri
      (yarı ömür, tekrar sayılmaması, veto eşiği) + `future_perturbation`.
- [ ] F4-7 `ensemble/veto.py`: haber vetosu davranışı (ağırlık ezme, `p_up` harmanı, güven `low`, rapor
      başlığı) + testleri.
- [ ] F4-8 Şablonlar: haber gerekçeleri ve veto metinleri; yasak kelime testi güncel.
- [ ] F4-9 API: `GET /news` (filtreler, cursor); outbox `news.classified`; `/config` içinde LLM durumu.
- [ ] F4-10 Frontend: Haber akışı ekranı (`NewsFilters`, `NewsCard`, `ImpactBadge`, grup boyutu, kategori
      dağılımı); Coin detay ve Dashboard'da veto rozeti; `ModuleBreakdown`'da haber maddeleri.
- [ ] F4-11 Retention: news 180 gün. `weights` tablosu: news aktif.

Bitti sayılır
- Bir günlük gerçek akışta tekrar oranı ve sınıflandırma maliyeti loglanmış; günlük maliyet tavanın altında.
- Sınıflandırma çıktısı her zaman şemaya uyuyor (parse hatası sıfır); bütçe aşımı simülasyonunda modül
  "veri yok" diyor ve sistem devam ediyor.
- Veto senaryosu testi: sentetik "çok negatif, güven 0.9" haberi teknik yukarı sinyalini eziyor ve rapor
  başında uyarı var.

---

## Faz 5 — Makro + Sentiment + takvim + tam ensemble (2 oturum)

**Amaç:** Beş modül de aktif. Çelişki tespiti ve takvim vetosu çalışıyor.

Görevler
- [ ] F5-1 `collectors/macro` (yfinance, `to_thread`, `available_at` kuralı, hata → degraded) + testleri
      (yfinance mock).
- [ ] F5-2 `collectors/fear_greed` (`available_at = 00:10 UTC`) + testi.
- [ ] F5-3 `backend/config/calendar.yaml` (bu yıl ve gelecek yılın FOMC, CPI, NFP tarihleri; kaynak: Fed
      ve BLS yayın takvimleri) ve `collectors/calendar` (yükleme, dosya değişimi, eski tarih uyarısı) + testi.
- [ ] F5-4 `FeatureStore`: fear_greed, macro, calendar veri setleri + `truncation_invariance`
      (F&G ve makro `available_at` sınırları özellikle test edilir).
- [ ] F5-5 `signals/macro.py` (dxy, risk_regime, gold, calendar; korelasyon ağırlığı; takvim vetosu) + testleri.
- [ ] F5-6 `signals/sentiment.py` (fear_greed uçları, crowding, news_tone; "aşırı uçlar ters") + testleri.
- [ ] F5-7 `ensemble/conflict.py` tam kural (işaret çelişkisi veya dağılım) + `p_up` çekme + rapor ilk maddesi
      + testleri; `confidence.py` takvim ve rejim cezaları.
- [ ] F5-8 Takvim vetosu davranışı (`veto.py`) + testi.
- [ ] F5-9 Şablonlar: makro, sentiment, çelişki metinleri.
- [ ] F5-10 Frontend: Dashboard'da çelişki rozeti; Coin detay'da makro/sentiment bileşenleri ve "yaklaşan
      olaylar" şeridi; Kalibrasyon modül tablosu 5 satır.

Bitti sayılır
- Beş modül `prediction_signals`'a yazıyor; ağırlık tablosu §9.1 ile aynı.
- Çelişki senaryosu testi: order flow +0.6, makro −0.6 → `conflict=True`, güven `low`, rapor ilk maddesi
  çelişki cümlesi.
- FOMC ±2 saat simülasyonunda takvim vetosu devrede.

---

## Faz 6 — Uyarılar + tarayıcı bildirimi + Ayarlar (2 oturum)

**Amaç:** Eşik aşımlarında uyarı üretiliyor, arayüzde zil ve tarayıcı bildirimi var, ayarlar arayüzden
yönetiliyor.

Görevler
- [ ] F6-1 `alerts/rules.py` (§12 tablosu), `alerts/engine.py` (değerlendirme, `dedup_key`, cooldown, outbox)
      + testleri (her kural için tetiklenen/tetiklenmeyen örnek, cooldown).
- [ ] F6-2 `settings` tablosu: eşikler, bildirim eşiği, semboller; `PUT /config` doğrulamaları
      (`exchangeInfo` sembol kontrolü, ağırlık toplamı 1.0, eşik aralıkları) + testleri.
- [ ] F6-3 Scheduler `settings.changed` izleyicisi: sembol değişince WS akışlarını yeniden başlatma, yeni
      sembol backfill kuyruğu + testleri.
- [ ] F6-4 API: `GET /alerts`, `POST /alerts/ack`, `GET/PUT /config` tam; outbox `alert.created`.
- [ ] F6-5 Frontend: `AlertBell` + sayaç + liste + okundu; `lib/notifications.ts` (izin akışı, `tag`,
      görünürlük kuralı), `lib/sound.ts` (Web Audio ton, tercih localStorage); Dashboard `AlertStrip`.
- [ ] F6-6 Frontend: Ayarlar ekranı — semboller, eşikler, ağırlık tablosu (toplam doğrulaması, varsayılana
      dön), bildirim (izin/eşik/ses), LLM (bütçe, bugünkü harcama), sistem sağlığı.
- [ ] F6-7 Retention: alerts 90 gün.

Bitti sayılır
- `high_probability`, `veto`, `price_move`, `liquidation_wave`, `collector_down` kuralları testte ve gerçek
  ortamda tetikleniyor; aynı olay cooldown içinde ikinci kez üretilmiyor.
- Tarayıcı izni verilmiş sekmede uyarı bildirimi geliyor; sekme öndeyken yalnızca zil.
- Ayarlar ekranından yeni sembol eklendiğinde 10 dk içinde o sembol için mumlar ve ilk tahmin görünüyor.

---

## Faz 7 — Backtest motoru (2–3 oturum)

**Amaç:** Geçmiş veriyle sinyalleri çalıştırıp aynı metriklerle skorlayabilmek; look-ahead eşdeğerlik
kanıtı.

Görevler
- [ ] F7-1 `backtest/engine.py`: `as_of` ızgarası, `run_id`, `source='backtest'`, canlı kod yolu ile aynı
      snapshot/modül/ensemble/ledger/resolver çağrıları; modül aktiflik raporu + testleri.
- [ ] F7-2 `FeatureStore` performans: sembol başına pencere önbelleği ve `as_of` dilimleme; 1 yıl × 4 ufuk × 1
      sembol süre ölçümü loglanır.
- [ ] F7-3 `backtest/report.py` + `cli.py` (`make backtest ARGS=...`): özet tablo, `data/backtests/<run_id>.json`.
- [ ] F7-4 `tests/lookahead/test_backtest_equivalence` gerçek motorla; ayrıca "gelecek mumları boz, backtest
      sonucu değişmesin" testi.
- [ ] F7-5 `make backfill` tam: 2 yıl 1h/4h/1d, 90 gün 1m/5m/15m, funding tam, F&G tam, makro 2 yıl.
- [ ] F7-6 API: `GET /calibration?run_id=` desteği; Frontend: Kalibrasyon ekranında `run_id` seçici
      (canlı / backtest çalıştırmaları).
- [ ] F7-7 Doküman: ilk backtest sonuçları `docs/backtests/README.md` (hangi modüller aktifti, hangi dönem,
      Brier/BSS, uyarılar).

Bitti sayılır
- 2025 yılı BTC için 4 ufukta backtest dakikalar içinde tamamlanıyor ve rapor üretiyor.
- Eşdeğerlik testi yeşil: aynı `as_of` için canlı iş ve motor birebir aynı `SignalResult`.
- Rapor, haber ve WS tabanlı order flow bileşenlerinin backtest'te kapsam dışı olduğunu açıkça yazıyor.

---

## Faz 8 — Kalibrasyon döngüsü (2 oturum)

**Amaç:** Modül bazlı kalibrasyon, haftalık rapor, ağırlık önerisi/uygulama akışı; Kalibrasyon ekranı tam.

Görevler
- [ ] F8-1 `module_calibration_fit` işi: modül başına lojistik fit (`a, b`), modül Brier, isabet + CI,
      "işe yaramıyor" etiketi; `n` eşiği + testleri (sentetik: bilgili modül vs. rastgele modül).
- [ ] F8-2 `k_h` fit (ufuk başına, `n >= 300`) → öneri olarak `weight_proposals` + testi.
- [ ] F8-3 `tracking/weekly.py`: rapor içeriği, `summary_tr` şablonları, `weekly_report` uyarısı + testleri.
- [ ] F8-4 `tracking/weight_proposals.py`: öneri algoritması (§11.5), `apply`/`reject`, `weights` versiyonlama,
      `predictions.weights_json` tutarlılığı + testleri.
- [ ] F8-5 API: `/calibration` tam (modül tablosu, alt kümeler, pencere), `/calibration/weekly`,
      `/calibration/proposals` + apply/reject.
- [ ] F8-6 Frontend: Kalibrasyon ekranı tam — `ModuleTable` (CI, etiket), `HorizonTable`, `WeeklyReportCard`,
      `ProposalCard` (mevcut/önerilen/kanıt, Uygula/Reddet), alt küme ve pencere filtreleri.
- [ ] F8-7 Beklenen aralığın `p_up`'a göre kaydırılması: yalnızca kalibrasyon verisi destekliyorsa (öneri
      olarak sunulur; uygulanması kullanıcı kararı).

Bitti sayılır
- Haftalık rapor Pazartesi üretiliyor ve ekranda görünüyor; en az bir modül için "işe yaramıyor / yarıyor"
  cümlesi CI ile birlikte yazıyor.
- Ağırlık önerisi uygulandığında sonraki tahmin yeni ağırlıkla, önceki tahminler eski `weights_json` ile
  kalıyor (test).

---

## Faz 9 — Sertleştirme ve işletim (1–2 oturum)

Görevler
- [ ] F9-1 Docker prod ayarları: non-root, healthcheck'ler, `restart: unless-stopped`, log rotasyonu, imaj
      boyutu.
- [ ] F9-2 Yedekleme: günlük `sqlite3 .backup` ile `data/backups/`, 14 gün saklama; geri yükleme notu.
- [ ] F9-3 Uzun süre testi: 7 gün kesintisiz; bellek ve DB büyüme ölçümü; retention doğrulaması.
- [ ] F9-4 Hata bütçesi: collector kesinti sürelerinin haftalık raporda görünmesi; `collector_down` uyarısının
      gerçek kesintide çalıştığının gözlemi.
- [ ] F9-5 Performans: `/calibration` ve `/predictions` sorguları 200 ms altında (indeks kontrolü);
      `metrics_daily` materyalizasyonu.
- [ ] F9-6 Doküman: `README.md` (kurulum, `.env`, ilk çalıştırma, ekran görüntüleri), `docs/operations.md`
      (yedek, geri yükleme, takvim güncelleme, sembol ekleme).
- [ ] F9-7 Frontend cila: klavye kısayolları, boş durum ekranları, hata durumları, yükleme iskeletleri;
      `tokens.css` açık tema seti (öncelik değil).

Bitti sayılır
- 7 günlük kesintisiz çalışma raporu; DB büyümesi öngörülen sınırda.
- Yedekten geri yükleme bir kez denenmiş ve belgelenmiş.

---

## Sonraya bırakılanlar (bu fazlarda yapılmaz)

- Message Batches API ile toplu haber sınıflandırma (`llm/batch.py`) — geçmiş haber arşivi olursa.
- Ücretli geçmiş türev verisi (OI/likidasyon) ile order flow backtest'i — bütçe kararı.
- TimescaleDB geçişi (§20) — SQLite darboğaz olursa.
- Yeni coin için LLM şema `Literal` güncellemesinin otomasyonu.
- Açık tema.
- Kimlik doğrulama — yalnızca internete açılacaksa, reverse proxy katmanında.
