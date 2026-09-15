# MarketPulse

BTC, ETH ve SOL için **30 dakika / 1 saat / 4 saat / 24 saat** ufuklarında **yön olasılığı** ve piyasa
durumu raporu üreten kişisel analiz sistemi.

Sistem **işlem yapmaz, emir iletmez, "al" ya da "sat" demez.** Şunu der:

> "Şu veriler şunu gösteriyor, yukarı olasılığı şu, güven seviyem şu, şu senaryoda yanılırım."

Kararı siz verirsiniz. Sistem ayrıca **kendi isabetini ölçer**: her tahmini kaydeder, ufuk dolunca gerçek
sonuçla karşılaştırır ve hangi sinyal modülünün gerçekten işe yaradığını rakamla gösterir.

Proje kuralları `CLAUDE.md`, tasarım `ARCHITECTURE.md`, iş planı `ROADMAP.md` dosyalarındadır.

---

## Mac'te sıfırdan kurulum

Bu bölüm yazılımcı olmayan biri için yazıldı. Her adımı sırayla uygulayın. "Terminal" yazan yerlerde
Mac'in **Terminal** uygulamasını kullanacaksınız: `Command (⌘) + Boşluk` tuşlarına basın, `Terminal` yazın,
Enter'a basın. Komutları kopyalayıp Terminal'e yapıştırın ve Enter'a basın.

> Terminal'de bir komut çalışırken ekranda hiçbir şey olmuyormuş gibi görünebilir. Bu normaldir; bittiğinde
> yeni satır gelir. Bir komut hata verirse ekrandaki yazıyı olduğu gibi kopyalayıp saklayın.

### Adım 1 — Homebrew (paket yükleyici)

Homebrew, gereken programları kurmayı kolaylaştırır. Kurulu mu diye bakın:

```bash
brew --version
```

Bir sürüm numarası görüyorsanız (`Homebrew 4.x.x` gibi) bu adımı atlayın. `command not found` diyorsa
şunu çalıştırın:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Kurulum sizden Mac şifrenizi isteyecek. Şifreyi yazarken ekranda hiçbir şey görünmez, bu normaldir; yazıp
Enter'a basın. Kurulum bitince Terminal'in size söylediği iki `echo ...` satırı varsa onları da
çalıştırın, sonra Terminal'i kapatıp yeniden açın.

### Adım 2 — Docker Desktop

En kolay yol budur: tek komutla her şey ayağa kalkar.

```bash
brew install --cask docker
```

Kurulum bitince **Launchpad**'den (veya Uygulamalar klasöründen) **Docker**'ı açın. İlk açılışta izin
isteyebilir, kabul edin. Menü çubuğundaki (ekranın sağ üstü) balina simgesi hareket etmeyi bırakıp sabit
durduğunda Docker hazır demektir. Kontrol:

```bash
docker info
```

Uzun bir metin geliyorsa hazır. `Cannot connect to the Docker daemon` diyorsa Docker Desktop uygulaması
açık değildir, açın ve bir dakika bekleyin.

### Adım 3 — Projeyi bilgisayarınıza indirin

`git` Mac'te genelde kuruludur. Değilse `brew install git` çalıştırın.

```bash
cd ~/Documents
git clone https://github.com/cozcandesign/sketch.git marketpulse
cd marketpulse
git checkout claude/crypto-market-analysis-plan-5qvgxr
```

Artık proje `Belgeler/marketpulse` klasöründe. **Bundan sonraki tüm komutlar bu klasörde çalıştırılır.**
Terminal'i kapatıp açtıysanız önce şunu yazın: `cd ~/Documents/marketpulse`

### Adım 4 — Ayar dosyasını oluşturun

```bash
cp .env.example .env
```

Bu komut hiçbir şey yazmaz, sessizce çalışır. `.env` dosyası kişisel ayarlarınızı tutar ve asla
GitHub'a gönderilmez.

**Şimdilik içini doldurmanız gerekmiyor.** `ANTHROPIC_API_KEY` satırı yalnızca haber analizi için
(Faz 4) gerekli olacak; o zamana kadar boş kalabilir. Doldurmak isterseniz:

```bash
open -e .env
```

Açılan metin düzenleyicide `ANTHROPIC_API_KEY=` satırının sonuna anahtarınızı yapıştırın
(`ANTHROPIC_API_KEY=sk-ant-...` gibi), `⌘ + S` ile kaydedin, pencereyi kapatın.

### Adım 5 — Çalıştırın

```bash
docker compose up --build
```

İlk çalıştırma 3–10 dakika sürer (program parçaları indirilip derleniyor). Terminal'de akan yazılar
normaldir. Şu satırları gördüğünüzde hazırdır:

```
api-1       | api başladı (sürüm 0.1.0)
engine-1    | engine başladı (sürüm 0.1.0, semboller ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
frontend-1  | ... nginx ... start worker processes
```

### Adım 6 — Arayüzü açın

Tarayıcınızda şu adrese gidin:

**http://localhost:3000**

Görmeniz gerekenler: solda 7 ekranlı menü, üstte yeşil noktalı "engine çalışıyor" şeridi, sağ üstte
"WS BAĞLI" rozeti.

### Günlük kullanım

| Ne yapmak istiyorsunuz | Komut |
|---|---|
| Sistemi başlat | `docker compose up -d` (arka planda çalışır, Terminal'i kapatabilirsiniz) |
| Sistemi durdur | `docker compose down` |
| Ne olup bittiğini izle | `docker compose logs -f` (çıkmak için `Control + C`) |
| Yeni sürümü al ve yeniden kur | `git pull && docker compose up -d --build` |

Mac'i kapatıp açtığınızda Docker Desktop açıksa sistem kendi kendine geri gelir (servisler
`restart: unless-stopped` ayarlıdır).

### Bir şey ters giderse

| Belirti | Ne yapmalı |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop uygulaması kapalı. Launchpad'den açın, balina simgesi sabitlenene kadar bekleyin. |
| Tarayıcıda "Bu siteye ulaşılamıyor" | Servisler henüz açılıyor olabilir. Bir dakika bekleyip sayfayı yenileyin. Sürmesi halinde `docker compose logs -f` çıktısını inceleyin. |
| `port is already allocated` | 3000 veya 8000 portunu başka bir program kullanıyor. `docker compose down` deyip tekrar deneyin. |
| Üstteki şeritte "engine kopuk" yazıyor | `docker compose logs engine` çıktısına bakın; son satırları kopyalayıp saklayın. |
| Her şeyi sıfırlamak istiyorum | `docker compose down` sonra `rm -rf data/marketpulse.db*` (biriken tüm veriyi siler, geri alınamaz) |

---

## Geliştirme (kod üzerinde çalışmak için)

Docker olmadan, kaynak koddan çalıştırma. Gerekenler: Python 3.12, [uv](https://docs.astral.sh/uv/),
Node.js 22.

```bash
brew install uv node
make install     # bağımlılıkları kurar
make dev         # api + engine + arayüz, hepsi birlikte
```

`make dev` de arayüzü **http://localhost:3000** adresinde açar. Durdurmak için `Control + C`.
Eksik bağımlılık varsa `make dev` bunları kendisi kurar.

| Komut | Ne yapar |
|---|---|
| `make check` | Tüm kontroller: stil, tip, testler. Kod değişikliğinden sonra bu yeşil olmalı. |
| `make test` | Sadece testler |
| `make migrate` | Veritabanı şemasını günceller |
| `make gen-types` | Arayüzün kullandığı API tiplerini yeniden üretir |
| `make help` | Komut listesi |

Tam komut listesi ve kod kuralları: `CLAUDE.md`.

---

## Sistem neden bu şekilde kurulu

- **Üç süreç:** `engine` veri toplar ve tahmin üretir, `api` bunları sunar, `frontend` gösterir. Biri
  çökerse diğerleri ayakta kalır.
- **Her tahmin kaydedilir ve ölçülür.** Bir sinyal modülünün işe yarayıp yaramadığı fikirle değil, Brier
  skoru ve isabet oranıyla belirlenir.
- **Referans tahminciler** (son 90 günün yukarı oranı, son mumun rengi) sürekli çalışır. Gerçek modüller
  bunları yenemiyorsa işe yaramıyor demektir.
- **Look-ahead koruması:** her hesap yalnızca o an kapanmış verilere bakar. Geçmişe dönük test ile canlı
  sistem aynı kodu kullanır.
