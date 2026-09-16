# CLAUDE.md — MarketPulse

Bu depoda çalışan her Claude Code oturumu önce bu dosyayı okur. Tasarım ayrıntıları `ARCHITECTURE.md`,
iş planı `ROADMAP.md` içindedir. Üçü çelişirse öncelik sırası: CLAUDE.md > ARCHITECTURE.md > ROADMAP.md;
çelişki fark edildiğinde aynı commit içinde giderilir.

## 1. Proje

**MarketPulse**, seçili kripto paralar (başlangıç: BTC, ETH, SOL) için **30dk / 1s / 4s / 24s** ufuklarında
**yön olasılığı** ve piyasa durumu raporu üreten kişisel bir analiz sistemidir. Python backend
(asyncio engine + FastAPI) ve React frontend'den oluşur. Tek kullanıcı, yerel ağda çalışır.

Sistemin işi: veri toplamak, sinyal modüllerini çalıştırmak, `olasılık + beklenen aralık + güven + gerekçe +
karşıt argüman` üretmek, her tahmini kaydetmek, ufuk dolunca gerçek sonuçla karşılaştırmak ve hangi modülün
gerçekten işe yaradığını ölçmek.

Kararı kullanıcı verir. Sistem şunu der: *"Şu veriler şunu gösteriyor, olasılık şu, güven seviyem şu,
şu senaryoda yanılırım."*

### Kesin yasaklar

- **Emir iletme yok.** Borsa hesabına bağlanılmaz, işlem yetkili API anahtarı depoda ve config'de bulunmaz.
  Binance'e yalnızca public endpoint'lerle erişilir; imzalı istek kodu yazılmaz.
- **Yönlendirici dil yok.** "al", "sat", "kesin", "garanti", "kaçırma", "fırsat", "mutlaka" ve benzerleri.
  Yasak kelime listesi `backend/src/marketpulse/reporting/banned_words.py` içindedir; rapor şablonlarını ve
  arayüz metinlerini tarayan bir test bunu zorlar.
- **Telegram, e-posta, push servisi yok.** Tek çıktı kanalı: web arayüzü + tarayıcı Notification API.
- **Uydurma feature yok.** Az ve doğrulanmış feature, çok ve gürültülü olandan iyidir. Yeni bir gösterge veya
  alt sinyal eklemek için dört şart: (1) ROADMAP'te görev olarak yazılmış, (2) unit testi var,
  (3) look-ahead testi geçiyor, (4) kalibrasyon ekranında ayrı ölçülebiliyor. Faz 10'dan sonraki
  genişletmeler ayrıca §14'teki ilkeye uyar: **yeni indikatör değil, yeni veri kaynağı.**
- **Secret koda gömülmez.** Anahtarlar yalnızca `.env` içinde; `.env` git'e girmez; loglara yazılmaz.

## 2. Kullanıcı ve iletişim

- Kullanıcı yazılımcı değil. Oturum özetleri sade Türkçe yazılır; teknik terim ilk geçtiğinde tek cümleyle
  açıklanır.
- Karar gerektiren konuda varsayım yapılmaz, sorulur. Rutin teknik tercihler Claude tarafından verilir ve
  özette "şunu şöyle seçtim, sebebi şu" diye belirtilir.
- Her faz ve her oturum sonunda sade Türkçe özet, dört başlık: **ne yaptın, ne çalışıyor, ne çalışmıyor,
  benden ne gerekiyor.** En fazla 15 satır.
- Kullanıcının elle yapması gereken adımlar tıklama seviyesinde anlatılır: hangi dosya, hangi satır, hangi
  komut, hangi buton.
- "Muhtemelen çalışır" denmez. Çalıştırılır, görülür, sonra söylenir. Bu ortamda çalıştırılamayan şey
  (örneğin Docker daemon yoksa) "burada çalıştıramadım, sende şu komutla denenecek" diye yazılır.
- Çalışmayan şey "çalışıyor" diye raporlanmaz. Test edilemeyen şey "test edilmedi" diye işaretlenir.

## 3. Verilmiş kararlar

| # | Konu | Karar | Gerekçe |
|---|---|---|---|
| K1 | Hedef tanımı | İkili: ufuk sonu kapanış > tahmin anı fiyatı ise "yukarı". Çıktı P(yukarı). | Brier ve kalibrasyon en temiz. "Yatay" durumu %50'ye yakın olasılık + düşük güven olarak görünür. Beklenen aralık ayrı çıktı. |
| K2 | Tahmin sıklığı | 30dk ufku her 15 dk, 1s her 30 dk, 4s her saat, 24s her 4 saat. | Sık rapor. Örtüşmesiz alt küme metriklerde ayrıca hesaplanır. |
| K3 | Ağırlık güncelleme | Sistem öneri üretir, kullanıcı arayüzden onaylar. Otomatik değişiklik yok. | Kararı kullanıcı verir. Az örnekle otomatik güncelleme gürültüye uyar. |
| K4 | Rapor metni | Deterministik şablon. LLM yalnızca haber sınıflandırmada. | Test edilebilir, ucuz, sayıyla çelişen metin riski yok. |
| K5 | Backtest kapsamı | Teknik + makro + funding + F&G backtest edilir. Order flow'un kalanı ve haber yalnızca ileriye dönük ölçülür. | Binance OI/LS geçmişi 30 gün; likidasyon, order book ve RSS geçmişi yok. Kendi arşiv ilk günden birikir. |
| K6 | Ekonomik takvim | Statik `calendar.yaml` (FOMC, CPI, NFP), yılda bir elle güncellenir. | Ücretsiz temiz API yok, scraping kırılgan. |
| K7 | LLM, iki kademe | Kademe 1 her haber: Claude Haiku 4.5 (`claude-haiku-4-5`) → kategori, ilgili coinler, kaba ton, önem 0–1. Kademe 2 önem > 0.6 (config): Claude Sonnet 5 (`claude-sonnet-5`) → derin analiz (fiyatlanmış mı, gerçek mi söylenti mi, ikinci derece etkiler, benzer geçmiş olaylar) → etki, güven, ufuk, gerekçe. Günlük tavan 3 USD (config). Aşımda önce Kademe 2 kapanır, Haiku devam eder; ikisi de kapanırsa haber modülü "veri yok", ensemble ağırlıkları yeniden dağıtır. | Ucuz eleme + pahalı derinlik yalnızca önemli haberde. Sonnet'in değeri veriyle ölçülür (K20). |
| K8 | Haber kaynağı | RSS ile başla: CoinDesk, The Block, Cointelegraph, Decrypt. CryptoPanic anahtar varsa opsiyonel. | Ücretsiz plan kısıtlı. |
| K9 | Çalışma ortamı | 7/24 küçük Linux makine (ev sunucusu veya VPS), Docker. Kesinti toleranslı. | WebSocket boşluklarında ilgili modüller "veri yok" der; sistem durmaz. Binance API ABD IP'lerini engeller. |
| K10 | Arayüz | Web: FastAPI REST + WebSocket; Vite + React + TypeScript + Tailwind. Telegram yok. | Kullanıcı kararı. |
| K11 | Erişim | Yerel ağ / Tailscale, kimlik doğrulama yok. | Tek kullanıcı. İnternete açılacaksa reverse proxy + auth eklenir, uygulamaya değil. |
| K12 | Dil | Dokümanlar ve arayüz metni Türkçe. Kod, identifier, commit mesajı İngilizce. | |
| K13 | Göstergeler | Kendi implementasyonumuz (numpy/pandas). pandas-ta ve TA-Lib kullanılmaz. | Tam test edilebilir, look-ahead denetimi kolay, derleme derdi yok. |
| K14 | Paket adı | `marketpulse` | |
| K15 | Zaman | DB'de UTC. Arayüzde Europe/Istanbul. | |
| K16 | Fiyat referansı | Gerçek sonuç Binance **spot** 1 dk kapanışından. Türev metrikleri USDT-M perpetual'dan. | |
| K17 | Depolama | SQLite (WAL modu), SQLAlchemy Core + Alembic. TimescaleDB'ye geçilebilir repository soyutlaması. | |
| K18 | Süreçler | Üç compose servisi: `engine` (tek yazıcı), `api` (okuyucu + WS), `frontend` (nginx). Redis/Kafka yok; `events_outbox` tablosu. | Tek kullanıcı için yeterli, çökme izolasyonu var. |
| K19 | Olasılık sınırı | Kalibrasyon kanıtlanana kadar P(yukarı) [0.10, 0.90] aralığına kırpılır. | Aşırı güvenli çıktı üretmemek için. |
| K20 | Haber kademe ölçümü | Her haber için geçtiği kademe ve yayın sonrası 1s/4s/24s fiyat hareketi kaydedilir. Kalibrasyon ekranında "Haiku isabeti vs Sonnet isabeti" karşılaştırması. | Sonnet'in parasını hak edip etmediği veriyle görülür. |
| K21 | Saklama | Klines tüm zaman dilimlerinde kalıcı. Order flow 1 dk özetleri 90 gün, haberler 180 gün. Ham depth saklanmaz. | Kullanıcı kararı. 1 dk mum 3 sembol için yılda yaklaşık 200 MB. |
| K22 | Veri durumu şeridi | Her ekranın üstünde: hangi collector çalışıyor, son güncelleme ne zaman, hangisi kopuk. | Kullanıcı kararı; "veri yok" durumları görünür olsun. |
| K23 | Maliyet | Ayrı `/costs` endpoint'i ve Maliyet ekranı: günlük/aylık API harcaması, kademe kırılımı. Ayarlar ekranında bütçe tavanı. | Kullanıcı kararı. |
| K24 | Süreç adı | Veri toplayan ve tahmin üreten süreç `engine` (`python -m marketpulse.engine`, compose servisi `engine`). | Kullanıcı spesifikasyonu: "engine + api + frontend". |
| K25 | Genişletme ilkesi | Faz 10'dan itibaren sisteme **yeni indikatör değil, yeni veri kaynağı** eklenir. Aynı fiyat serisinin başka bir dönüşümü yeni bilgi getirmez, yalnızca aşırı uyum (overfitting) riski getirir. Ayrıntı §14. | Kullanıcı kararı. Fiyattan türetilen her yeni gösterge aynı gürültüyü yeniden paketler; bilgi ancak dışarıdan gelir. |
| K26 | Modül ispat eşiği | Her yeni sinyal modülü, canlıda **en az 200 çözümlenmiş tahmin** boyunca iki referans tahminciyi de yenmek zorundadır. Yenemezse sistem ağırlık sıfırlama önerir, kullanıcı onaylar (K3 ile aynı yol). | Bir modülün işe yaradığı fikirle değil ölçümle belirlenir. Ölçüm penceresi yeterince uzun olmazsa gürültü "başarı" gibi görünür. |

Yeni karar alındığında tabloya satır eklenir. Karar değişirse satır güncellenir, eski satır silinmez;
"iptal edildi: K#, tarih, sebep" notu düşülür.

## 4. Mimari özeti

Üç süreç, tek `docker compose up`:

- **engine** — collector'lar (REST + WebSocket), iki kademeli haber sınıflandırma, feature hesaplama, sinyal
  modülleri, ensemble, tahmin defteri, sonuç çözümleyici, haber sonuç ölçümü, metrikler, uyarı motoru.
  DB'nin tek düzenli yazıcısı.
- **api** — FastAPI. REST + WebSocket. DB'yi okur; `events_outbox` tablosunu izleyip WS istemcilerine
  yayınlar; canlı fiyatı Binance miniTicker akışından relay eder. Yalnızca ayarları, uyarı onaylarını ve
  ağırlık önerisi kararlarını yazar.
- **frontend** — Vite build çıktısı, nginx ile servis edilir; `/api` ve `/ws` istekleri api'ye proxy'lenir.

Veri akışı:

```
collector → storage → FeatureStore.snapshot(symbol, as_of) → sinyal modülleri (5) → ensemble
        → predictions (+ prediction_signals) → [ufuk dolunca] resolver → prediction_outcomes
        → metrics → weekly_reports → weight_proposals → [kullanıcı onayı] → weights
```

Ayrıntı: `ARCHITECTURE.md`.

## 5. Depo yapısı

```
.
├── CLAUDE.md  ARCHITECTURE.md  ROADMAP.md
├── Makefile                      # dev / dev-stop / up / down / test / lint / typecheck / check / migrate / backfill / backtest / gen-types
├── docker-compose.yml
├── .env.example
├── data/                         # SQLite dosyası (git'e girmez)
├── backend/
│   ├── pyproject.toml            # uv, Python 3.12
│   ├── Dockerfile
│   ├── alembic/                  # migration'lar
│   ├── config/
│   │   ├── calendar.yaml         # FOMC / CPI / NFP tarihleri
│   │   └── weights.default.yaml  # ufuk bazlı varsayılan modül ağırlıkları
│   ├── src/marketpulse/
│   │   ├── config.py             # pydantic-settings, .env
│   │   ├── core/                 # tipler (Horizon, Symbol), Clock, zaman yardımcıları, hatalar
│   │   ├── storage/              # tablolar, repository arayüzü, sqlite implementasyonu, outbox
│   │   ├── collectors/           # binance_client, binance_futures, futures, klines(_ws), orderflow_ws/_agg, rss, cryptopanic, feargreed, macro, calendar
│   │   ├── features/             # indicators.py, levels.py (S/R + hacim profili), feature_store.py
│   │   ├── signals/              # base.py, technical.py, orderflow.py, news.py, macro.py, sentiment.py
│   │   ├── ensemble/             # combine.py, confidence.py, veto.py, expected_range.py, conflict.py
│   │   ├── reporting/            # templates.py, counter_argument.py, build.py, banned_words.py
│   │   ├── tracking/             # ledger.py, resolver.py, metrics.py, weekly.py, weight_proposals.py, news_outcomes.py
│   │   ├── alerts/               # rules.py, evaluator.py
│   │   ├── llm/                  # client.py, tier1.py (Haiku), tier2.py (Sonnet), router.py, budget.py, dedup.py
│   │   ├── backtest/             # engine.py, report.py, cli.py
│   │   ├── devtools/             # runner.py (make dev), procs.py — geliştirme aracı, üretim yolunda değil
│   │   ├── engine/               # jobs.py, supervisor.py, ratelimit.py, main.py  → süreç: python -m marketpulse.engine
│   │   └── api/                  # app.py, routers/ (predictions, market, signals, news, calibration, alerts, config, costs, health), ws.py, live_relay.py, schemas/
│   └── tests/
│       ├── unit/                 # modül başına
│       ├── lookahead/            # look-ahead bias testleri
│       ├── integration/          # DB + engine + API uçtan uca (ağ yok)
│       └── fixtures/             # sentetik seriler, kaydedilmiş API yanıtları
└── frontend/
    ├── package.json  vite.config.ts  tsconfig*.json  eslint.config.js  .prettierrc
    ├── openapi.json              # make gen-types üretir; types.gen.ts'nin kaynağı
    ├── Dockerfile  nginx.conf
    └── src/
        ├── main.tsx
        ├── app/                  # router, providers, layout (Shell, Sidebar, Topbar, DataStatusStrip, StatusBar)
        ├── api/                  # client.ts, ws.ts, useLive.ts, types.gen.ts (OpenAPI'den üretilir), queries/
        ├── store/                # zustand: ui.ts (WS durumu, uyarı sayacı, tercihler)
        ├── components/ui/        # Card, Badge, Button, Table, Tabs, Drawer, Tooltip, Skeleton, Kbd
        ├── components/charts/    # CandleChart (lightweight-charts), LineChart, BarChart, CalibrationCurve, Sparkline
        ├── components/domain/    # ProbabilityGauge, ConfidenceBadge, ScoreBar, ModuleBreakdown, RationaleList, NewsCard, AlertBell, DataHealthDot
        ├── features/             # dashboard/, coin/, news/, predictions/, calibration/, settings/, costs/
        ├── lib/                  # format.ts, time.ts, notifications.ts, sound.ts
        ├── i18n/tr.ts            # tüm arayüz metinleri
        └── styles/               # tokens.css (renk/boşluk/font değişkenleri), globals.css
```

## 6. Python kod standartları

- Python 3.12. Bağımlılık yönetimi `uv` (`uv sync`, `uv run`). `requirements.txt` yok.
- **Tip ipuçları zorunlu.** `mypy --strict` temiz geçer. `Any` yalnızca dış kütüphane sınırında ve
  `# type: ignore[kod]` gerekçeli.
- `ruff` hem lint hem format. Satır uzunluğu 100. Import sırası ruff'a bırakılır.
- **asyncio** her yerde: collector'lar, engine, API. Bloklayan iş (pandas hesapları, yfinance, LLM SDK
  senkron çağrısı yerine `AsyncAnthropic`) `asyncio.to_thread` ile ya da async istemciyle çalışır.
  `time.sleep` yasak.
- `datetime` her zaman timezone-aware UTC. Naive datetime alan fonksiyon `ValueError` fırlatır.
  `core/time.py` dışında `datetime.now()` çağrılmaz; `Clock` protokolü kullanılır (testte `FakeClock`).
- Loglama `loguru`. `print` yasak. Log satırları yapılandırılmış alan taşır: `symbol`, `horizon`, `job`,
  `collector`.
- Config `pydantic-settings` ile `.env`'den okunur. Koddan `os.environ` okunmaz.
- Veri modelleri `pydantic` v2 (`BaseModel`, `frozen=True` mümkünse). DB satırları SQLAlchemy Core
  tabloları; ORM sınıfları yok.
- **Collector'lar istisna yükseltmez.** Hata → `collector_health` güncellenir, log, backoff, devam.
  Engine asla bir collector yüzünden düşmez.
- **Sinyal modülleri saf fonksiyondur.** Girdi `FeatureSnapshot`, çıktı `SignalResult`. Ağ, DB, saat
  erişimi yok. Aynı girdi → aynı çıktı.
- Göstergeler `features/indicators.py` içinde numpy/pandas ile yazılır; her biri referans değerle test
  edilir; hepsi nedenseldir (bkz. §9).
- Fiyat ve oranlar `float`; para birimi hesabı yapılmadığı için `Decimal` gerekmez.
- Dosya 400 satırı geçiyorsa bölünür. Fonksiyon 60 satırı geçiyorsa bölünür.
- Docstring: modül başında ne yaptığı; fonksiyonlarda sözleşme (girdi, çıktı, birim, aralık). Yorum "neden"
  anlatır, "ne" yaptığını değil.

## 7. Frontend kod standartları

- TypeScript `strict: true`. `any` yasak. Dış veri `api/types.gen.ts` tipleriyle gelir.
- API tipleri `openapi-typescript` ile backend OpenAPI şemasından üretilir (`make gen-types`). Elle
  düzenlenmez; değişiklik backend şemasında yapılır.
- Fonksiyon bileşenleri, named export. Bir dosya bir bileşen (+ yalnızca onun kullandığı küçük parçalar).
- Sunucu verisi TanStack Query ile. WebSocket mesajları query cache'ini günceller; bileşenler WS'e doğrudan
  bağlanmaz. Global UI durumu (uyarı sayacı, bildirim tercihleri, seçili sembol) zustand.
- Stil yalnızca Tailwind sınıfları + `styles/tokens.css` içindeki CSS değişkenleri. Bileşen içinde hex renk,
  piksel büyüklüğü veya font adı yazılmaz; hepsi token. Kullanıcı tasarımı sonra `tokens.css` ve
  `components/ui` üzerinden değiştirecek; `features/*` dosyalarına dokunmadan görünüm değişebilmeli.
- Koyu tema varsayılan. Açık tema token seti tanımlı olur ama öncelik değil.
- Tüm arayüz metinleri `i18n/tr.ts` içinde. JSX içinde çıplak Türkçe string yok.
- Sayılar `tabular-nums` mono fontla. Yüzde, fiyat, zaman formatları yalnızca `lib/format.ts` ve
  `lib/time.ts` üzerinden.
- Grafik: mum grafikleri `lightweight-charts`, metrik grafikleri `Recharts`. Üçüncü bir grafik kütüphanesi
  eklenmez.
- Katmanlar: `features/*` sayfaları `components/domain` ve `components/ui` parçalarını birleştirir. Sayfa
  bileşenleri fetch yapmaz; `api/queries` hook'larını kullanır. `components/ui` proje alanına özgü hiçbir şey
  bilmez.
- Test: `vitest` + Testing Library. `lib/` ve `components/domain` için birim testleri, her sayfa için
  render smoke testi.
- Görünüm: veri yoğun terminal. Sıkı satır aralığı, küçük ama okunaklı yazı, renk yalnızca anlam taşıdığında
  (yukarı/aşağı/nötr/uyarı). Süs animasyonu yok.

## 8. Test kuralları

- `pytest` + `pytest-asyncio`. Testlerde ağ yok: HTTP `respx` ile mock'lanır, WebSocket sahte akışla
  beslenir. Ağa çıkan test hata sayılır.
- Her sinyal modülü için unit test: (a) sentetik seride beklenen işaret, (b) çıktı aralığı -1..+1,
  (c) veri eksikken davranış (`coverage` düşer, çökme yok), (d) gerekçe metninde yasak kelime yok.
- Her gösterge için referans değer testi (elle hesaplanmış küçük seri).
- Metrikler (Brier, Brier skill score, kalibrasyon eğrisi, isabet) elle hesaplanmış örneklerle test edilir.
- Look-ahead test seti `tests/lookahead/` her `make check`te koşar (bkz. §9).
- Zaman `FakeClock` ve `time-machine` ile kontrol edilir. Testte gerçek saat yok.
- `hypothesis` ile nedensellik property testleri (gelecek değeri değiştir, geçmiş çıktı değişmesin).
- Kapsam hedefi: `signals/`, `features/`, `ensemble/`, `tracking/` için %90+; geri kalan için %70+.

## 9. Look-ahead bias kuralları (kritik)

1. Tüm feature hesapları `FeatureStore.snapshot(symbol, as_of)` üzerinden yapılır. Modüller ham DB'ye
   erişmez.
2. Snapshot yalnızca `as_of` anında **kapanmış** mumları içerir: `open_time + interval <= as_of`.
   Oluşmakta olan mum asla dahil değildir.
3. Zaman serileri `ts <= as_of`. Haberler `published_at + MP_NEWS_INGEST_LATENCY_SEC <= as_of` (varsayılan
   5 dk). Fear & Greed günlük değeri ilgili gün `00:10 UTC` sonrasında kullanılabilir. Makro günlük mum
   ertesi gün `00:00 UTC` sonrasında kullanılabilir.
4. Gösterge fonksiyonları nedenseldir: `çıktı[i]` yalnızca `girdi[:i+1]`'e bağlıdır. Merkezlenmiş pencere,
   `shift(-n)`, ileri doldurma sonrası geri bakış yasaktır.
5. Backtest ve canlı sistem **aynı** kod yolunu kullanır. "Backtest için ayrı feature hesabı" yoktur.
6. Resolver yalnızca `target_at` anında kapanmış olan mumu kullanır.
7. Testler: (a) **kesme değişmezliği** — `snapshot(as_of)` tam DB ile ve DB `as_of`'ta kesilerek alındığında
   birebir eşit; (b) **gelecek perturbasyonu** — girdinin `as_of` sonrası değerleri rastgele değiştirilince
   çıktı değişmez; (c) **resolver sınırı** — resolver hiçbir zaman `target_at` sonrası mum okumaz;
   (d) **backtest eşdeğerliği** — aynı `as_of` için backtest motoru ve canlı tahmin işi aynı `SignalResult`
   üretir.

## 10. Komutlar

| Komut | Ne yapar |
|---|---|
| `make install` | `uv sync` (backend) + `npm install` (frontend) |
| `make dev` | api (auto-reload), engine ve Vite dev server'ını **bağımsız süreçler** olarak başlatır; çöken süreç kendiliğinden yeniden başlar, diğerleri ayakta kalır; `.env` şart |
| `make dev-stop` | Arka planda kalmış geliştirme süreçlerini durdurur |
| `make up` / `make down` | `docker compose up -d --build` / `docker compose down` |
| `make logs` | compose loglarını takip eder |
| `make test` | backend pytest + frontend vitest (`make test-backend`, `make test-frontend` ayrı ayrı) |
| `make lint` | ruff check + ruff format --check + eslint |
| `make typecheck` | mypy --strict + tsc --noEmit |
| `make check` | lint + typecheck + test. **Commit öncesi zorunlu.** |
| `make migrate` | alembic upgrade head |
| `make backfill` | geçmiş klines / funding / F&G / makro verisini çeker |
| `make backtest ARGS="--symbol BTCUSDT --from 2025-01-01 --to 2025-06-30"` | backtest motoru |
| `make gen-types` | OpenAPI → `frontend/src/api/types.gen.ts` |

## 11. Git kuralları

- Çalışma dalı `claude/` ön ekli feature dalları. `main`'e doğrudan push yok.
- Commit mesajı İngilizce, Conventional Commits: `feat(signals): add funding deviation score`,
  `fix(resolver): use closed candle at target_at`, `test(lookahead): add truncation invariance`,
  `docs: ...`, `chore: ...`.
- Bir commit bir iş. ROADMAP görev kimliği gövdede: `Refs: F2-3`.
- `make check` geçmeden commit yok.
- Commit'e girmez: `.env`, `data/`, `node_modules/`, `.venv/`, `dist/`, `__pycache__/`.
- Model adı veya oturum kimliği kod, doküman ve commit gövdesine yazılmaz.

## 12. Claude için çalışma protokolü

1. Oturum başında `ROADMAP.md`'deki aktif fazı bul; `[ ]` görevleri sırayla al. Faz atlanmaz. Faz içine
   ROADMAP'te olmayan iş eklenmez; gerekiyorsa önce ROADMAP'e görev olarak yazılır ve kullanıcıya söylenir.
2. Her görev: kod + test + `make check` + commit + ROADMAP'te `[x]`.
3. Kod yazmadan önce ilgili ARCHITECTURE bölümü okunur. Sapma gerekiyorsa ARCHITECTURE aynı commit'te
   güncellenir.
4. Yeni bağımlılık eklemeden önce üç soru: gerçekten gerekli mi, bakımı yapılıyor mu, lisansı uygun mu.
   Eklenirse özette belirtilir.
5. Dış API davranışı belgelenenden farklı çıkarsa (limit, alan adı, şema) ARCHITECTURE'daki ilgili tablo
   güncellenir.
6. Bir feature'ın işe yaramadığı kalibrasyon verisiyle görülürse önce kullanıcıya raporlanır; silme veya
   ağırlık değişikliği kullanıcı kararıdır.
7. Oturum sonunda özet (§2) ve dala push.

## 13. Güvenlik ve gizlilik

- Secret'lar yalnızca `.env`: `ANTHROPIC_API_KEY`, opsiyonel `CRYPTOPANIC_TOKEN`. Loglara ve hata
  mesajlarına anahtar yazılmaz.
- Binance'e yalnızca public endpoint. İmzalı istek kodu depoda bulunmaz.
- Dashboard yerel ağda. CORS yalnızca `MP_CORS_ORIGINS` içindeki origin'lere açık.
- LLM'e giden haber metni dış içeriktir. Sınıflandırıcı sistem promptu haber içindeki talimatları yok sayacak
  şekilde yazılır; çıktı şema ile doğrulanır; haber metni hiçbir zaman sistem promptuna eklenmez.
- Arayüz, kullanıcı girdisini (sembol adı, eşik değeri) backend'de doğrular; sembol listesi Binance
  `exchangeInfo` ile kontrol edilir.

## 14. Genişletme ilkesi (Faz 10 ve sonrası)

Faz 1–9 temel sistemi kurar. Ondan sonraki her faz **tek bir yeni veri kaynağı** ekler. Bu bölüm o
fazların değişmez kurallarıdır; ROADMAP'teki faz tanımları bunun üstüne yazılır.

### 14.1 Yeni indikatör değil, yeni veri kaynağı

Aynı fiyat serisinin farklı bir dönüşümü (yeni bir hareketli ortalama, yeni bir osilatör, aynı serinin
başka bir penceresi) sisteme bilgi eklemez. Aynı gürültüyü yeniden paketler ve geçmişe uydurma riskini
artırır. Bilgi ancak **fiyatta henüz görünmeyen bir yerden** gelir.

| Meşru genişletme (yeni veri kaynağı) | Meşru olmayan (aynı serinin dönüşümü) |
|---|---|
| Opsiyon zinciri: örtük volatilite, skew, açık pozisyon | Fiyattan hesaplanan yeni bir volatilite göstergesi |
| Başka borsadaki fiyat ve derinlik | Aynı borsanın fiyatının başka bir zaman diliminde EMA'sı |
| ETF net akışı, CME açık pozisyonu | RSI'ın 9 yerine 11 periyotlusu |
| Zincir üstü transfer ve stablecoin arzı | MACD'nin farklı parametreleri |
| Haberin kaç kaynağa kaç dakikada düştüğü | Mevcut haber skorunun karekökü |

**Konum (positioning) verisi fiyat dönüşümü değildir.** Açık pozisyon, funding, kaldıraç dağılımı ve
bunlardan türetilen likidasyon kümeleri (Faz 14) piyasa katılımcılarının nerede durduğunu anlatır;
fiyatın kendisinden çıkarılamaz. Bu yüzden ilkeye aykırı değildir.

**Zaman ve takvim feature'ları (Faz 15) sınırlı tutulur.** Bunlar dışarıdan gelir ama örnek sayısı
azdır ve çoklu karşılaştırma tuzağı yüksektir: yeterince çok zaman dilimi denenirse biri her zaman
"anlamlı" çıkar. Faz 15'te feature sayısı baştan sabitlenir ve sonradan genişletilmez.

### 14.2 Her yeni veri kaynağı için ön koşul: erişim doğrulaması

Faz başlamadan **önce** veri kaynağının gerçekten ücretsiz ve erişilebilir olduğu doğrulanır: uç
nokta çağrılır, yanıt biçimi kaydedilir, kullanım koşulları ve hız limiti okunur, geçmiş veri derinliği
ölçülür.

- Erişilemiyorsa (ücretli, anahtar zorunlu, bölge kısıtlı, ağ engeli) **faz atlanır ve kullanıcıya
  raporlanır.** Karar kullanıcınındır: bütçe ayırmak, başka kaynak aramak veya vazgeçmek.
- **Uydurma veri asla kullanılmaz.** Test amaçlı sentetik seri yalnızca `tests/` içinde, gerçek yanıt
  biçimini taklit ederek kullanılır; üretim veritabanına sentetik satır yazılmaz.
- Kaynak zamanla bozulursa (şema değişikliği, kapanan uç nokta) ilgili collector `down` olur, modül
  "veri yok" der ve ensemble ağırlığı diğer modüllere dağıtır. Sistem durmaz.

### 14.3 Her yeni modülün ispat yükümlülüğü (K26)

Yeni bir sinyal modülü eklendiğinde:

1. Ağırlığı **düşük** başlar (varsayılan 0.05), böylece kanıtlanmadan tahminleri sürüklemez.
2. Modül skoru her tahminde `prediction_signals` tablosuna yazılır; kalibrasyon ekranında ayrı ölçülür.
3. **En az 200 çözümlenmiş tahmin** biriktikten sonra değerlendirilir. Ölçüt: modülün isabet oranının
   Wilson güven aralığı alt sınırı, **her iki referans tahmincinin** isabet oranını geçmeli.
4. Geçemezse Faz 17'deki tasfiye akışı devreye girer: sistem ağırlık sıfırlama önerir, kullanıcı onaylar.
   Kod silinmez; ağırlık sıfırlanır ve modül "ölçülüyor ama kullanılmıyor" durumuna geçer.
5. Sıfırlanan bir modül, veri kaynağı veya hesap yöntemi değişirse yeniden 200 tahminlik ispat süresine
   girer. "Bu sefer tutar" gerekçesiyle ağırlık geri verilmez.

### 14.4 Faz sırası bozulmaz

Faz 10 ve sonrası, **Faz 1–9 bitmeden ve temel sistem canlıda ölçülmeden** başlamaz. Gerekçe: bir modülün
işe yarayıp yaramadığı ancak çalışan bir doğruluk takibi varsa söylenebilir. Ölçüm altyapısı olmadan
eklenen her modül inanç meselesidir.
