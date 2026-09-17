"""RSS/Atom gövde biçimleri.

Bu ortamdan feed'lere erişilemediği için gövdeler **elle yazılmıştır**; RSS 2.0 ve Atom 1.0
şemalarına uyar ve kaynakların bilinen alan seçimlerini taklit eder (CoinDesk/Cointelegraph
RSS 2.0 + `pubDate`, Decrypt Atom + `updated`). Gerçek yanıtla ilk karşılaşma kullanıcının
makinesinde olur; oradaki fark çıkarsa ARCHITECTURE §4 tablosu güncellenir (CLAUDE.md §12.5).
"""

from typing import Final

RSS_TWO_ITEMS: Final = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CoinDesk</title>
    <link>https://www.coindesk.com</link>
    <item>
      <title>Bitcoin holds above key level as ETF flows turn positive</title>
      <link>https://www.coindesk.com/markets/2026/09/17/btc-etf-flows?utm_source=rss&amp;utm_medium=feed</link>
      <description>&lt;p&gt;Spot bitcoin funds recorded net inflows for a third
        day.&lt;/p&gt;</description>
      <pubDate>Thu, 17 Sep 2026 08:30:00 GMT</pubDate>
      <guid>https://www.coindesk.com/markets/2026/09/17/btc-etf-flows</guid>
    </item>
    <item>
      <title>Ether staking withdrawals queue lengthens</title>
      <link>https://www.coindesk.com/tech/2026/09/17/eth-exit-queue/</link>
      <description>Validators waiting to exit rose sharply this week.</description>
      <pubDate>Thu, 17 Sep 2026 07:05:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_ONE_ITEM: Final = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Decrypt</title>
  <entry>
    <title>Solana network upgrade ships on mainnet</title>
    <link href="https://decrypt.co/1234/solana-upgrade"/>
    <updated>2026-09-17T09:15:00Z</updated>
    <summary>The upgrade reduces block times.</summary>
  </entry>
</feed>
"""

# Başlıksız girdi ve tarihsiz girdi: ikisi de gerçek feed'lerde görülür.
RSS_MESSY: Final = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>The Block</title>
    <item>
      <link>https://www.theblock.co/post/1/no-title</link>
      <pubDate>Thu, 17 Sep 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Exchange outage reported</title>
      <link>https://www.theblock.co/post/2/outage</link>
    </item>
    <item>
      <title>Very old story</title>
      <link>https://www.theblock.co/post/3/old</link>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
