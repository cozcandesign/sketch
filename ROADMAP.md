# ROADMAP.md — MarketPulse

Fazlar sıralıdır; bir faz "Bitti sayılır" maddelerinin tamamı sağlanmadan sonraki faza geçilmez.
Görev kimlikleri `F<faz>-<no>` commit gövdesinde `Refs:` ile anılır. Biten görev `[x]` yapılır.
Faz içine ROADMAP'te olmayan iş eklenmez; gerekiyorsa önce buraya görev olarak yazılır.

**Faz 0–9 temel sistemdir ve sırayla yapılır. Faz 10 ve sonrası genişletmedir**; kendi kuralları vardır
(erişim doğrulaması, tek kaynak, 200 tahminlik ispat) ve aralarındaki sıra esnektir — erişilemeyen bir
kaynak fazı atlanır. Bkz. "Faz 10 ve sonrası" bölümü ve CLAUDE.md §14.

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
- [x] F0-1 `backend/pyproject.toml` (uv, Python 3.12), bağımlılıklar: fastapi, uvicorn, pydantic v2,
      pydantic-settings, sqlalchemy 2, aiosqlite, alembic, httpx, websockets, pandas, numpy, loguru,
      anthropic, feedparser, yfinance, pyyaml. Dev: pytest, pytest-asyncio, respx, hypothesis, time-machine,
      ruff, mypy, pandas-stubs, honcho, pre-commit.
- [x] F0-2 `ruff`, `mypy --strict`, `pytest` yapılandırması; `signals → storage` import yasağı (import-linter sözleşmesi).
- [x] F0-3 `config.py` (pydantic-settings, `MP_` ön eki), `.env.example`, `core/` (Horizon, Symbol, Clock,
      FakeClock, utc_now, floor_to_minute, hata sınıfları) + testleri.
- [x] F0-4 `storage/`: DB bağlantısı (WAL, busy_timeout), `tables.py` (tüm §6 tabloları), Alembic ilk migration,
      `Repository` protokolü ve `SqliteRepository` iskeleti, `Outbox` yazıcı/okuyucu + testleri.
- [x] F0-5 `engine/main.py`: supervisor, heartbeat işi, `SIGTERM` ile temiz kapanış, çift örnek koruması.
- [x] F0-6 `api/app.py`: FastAPI, CORS, `/api/v1/health`, `/ws` (subscribe/ping/pong), outbox relay görevi.
- [x] F0-7 Frontend iskeleti: Vite + React + TS strict + Tailwind, `tokens.css` koyu tema, `Shell`
      (Sidebar / Topbar / **DataStatusStrip** her ekranın üstünde / StatusBar), 7 boş rota (Dashboard, Coin,
      Haber, Tahminler, Kalibrasyon, Ayarlar, Maliyet), `WsClient`, `i18n/tr.ts`, eslint/prettier/vitest.
- [x] F0-8 `make gen-types` (openapi-typescript) ve ilk `types.gen.ts`.
- [x] F0-9 `Makefile` (tüm hedefler), `Procfile.dev`, `docker-compose.yml`, iki Dockerfile, `nginx.conf`,
      `.gitignore`, `.dockerignore`, `pre-commit` (ruff, mypy, eslint).
- [x] F0-10 `reporting/banned_words.py` + `templates.py` ve `i18n/tr.ts`'i tarayan test (liste boşken de
      koşar).

Bitti sayılır
- `make check` yeşil (backend + frontend).
- `make dev` üç süreci başlatır; veri durumu şeridi WS "bağlı" ve engine heartbeat'ini gösterir.
- `docker compose up` ile aynı sonuç Docker'da; `http://localhost:3000` açılır ve boş da olsa çalışan bir
  sayfa görünür. (Bu, kullanıcının Faz 0 başarı ölçütüdür.)
- `.env` olmadan uygulama anlaşılır hata ile durur (hangi anahtar eksik).

Faz 0 durum notu (geliştirme ortamında doğrulandı)
- Doğrulandı: `make check` (74 backend + 16 frontend testi), `make dev` (honcho: api + engine + Vite),
  `vite preview` ile üretim build'i, `/api/v1/health` ve `/ws` frontend proxy'sinden, tarayıcıda (headless
  Chromium) panel açılışı ve konsolda hata yok, engine'e SIGTERM ile temiz kapanış (heartbeat silindi, API
  "engine kopuk" dedi), `.env` yokken anlaşılır hata (unit test + `make dev` ön kontrolü).
- Burada çalıştırılamadı: `docker compose up --build` (geliştirme ortamında Docker daemon yok). Yalnızca
  `docker compose config` ile dosya doğrulandı; iki Dockerfile derlenmedi. **Kullanıcının makinesinde
  denenecek**; hata çıkarsa çıktı bir sonraki oturuma yapıştırılır.

---

## Faz 1 — Veri omurgası + tahmin defteri + doğruluk takibi (3–4 oturum)

**Amaç:** Mumlar akıyor, tahmin defteri ve resolver çalışıyor, metrikler hesaplanıyor. Gerçek motor henüz
yok; baseline tahminler defteri uçtan uca kullanıyor. Arayüzde fiyat kartları, tahmin geçmişi ve ilk
kalibrasyon grafiği var.

Görevler
- [x] F1-1 `engine/ratelimit.py`: `exchangeInfo`'dan limit okuma, token bucket, `X-MBX-USED-WEIGHT-1M`
      senkronu, 429/418 davranışı + testleri (respx).
- [x] F1-2 Binance HTTP istemcisi (httpx, retry/backoff, zaman damgası normalizasyonu) + testleri.
- [x] F1-3 `collectors/spot_klines`: REST backfill (1m/5m/15m/1h/4h/1d, sayfalama), boşluk denetimi,
      yalnızca kapanmış mum yazma, idempotent upsert + testleri (kaydedilmiş yanıt fixture'ları).
- [x] F1-4 `collectors/binance_ws` altyapısı: combined stream, yeniden bağlanma, 23. saat planlı yenileme,
      `kline_1m` işleyicisi (`x=true` filtresi) + sahte akış testleri.
- [x] F1-5 `engine/jobs.py`: duvar saatine hizalı `Job`, `predict_*` tetikleri (+10 sn), `resolve`,
      `gap_check`, `retention`, `health_heartbeat`; `FakeClock` ile testler (tetik anları, kaçırılan tetik
      davranışı).
- [x] F1-6 `tracking/ledger.py`: tahmin + modül skorları tek transaction; `non_overlapping` bayrağı; `source`
      ve `run_id` + testleri.
- [x] F1-7 `tracking/resolver.py`: 1m mum ile çözümleme, REST backfill yolu, 24 saat sonra `unresolved`,
      `hit`/`brier`/`realized_return` + testleri (sınır: eşitlik, eksik mum, geç gelen mum).
- [x] F1-8 `tracking/metrics.py`: Brier, BSS, kalibrasyon kovaları, isabet + Wilson CI, alt kümeler
      (all / non_overlapping / high_confidence), günlük seri; elle hesaplanmış örneklerle testler.
- [x] F1-9 Baseline tahminciler (`climatology`, `momentum`), `predict_*` işlerine bağlanması
      (`source='baseline'`) + testleri.
- [x] F1-10 `tests/lookahead/test_resolver_boundary` ve `test_truncation_invariance` (candles için; diğer veri
      setleri kendi fazında eklenir).
- [x] F1-11 API: `GET /predictions`, `/predictions/{id}`, `/market/{symbol}` (fiyat + 24s Δ + baseline
      tahminler), `/market/{symbol}/candles`, `/calibration` (Brier serisi, kovalar, isabet), `/health`;
      `api/live_relay.py` (miniTicker → `price.*`); outbox `prediction.created`, `outcome.resolved`,
      `health.changed`.
- [x] F1-12 Frontend: Dashboard (CoinCard: canlı fiyat + baseline olasılık placeholder'ı + DataHealthDot),
      Tahmin geçmişi tablosu (filtre + cursor sayfalama + Drawer), Kalibrasyon ekranının Brier serisi ve
      kalibrasyon eğrisi (baseline verisiyle), `DataStatusStrip` gerçek collector verisiyle (çalışıyor / son
      güncelleme / kopuk).
- [x] F1-13 `make backfill` CLI (klines; ileride diğer setler eklenir).
- [x] F1-14 Retention işi (outbox 24 saat; klines silinmez, K21) + testi.

Bitti sayılır
- 3 sembol için 1m..1d mumlar canlı akıyor; WS kesilince boşluk 5 dk içinde REST ile dolmuş oluyor (test ve
  gerçek ortamda gözlem).
- Baseline tahminler dört ufukta üretiliyor, ufuk dolunca çözümleniyor; kalibrasyon ekranında Brier serisi
  ve kalibrasyon eğrisi doluyor.
- Look-ahead testleri (`resolver_boundary`, `truncation_invariance`) yeşil.
- Sistem 24 saat kesintisiz çalışmış, hiçbir supervisor sürekli yeniden başlamıyor (health tablosu temiz).

Faz 1 durum notu (geliştirme ortamında doğrulandı)
- Doğrulandı: `make check` (171 backend + 30 frontend testi), `make backfill` (3 sembol × 6 zaman dilimi =
  38.568 mum, 8 saniye), engine'in WS'ten canlı mum yazması, dört ufukta referans tahmin üretimi, ufuk
  dolunca çözümleme, `/predictions` ve `/calibration` uçları, tarayıcıda Panel / Tahmin geçmişi /
  Kalibrasyon ekranları (konsolda hata yok), canlı fiyatın WebSocket ile panele akması.
- **Gerçek Binance'e bağlanılamadı:** bu geliştirme ortamının ağ politikası `api.binance.com` adresini
  403 ile engelliyor. Bu yüzden uçtan uca doğrulama, aynı yanıt biçimlerini üreten **yerel bir sahte
  Binance sunucusuyla** yapıldı; birim testleri kayıtlı gerçek yanıt biçimlerini kullanır. Gerçek API'ye
  ilk bağlantı **kullanıcının makinesinde** olacak; ilk çalıştırmada `make backfill` çıktısı ve veri
  durumu şeridi kontrol edilmeli.
- Ekran görüntülerindeki sayılar sahte sunucunun sentetik fiyat serisinden gelir; **piyasa verisi
  değildir**. Gerçek isabet oranları ancak sistem sende çalıştıkça birikir.

---

## Faz 2 — Teknik modül + Ensemble v0 + rapor (3 oturum)

**Amaç:** İlk gerçek sinyal modülü. Tahminler artık `source='live'` ile üretiliyor ve ölçülüyor. Coin
detay ekranı mum grafiği ve modül kırılımıyla açılıyor.

Görevler
- [x] F2-1 `features/indicators.py` (+ `features/levels.py`): EMA, SMA, RSI, MACD, ATR, Bollinger, ADX, swing high/low, volume profile
      (POC, değer alanı); her biri referans değer testi; `hypothesis` nedensellik testi (gelecek perturbasyonu).
- [x] F2-2 `features/feature_store.py`: `FeatureSnapshot`, candles için kesme kuralı, geriye bakış pencereleri,
      `coverage` hesabı + testleri; `test_truncation_invariance` tüm candles interval'larına genişletilir.
- [x] F2-3 `signals/base.py` (`SignalResult`, `SignalModule`, ufuk→TF eşlemesi) ve `signals/technical.py`
      (trend, momentum, volume, sr, vol_regime) + unit testleri (işaret, aralık, eksik veri, yasak kelime).
- [x] F2-4 `ensemble/`: `combine.py` (ağırlıklı log-odds, `k_h`, K19 kırpma), `confidence.py`,
      `conflict.py`, `expected_range.py`; `weights.default.yaml` yükleyici; `weights` tablosu tohumu + testleri.
      Bu fazda yalnızca technical modülü aktif; diğerleri `coverage=0`.
- [x] F2-5 `reporting/`: `templates.py` (teknik modül şablonları), `counter_argument.py`, `build_report()`
      + testleri; yasak kelime testi şablonları tarar.
- [x] F2-6 `predict_*` işleri gerçek akışa geçer (snapshot → modüller → ensemble → rapor → ledger);
      modül istisnasında "veri yok" davranışı testi.
- [x] F2-7 `tests/lookahead/test_future_perturbation` (technical için) ve `test_backtest_equivalence`
      iskeleti (motor Faz 7'de; şimdilik aynı fonksiyonun iki çağrısı).
- [x] F2-8 API: `GET /signals/{symbol}`, `/market/{symbol}/levels`; `/market/{symbol}` canlı tahmin özetleri;
      outbox `signals.updated`.
- [x] F2-9 Frontend: Coin detay ekranı — `CandleChart` (lightweight-charts; interval seçici; EMA/S-R/POC
      overlay toggle; tahmin işaretçileri sonuç rengiyle), ufuk sekmeleri, `ModuleBreakdown` +
      `RationaleList`, `ReportCard` (headline, gerekçe, karşıt argüman, beklenen aralık). Dashboard kartları
      gerçek olasılık + `ConfidenceBadge` + çelişki/veto rozetleri.
- [x] F2-10 Kalibrasyon ekranına modül tablosu (şimdilik tek modül) ve baseline karşılaştırma çizgileri.

Bitti sayılır
- Dört ufukta canlı tahminler üretiliyor; her tahminin `prediction_signals` satırı, raporu ve karşıt
  argümanı var.
- Teknik modül unit testleri, gösterge referans testleri ve look-ahead testleri yeşil.
- Coin detay ekranında mum grafiği, işaretçiler ve modül kırılımı çalışıyor; sayfa yenilemeden yeni tahmin
  düşüyor.

Faz 2 durum notu (geliştirme ortamında doğrulandı)
- Doğrulandı: `make check` (350 backend + 39 arayüz testi), canlı tahmin yolunun uçtan uca çalışması
  (snapshot → teknik modül → ensemble → rapor → defter → çözümleme), `/signals/{symbol}` ve
  `/market/{symbol}/levels` uçları, coin detay ekranı (mum grafiği, EMA/seviye/POC katmanları, tahmin
  işaretçileri, ufuk sekmeleri, modül kırılımı, karşıt argüman), kalibrasyon ekranındaki modül tablosu
  ve referans karşılaştırması. Tarayıcı konsolunda hata yok.
- **Sayılar sentetik seriden gelir, piyasa verisi değildir.** Doğrulama için üretilen veri setinde
  teknik modül %46,2 isabet (CI 0,431–0,494), referans çizgisi %53,3 — yani ekranda "referansı
  geçemiyor" yazıyor. Bu, rastgele yürüyüş serisinde beklenen sonuçtur ve modül hakkında **hiçbir şey
  söylemez**; gerçek hüküm canlıda 200+ çözümlenmiş tahminden sonra verilir (K26).
- Mum grafiği jsdom'da çizilemediği için birim testlerde kütüphane taklit edilir; grafiğin kendisi
  gerçek tarayıcıda ekran görüntüsüyle doğrulandı.
- Faz 2'de yalnızca teknik modül veri üretir. Ensemble kalan dört modülün ağırlığını ona dağıtır ama
  güven çarpanı (`breadth`) bunu telafi etmez: tahminler bilerek "düşük güven" görünür.

---

## Faz 3 — Order flow (3 oturum)

**Amaç:** Funding, OI, L/S, taker, likidasyon, order book, CVD toplanıyor ve order flow modülü çalışıyor.
Kendi arşivimiz birikmeye başlıyor.

Görevler
- [x] F3-1 `collectors/funding` (geçmiş + anlık), `open_interest` (hist + live), `long_short`, `taker_volume`
      + testleri; `make backfill`'e funding ve 30 günlük OI/LS/taker eklenir.
- [x] F3-2 `collectors/binance_ws` futures akışları: `aggTrade`, `forceOrder`, `depth20@100ms`; 1 dk kova
      toplayıcı (`orderflow_1m`), `coverage_seconds`, `liquidations` ham kayıt; kapanışta flush + testleri.
- [x] F3-3 `collectors/depth_snapshot` (REST 500 seviye, ±%1 derinlik) + testi.
- [x] F3-4 `FeatureStore`: funding, OI, LS, taker, orderflow_1m, liquidations veri setleri; kesme ve kapsama
      + `truncation_invariance` genişletme.
- [x] F3-5 `signals/orderflow.py`: funding_dev, oi_price (4 durum), liquidations, book_imbalance, cvd +
      unit testleri (her durum için sentetik seri) + `future_perturbation`.
- [x] F3-6 Şablonlar: order flow gerekçeleri; ensemble'da orderflow aktif.
- [x] F3-7 API: `GET /market/{symbol}/orderflow`; `/market/{symbol}` içine funding/OI/LS özetleri.
- [x] F3-8 Frontend: Coin detay alt panelleri — `FundingPanel`, `OIPanel` (OI + fiyat, durum etiketi),
      `LiquidationPanel`, `OrderBookPanel`, `CVDPanel`; `ModuleBreakdown`'da orderflow bileşenleri.
- [x] F3-9 Retention: orderflow_1m ve liquidations 90 gün.
- [x] F3-10 Canlı çalıştırmada çıkan düzeltmeler: (a) `spot_klines` sağlık kaydı `gap_check` işine
      bağlanır — REST toplayıcı çalışırken şeritte yanlışlıkla "aksıyor" görünüyordu; (b) türev geçmiş
      tamamlamaları (`funding_hist`, `open_interest_hist`) açılışta bir kez koşar — funding z-skoru ve
      `funding_dev` bileşeni ilk 8 saat boyunca eksik kalıyordu; (c) sağlık kayıtları açılışta DB'den
      okunur — yeniden başlatmadan sonra seyrek işler "çalışıyor hiç" görünüyordu; (d) futures WS
      mesaj ayrıştırma hataları sessizce yutulmaz, loglanır ve sağlık kaydına yazılır.

Bitti sayılır
- WS akışları 24 saat kesintisiz; `coverage_seconds` ortalaması > 3500/3600.
- Order flow modülü tahminlere katılıyor; kalibrasyon ekranı modül tablosunda ayrı satırı var.
- Bir WS kesintisi simülasyonunda modül `coverage` düşürüyor, tahmin yine üretiliyor, güven düşüyor (test).

Faz 3 durum notu (geliştirme ortamında doğrulandı)
- Doğrulandı: `make check` (438 backend + 59 arayüz testi), `/market/{symbol}/orderflow` ucu, coin
  ekranındaki beş order flow paneli (funding + long/short, açık pozisyon, zorunlu kapatmalar,
  order book, CVD), kapsama rozeti, kalibrasyon ekranında order flow'un ayrı satırı. Tarayıcı
  konsolunda hata yok. WS kesintisi ölçütü testle karşılanıyor
  (`test_an_order_flow_outage_lowers_confidence_but_still_predicts`).
- **Bu ortamdan `fapi.binance.com` ve `api.binance.com` erişilemiyor (HTTP 000).** Collector'lar
  belgelenmiş yanıt biçimlerine göre yazıldı ve `respx` ile kaydedilmiş yanıtlarla test edildi;
  panellerin doldu mu diye bakılan veri **sentetiktir, piyasa verisi değildir** ve yalnızca
  scratchpad veritabanına yazıldı. Gerçek futures verisiyle ilk çalışma kullanıcının makinesinde olur.
- **Açık kalan bitti ölçütü:** "WS akışları 24 saat kesintisiz, `coverage_seconds` ortalaması
  > 3500/3600" burada ölçülemez; kullanıcının makinesinde bir gün çalıştıktan sonra
  `/market/{symbol}/orderflow` kapsama rozetinden okunacak.
- Kalibrasyon tablosunda order flow satırı "veri yetersiz" görünür: modül yeni katıldı, henüz
  çözümlenmiş tahmini yok. Hüküm 200 çözümlenmiş tahminden sonra verilir (K26).

---

## Faz 4 — Haber + iki kademeli LLM + veto + maliyet (4 oturum)

**Amaç:** RSS akışı toplanıyor, tekrarlar birleştiriliyor, her haber Kademe 1 (Haiku) ile eleniyor, önemli
haberler Kademe 2 (Sonnet) ile derin analiz ediliyor, haber modülü ve veto çalışıyor. Her haberin sonraki
fiyat hareketi kaydediliyor; Maliyet ekranı ve `/costs` açık.

Görevler
- [ ] F4-1 `collectors/rss` (4 kaynak, koşullu istek, `published_at` normalizasyonu) + testleri (kaydedilmiş
      feed fixture'ları). `collectors/cryptopanic` (token varsa) + testi.
- [ ] F4-2 `llm/dedup.py`: URL kanonikleştirme, başlık token Jaccard, grup başı seçimi + testleri.
- [ ] F4-3 `llm/client.py`: `AsyncAnthropic`, `messages.parse`, sabit sistem promptu + `cache_control`, hata
      sınıfı ayrımı (429/5xx backoff, 4xx down); `llm/budget.py`: `llm_usage` (model + kademe), günlük tavan,
      kademe bazlı kapanma sırası (önce Kademe 2, sonra Kademe 1) + testleri (SDK mock; gerçek API'ye çıkan
      test yok).
- [ ] F4-4 `llm/tier1.py` (Haiku): kategori, ilgili coinler, kaba ton, önem 0–1; parti 20; `<item>` sarma ve
      talimat yok sayma; şema testi.
- [ ] F4-5 `llm/tier2.py` (Sonnet): tek haber, derin analiz şeması (fiyatlanmış mı, güvenilirlik, ikinci
      derece etkiler, benzer geçmiş olay, etki, güven, ufuk, gerekçe); `llm/router.py`: `importance >
      MP_LLM_TIER2_THRESHOLD` ise Kademe 2'ye yönlendirme, bütçe kontrolü + testleri.
- [ ] F4-6 `collectors/news_tier1` ve `collectors/news_tier2` işleri (kuyruk, parti, miras kopyalama, bütçe
      aşımında durma, `budget_exhausted` health) + testleri.
- [ ] F4-7 `FeatureStore`: news veri seti (`published_at + gecikme` kesmesi; Kademe 2 varsa onun etkisi,
      yoksa Kademe 1 tonu) + `truncation_invariance`.
- [ ] F4-8 `signals/news.py`: decay, ilgi, kategori bileşenleri, Kademe 1/2 ağırlıklandırması, veto bayrağı
      (yalnızca Kademe 2) + unit testleri (yarı ömür, tekrar sayılmaması, veto eşiği) + `future_perturbation`.
- [ ] F4-9 `ensemble/veto.py`: haber vetosu davranışı (ağırlık ezme, `p_up` harmanı, güven `low`, rapor
      başlığı) + testleri.
- [ ] F4-10 `tracking/news_outcomes.py`: her haber için 1s/4s/24s sonrası fiyat hareketi (ilgili semboller),
      kademe bazlı isabet (`sign(etki) == sign(getiri)`), Kademe 1 vs Kademe 2 karşılaştırma metrikleri +
      testleri; `news_outcomes` işi.
- [ ] F4-11 Şablonlar: haber gerekçeleri ve veto metinleri; yasak kelime testi güncel.
- [ ] F4-12 API: `GET /news` (filtreler, cursor, kademe alanları), `GET /costs` (günlük/aylık, model ve kademe
      kırılımı, tavan, kalan), `GET /calibration/news-tiers`; outbox `news.classified`; `/config` içinde LLM
      durumu ve bütçe tavanı.
- [ ] F4-13 Frontend: Haber akışı ekranı (`NewsFilters`, `NewsCard`, `ImpactBadge`, `TierBadge` "Haiku" /
      "Haiku+Sonnet", grup boyutu, kategori dağılımı); Coin detay ve Dashboard'da veto rozeti;
      `ModuleBreakdown`'da haber maddeleri.
- [ ] F4-14 Frontend: Maliyet ekranı (`/costs`): bugün / bu ay harcama, tavan ve kalan, kademe ve model
      kırılımı, günlük seri (Recharts), bütçe aşımı durumu. Ayarlar ekranında bütçe tavanı alanı (F6-6 ile
      birleşir).
- [ ] F4-15 Frontend: Kalibrasyon ekranına "Haber kademe isabeti" kartı (Haiku vs Sonnet, ufuk bazlı, n ile).
- [ ] F4-16 Retention: news 180 gün. `weights` tablosu: news aktif.

Bitti sayılır
- Bir günlük gerçek akışta tekrar oranı, Kademe 2'ye giden haber oranı ve maliyet loglanmış; günlük maliyet
  tavanın altında ve Maliyet ekranında görünüyor.
- Sınıflandırma çıktısı her zaman şemaya uyuyor (parse hatası sıfır). Bütçe aşımı simülasyonunda önce
  Kademe 2 kapanıyor, Haiku devam ediyor; ikisi kapanınca modül "veri yok" diyor ve tahmin yine üretiliyor.
- Veto senaryosu testi: sentetik "çok negatif, güven 0.9" Kademe 2 haberi teknik yukarı sinyalini eziyor ve
  rapor başında uyarı var.
- `news_outcomes` 24 saat sonra dolmuş; kalibrasyon ekranında Haiku vs Sonnet isabeti n değerleriyle
  görünüyor.

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
- [ ] F6-1 `alerts/rules.py` (§12 tablosu), `alerts/evaluator.py` (değerlendirme, `dedup_key`, cooldown, outbox)
      + testleri (her kural için tetiklenen/tetiklenmeyen örnek, cooldown).
- [ ] F6-2 `settings` tablosu: eşikler, bildirim eşiği, semboller; `PUT /config` doğrulamaları
      (`exchangeInfo` sembol kontrolü, ağırlık toplamı 1.0, eşik aralıkları) + testleri.
- [ ] F6-3 Engine `settings.changed` izleyicisi: sembol değişince WS akışlarını yeniden başlatma, yeni
      sembol backfill kuyruğu + testleri.
- [ ] F6-4 API: `GET /alerts`, `POST /alerts/ack`, `GET/PUT /config` tam; outbox `alert.created`.
- [ ] F6-5 Frontend: `AlertBell` + sayaç + liste + okundu; `lib/notifications.ts` (izin akışı, `tag`,
      görünürlük kuralı), `lib/sound.ts` (Web Audio ton, tercih localStorage); Dashboard `AlertStrip`.
- [ ] F6-6 Frontend: Ayarlar ekranı — semboller, eşikler, ağırlık tablosu (toplam doğrulaması, varsayılana
      dön), bildirim (izin/eşik/ses), LLM (bütçe tavanı, Kademe 2 eşiği, bugünkü harcama), sistem sağlığı.
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

## Faz 10 ve sonrası — genişletme fazları

Bu fazlar **Faz 1–9 bitmeden ve temel sistem canlıda en az birkaç hafta ölçülmeden başlamaz.** İlke ve
kurallar CLAUDE.md §14'tedir; burada yalnızca faz içerikleri var. Her genişletme fazı için değişmez
kurallar:

1. **Önce erişim doğrulaması (her fazın `-0` görevi).** Uç nokta gerçekten çağrılır, yanıt biçimi
   `tests/fixtures/` altına kaydedilir, hız limiti ve kullanım koşulları okunur, geçmiş veri derinliği
   ölçülür. Erişilemiyorsa **faz atlanır ve kullanıcıya raporlanır**; uydurma veri kullanılmaz.
2. **Faz başına tek veri kaynağı.** İki kaynak aynı fazda paketlenmez; hangisinin işe yaradığı
   ayrıştırılamaz hale gelir.
3. **Yeni modül düşük ağırlıkla başlar** (0.05) ve `prediction_signals` üzerinden ayrı ölçülür.
4. **200 çözümlenmiş tahmin ispatı (K26).** Modülün isabet oranının Wilson alt sınırı her iki referans
   tahmincinin isabetini geçmeli. Geçemezse Faz 17 tasfiye akışına girer.
5. **Geçmiş veri yoksa backtest edilmez, ileriye dönük ölçülür.** Bu dürüstçe yazılır, "backtest ettik"
   denmez.
6. Fazlar arası sıra esnektir: erişim doğrulaması başarısız olan faz atlanıp sonraki faza geçilir.

> **Ağ notu:** Bu dokümandaki kaynakların hiçbiri Claude'un geliştirme ortamından doğrulanamaz; o ortamın
> ağ politikası `api.binance.com` dahil dış adresleri engelliyor. Erişim doğrulaması **kullanıcının
> makinesinde** yapılır. Aşağıdaki "beklenen uç nokta" bilgileri plan içindir, doğrulanmış gerçek değildir.

---

## Faz 10 — Opsiyon verisi (Deribit)

**Neden:** Opsiyon piyasası, spot fiyatın içermediği bir şeyi taşır: piyasanın **gelecek volatilite
beklentisi** ve hangi yönde korunma satın aldığı. Fiyattan türetilemez.

**Beklenen kaynak:** Deribit public REST (anahtar gerekmez): `/public/get_instruments`,
`/public/get_book_summary_by_currency`, `/public/ticker` (greeks + örtük volatilite),
`/public/get_index_price`. BTC ve ETH kapsamı iyi; **SOL opsiyon kapsamı doğrulanmalı**, yoksa o sembol
için modül "veri yok" der.

Görevler
- [ ] F10-0 Erişim doğrulaması: uç noktalar, hız limiti, SOL kapsamı, geçmiş derinliği. Rapor edilmeden
      sonraki göreve geçilmez.
- [ ] F10-1 `collectors/deribit.py`: enstrüman listesi, vade takvimi, zincir özeti; 5 dk periyot.
- [ ] F10-2 Tablolar: `option_chain_snapshots` (vade × kullanım fiyatı özetleri), `option_metrics`
      (ATM IV, skew, put/call, term structure, max pain, yaklaşık GEX), `option_expiries`.
- [ ] F10-3 Metrik hesapları + birim testleri: ATM örtük volatilite, 25-delta risk reversal (skew),
      açık pozisyona dayalı put/call oranı, ön vade ile arka vade IV farkı (term structure),
      max pain, yaklaşık gamma exposure. Her biri elle hesaplanmış küçük zincirle test edilir.
- [ ] F10-4 `FeatureStore`: opsiyon veri seti + kesme kuralı (`snapshot_ts <= as_of`) + truncation testi.
- [ ] F10-5 `signals/options.py`: IV rejimi, skew sapması, term structure eğimi, vadeye yakınlık.
      Ağırlık 0.05 başlar.
- [ ] F10-6 Vade günleri `calendar_events` tablosuna yazılır (Faz 5 takvimiyle aynı yol).
- [ ] F10-7 Arayüz: Coin detayda opsiyon paneli (IV terim yapısı, skew, put/call, max pain seviyesi).
- [ ] F10-8 Kalibrasyon ekranında modül satırı; 200 tahmin sayacı görünür.

Bitti sayılır
- Opsiyon metrikleri 7 gün kesintisiz toplanıyor, `coverage` > %95.
- Modül tahminlere katılıyor ve ayrı ölçülüyor; 200 tahmin dolmadan ağırlık artırılmıyor.
- SOL kapsamı yoksa bu açıkça raporlanmış ve modül o sembolde "veri yok" diyor.

---

## Faz 11 — Borsa arası fiyat farkı ve basis

**Neden:** Aynı varlığın farklı borsalardaki fiyat farkı, **hangi tarafın alıcı olduğunu** gösterir
(ABD kurumsalı mı, Kore perakendesi mi). Perp-spot basis kaldıraçlı talebin fiyatıdır. Tek borsanın
fiyatından görülemez.

**Beklenen kaynak:** Coinbase Exchange public API (ticker, order book), Upbit public API (KRW
fiyatları) + USD/KRW kuru (yfinance `KRW=X`), Kraken public API, Binance USDT-M perpetual (Faz 3'te
zaten toplanıyor) ve üç aylık vadeli kontratlar.

Görevler
- [ ] F11-0 Erişim doğrulaması: Coinbase, Upbit, Kraken public uçları; hız limitleri; USD/KRW kuru
      kaynağının güvenilirliği.
- [ ] F11-1 `collectors/crossexchange.py`: sembol başına çoklu borsa fiyatı ve top-20 derinliği, 1 dk.
- [ ] F11-2 Tablolar: `exchange_prices`, `exchange_depth`, `basis_series`.
- [ ] F11-3 Hesaplar + testleri: Coinbase primi (Coinbase/Binance − 1), Kore primi (Upbit KRW → USD
      çevrimi sonrası fark), perp-spot basis, üç aylık vadeli yıllıklandırılmış basis (term structure),
      borsalar arası derinlik oranı.
- [ ] F11-4 `FeatureStore` + kesme + truncation testi.
- [ ] F11-5 `signals/crossexchange.py`: prim sapması (30 günlük z), basis rejimi, derinlik dengesizliği.
      Ağırlık 0.05.
- [ ] F11-6 Arayüz: Coin detayda "borsa farkı" paneli; prim serileri.
- [ ] F11-7 Kalibrasyon modül satırı + ispat sayacı.

Bitti sayılır
- Üç borsadan fiyat 7 gün kesintisiz; kur çevrimi doğrulanmış (bilinen bir günün primi elle kontrol).
- Modül ayrı ölçülüyor.

---

## Faz 12 — Kurumsal akış (ETF ve CME)

**Neden:** Spot ETF akışları ve CME açık pozisyonu, kripto borsalarında görünmeyen **kurumsal talebi**
gösterir. Hafta sonu CME kapalıyken oluşan boşluklar ayrı bir davranış üretir.

**Beklenen kaynak — en riskli faz.** ETF günlük net akışları için resmî ücretsiz API yok; Farside
Investors gibi kaynaklar HTML tablo yayınlar (scraping; K6'daki "scraping kırılgan" gerekçesiyle
çelişir). CME açık pozisyonu için ücretsiz gecikmeli veri kayıt gerektirebilir.

Görevler
- [ ] F12-0 Erişim doğrulaması **ve karar noktası**: ETF akışı ve CME OI için gerçekten ücretsiz,
      kullanım koşullarına uygun bir yol var mı? Yoksa seçenekler (ücretli kaynak, elle günlük giriş,
      fazı atlama) kullanıcıya sunulur ve **kullanıcı karar verene kadar faz başlamaz.**
- [ ] F12-1 `collectors/etf_flows.py`: günlük net akış (varlık bazında), yayın gecikmesi modellenir
      (akış T günü için T+1'de yayımlanır → look-ahead riski burada yüksek, `available_at` zorunlu).
- [ ] F12-2 `collectors/cme.py`: açık pozisyon, uzlaşma fiyatı, seans saatleri.
- [ ] F12-3 Tablolar: `etf_flows`, `cme_daily`, `cme_sessions`.
- [ ] F12-4 Hesaplar + testleri: 5 günlük kümülatif net akış, akışın piyasa değerine oranı, CME OI
      değişimi, hafta sonu boşluğu (Cuma kapanış → Pazar açılış) ve boşluğun kapanma oranı.
- [ ] F12-5 `FeatureStore` + `available_at` kesmesi + truncation testi (bu fazda kritik: veri geç yayımlanır).
- [ ] F12-6 `signals/institutional.py`, ağırlık 0.05.
- [ ] F12-7 Arayüz: Panelde "kurumsal akış" şeridi; Coin detayda akış serisi.
- [ ] F12-8 Kalibrasyon modül satırı + ispat sayacı.

Bitti sayılır
- Akış verisi en az 30 gün geriye dolmuş ve yayın gecikmesi `available_at` ile doğru modellenmiş.
- Truncation testi, T günü akışının T günü tahminlerinde **görünmediğini** kanıtlıyor.

---

## Faz 13 — Zincir üstü (on-chain)

**Neden:** Borsaya giren/çıkan coin miktarı ve stablecoin arzı, alım gücünün **fiyat oluşmadan önceki**
hareketidir.

**Beklenen kaynak:** DefiLlama stablecoins API (ücretsiz, anahtarsız) → stablecoin arzı ve basım;
mempool.space (BTC ağ istatistikleri, ücretsiz); Etherscan ücretsiz kademe (anahtar gerekir, ücretsiz)
→ büyük transferler ve bilinen borsa adreslerine akış. **Borsa net akışının kaliteli hali genelde
ücretlidir (Glassnode, CryptoQuant).** Ücretsiz uçlarla başlanır; yetersizse bu açıkça raporlanır.

Görevler
- [ ] F13-0 Erişim doğrulaması: DefiLlama, mempool.space, Etherscan ücretsiz kademe limitleri; borsa
      adres listelerinin güvenilirliği. Ücretsiz veriyle ne kadarının yapılabildiği raporlanır.
- [ ] F13-1 `collectors/onchain.py`: stablecoin arzı ve basım/yakım olayları (saatlik).
- [ ] F13-2 Borsa net akışı: bilinen borsa adreslerine giren/çıkan tutar; adres listesi `config/` altında
      sürümlenir, kaynağı belgelenir. Kapsamın kısmi olduğu arayüzde yazılır.
- [ ] F13-3 Büyük transfer tespiti (eşik config'de), 1 saatlik kovalar.
- [ ] F13-4 Tablolar: `stablecoin_supply`, `exchange_flows`, `large_transfers`.
- [ ] F13-5 `FeatureStore` + kesme (blok onay gecikmesi dahil) + truncation testi.
- [ ] F13-6 `signals/onchain.py`, ağırlık 0.05.
- [ ] F13-7 Arayüz: Coin detayda zincir üstü paneli; kapsam uyarısı görünür.
- [ ] F13-8 Kalibrasyon modül satırı + ispat sayacı.

Bitti sayılır
- Stablecoin arzı 30 gün geriye dolu ve bilinen bir basım olayı doğrulanmış.
- Borsa net akışının kapsam sınırı ölçülmüş ve arayüzde yazılı.

---

## Faz 14 — Likidasyon haritası

**Neden:** Kaldıraçlı pozisyonların nerede tasfiye olacağı, fiyatın nereye çekileceğine dair konum
bilgisidir. **Fiyat dönüşümü değildir** (CLAUDE.md §14.1): açık pozisyon, funding ve kaldıraç
dağılımından türetilir.

**Kaynak:** Faz 3'te zaten toplanan veriler (OI, funding, long/short oranı, gerçekleşen likidasyonlar).
Yeni dış kaynak yok; bu yüzden erişim doğrulaması yerine **model doğrulaması** yapılır.

Görevler
- [ ] F14-0 Yöntem doğrulaması: tahmin edilen likidasyon kümeleri ile **gerçekleşen** `forceOrder`
      olayları karşılaştırılır (Faz 3'ten beri arşivleniyor). Tahmin gücü yoksa faz burada durur ve
      raporlanır.
- [ ] F14-1 `features/liquidation_map.py`: OI + funding + varsayılan kaldıraç dağılımından fiyat
      seviyesi başına yaklaşık tasfiye yoğunluğu.
- [ ] F14-2 Feature'lar: en yakın kümeye uzaklık (ATR cinsinden), küme büyüklüğü, yukarı/aşağı küme
      asimetrisi.
- [ ] F14-3 Doğrulama metriği: gerçekleşen likidasyon dalgalarının tahmin edilen kümelere düşme oranı;
      rastgele seviyelere göre üstünlük testi.
- [ ] F14-4 `signals/orderflow.py` içine bileşen olarak eklenir (yeni modül değil; mevcut modülün yeni
      bileşeni) ve bileşen bazlı ayrı ölçülür.
- [ ] F14-5 Arayüz: Coin detayda mum grafiği üzerine likidasyon yoğunluk katmanı.

Bitti sayılır
- F14-0 doğrulaması pozitif: kümeler rastgeleden anlamlı ölçüde iyi.
- Bileşen ayrı ölçülüyor ve order flow modülünün isabetini düşürmüyor.

---

## Faz 15 — Zaman ve rejim

**Neden:** Piyasa davranışı saate, güne ve seans yapısına göre değişir; korelasyon rejimi kırıldığında
makro modülün anlamı değişir.

**Uyarı (CLAUDE.md §14.1):** Zaman feature'ları çoklu karşılaştırma tuzağına açıktır. **Feature listesi
bu fazda sabitlenir ve sonradan genişletilmez.** Liste: haftanın günü, günün saati (4 dilim), ay sonu
(son 2 iş günü), opsiyon vadesi günü (Faz 10'dan), CME açılış/kapanış pencereleri.

Görevler
- [ ] F15-0 Feature listesini dondur ve ROADMAP'e yaz. Liste dışına çıkmak yeni bir faz gerektirir.
- [ ] F15-1 `features/time_features.py` + birim testleri (saat dilimi ve tatil sınırları dahil).
- [ ] F15-2 `features/regime.py`: BTC-SPX ve BTC-DXY hareketli korelasyon (30 ve 90 gün),
      korelasyon kırılması tespiti (pencereler arası fark eşiği).
- [ ] F15-3 `FeatureStore` + truncation testi.
- [ ] F15-4 `signals/macro.py` içine rejim bileşeni; zaman feature'ları ensemble'a **modül olarak değil**,
      güven düzeltmesi olarak girer (ör. düşük likidite saatlerinde güven düşer). Gerekçesi: zaman
      başlı başına yön sinyali değildir.
- [ ] F15-5 Arayüz: Kalibrasyon ekranında saat/gün bazlı isabet kırılımı (yalnız gözlem amaçlı).
- [ ] F15-6 Korelasyon kırılması uyarı kuralı (Faz 6 uyarı motoruna eklenir).

Bitti sayılır
- Zaman feature'ları güveni etkiliyor, yönü doğrudan etkilemiyor.
- Korelasyon kırılması bilinen bir geçmiş olayda (ör. 2025 makro şoku) doğrulanmış.

---

## Faz 16 — Haber derinleştirme

**Neden:** Faz 4 haberi sınıflandırır; bu faz haberin **güvenilirliğini ve yayılma hızını** ölçer.
Aynı haber tek kaynakta mı kaldı, yoksa 10 dakikada 6 kaynağa mı düştü — bu bilgi haber metninde yoktur.

**Beklenen kaynak:** SEC EDGAR full-text search API (ücretsiz, anahtarsız, `User-Agent` zorunlu),
resmî kaynaklar (Fed, CFTC, borsa duyuru sayfaları), mevcut RSS akışları (yayılma hızı için).

Görevler
- [ ] F16-0 Erişim doğrulaması: EDGAR API limitleri ve kullanım koşulları; resmî kaynakların makine
      okunur bir akışı var mı.
- [ ] F16-1 Kaynak güvenilirlik ağırlığı: her kaynağın geçmiş `news_outcomes` isabetinden öğrenilen
      katsayı; en az 50 haber biriktikten sonra devreye girer, öncesinde 1.0.
- [ ] F16-2 Yayılma hızı: bir `dedup_group` kaç kaynağa kaç dakikada düştü; hız ve genişlik feature'ı.
- [ ] F16-3 `collectors/edgar.py`: ilgili şirket ve fon başvuruları (ETF dosyalamaları dahil).
- [ ] F16-4 Benzer geçmiş olay arşivi: kategori + etki bazında geçmiş olayların sonraki 1s/4s/24s
      hareket dağılımı; Kademe 2 promptuna **veri olarak** verilir (metin olarak değil).
- [ ] F16-5 `signals/news.py` genişletme: güvenilirlik ve yayılma bileşenleri; bileşen bazlı ölçüm.
- [ ] F16-6 Arayüz: Haber kartında kaynak güvenilirliği ve yayılma göstergesi.

Bitti sayılır
- Yayılma hızı 30 gün ölçülmüş; hızlı yayılan haberlerin etkisi yavaşlardan ayrışıyor mu, veriyle yazılı.
- Kaynak ağırlıkları kalibrasyon ekranında görünüyor.

---

## Faz 17 — Modül tasfiyesi

**Neden:** Sistem büyüdükçe işe yaramayan modüller birikir. Tasfiye olmazsa gürültü ağırlık taşır.

Görevler
- [ ] F17-1 `tracking/module_audit.py`: 200 çözümlenmiş tahmin eşiğini geçmiş her modül için isabet +
      Wilson CI, modül Brier, referans tahmincilerle karşılaştırma.
- [ ] F17-2 Tasfiye kuralı: modülün isabet CI alt sınırı her iki referansın isabetini geçemiyorsa
      **ağırlık sıfırlama önerisi** üretilir (`weight_proposals` tablosuna, K3 ile aynı akış).
- [ ] F17-3 Haftalık rapora "tasfiye adayları" bölümü; her aday için kaç tahminde nasıl performans.
- [ ] F17-4 Arayüz: Kalibrasyon ekranında **"İşe yaramayan modüller"** bölümü — modül, n, isabet + CI,
      referans farkı, öneri, "Onayla / Reddet" düğmeleri.
- [ ] F17-5 Sıfırlanan modül durumu: kod kalır, ağırlık 0, `prediction_signals`'a yazmaya **devam eder**
      (ölçüm sürer). Arayüzde "ölçülüyor, kullanılmıyor" etiketi.
- [ ] F17-6 Yeniden ispat kuralı: sıfırlanan modülün veri kaynağı veya hesabı değişirse sayaç sıfırlanır
      ve 200 tahminlik süreç yeniden başlar. Otomatik geri dönüş yok.
- [ ] F17-7 Testler: sentetik "bilgili modül" ve "rastgele modül" ile tasfiye kararının doğruluğu.

Bitti sayılır
- En az bir modül için tasfiye önerisi üretilmiş ve arayüzde görünmüş (öneri doğru olmasa bile akış çalışıyor).
- Sıfırlanan modül ölçülmeye devam ediyor.

---

## Sonraya bırakılanlar (hiçbir fazda yapılmaz; ayrı karar gerektirir)

- Message Batches API ile toplu haber sınıflandırma (`llm/batch.py`) — geçmiş haber arşivi olursa.
- Kademe 2 için daha güçlü model denemesi — yalnızca Haiku vs Sonnet ölçümü (K20) Sonnet'in değerini gösterdikten sonra.
- Ücretli geçmiş türev verisi (OI/likidasyon) ile order flow backtest'i — bütçe kararı.
- Ücretli zincir üstü ve kurumsal akış kaynakları (Glassnode, CryptoQuant, CME DataMine) — Faz 12 ve 13
  ücretsiz uçlarla yetersiz kalırsa kullanıcıya seçenek olarak sunulur.
- Otomatik ağırlık değişikliği — K3 gereği hiçbir fazda yapılmaz; sistem yalnızca öneri üretir.
- Fiyat serisinden türetilen yeni gösterge eklemek — CLAUDE.md §14.1 gereği ilke olarak reddedilir.
- TimescaleDB geçişi (§20) — SQLite darboğaz olursa.
- Yeni coin için LLM şema `Literal` güncellemesinin otomasyonu.
- Açık tema.
- Kimlik doğrulama — yalnızca internete açılacaksa, reverse proxy katmanında.
