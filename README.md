# treca-market-lp

トレカ相場ログ — スニダン実売データの日次価格変動を公開する静的LP。

- 公開URL: https://kakeru321.github.io/treca-market-lp/
- 生成: `python3 generator/build_site.py --days 30`
  - 入力: `~/Documents/treca/treca_draft_YYYYMMDD.json`（daily-treca-news が生成）
  - 出力: `docs/`（GitHub Pages 公開ディレクトリ）
- 静的ページ: `docs/about.html` / `docs/privacy.html`（手動管理）
- アフィリエイトCTA: `generator/build_site.py` の `CTA_SELL_URL` / `CTA_BUY_URL` を提携承認後に設定
