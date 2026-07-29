# スクリプト・ワークフロー 開発者向け情報

## リポジトリ構成

```
.github/
├── scripts/
│   ├── generate_index.py   # GitHub Pages用コンテンツ生成スクリプト
│   ├── index_template.html # HTMLテンプレート
│   └── pages/
│       ├── index.md        # トップページコンテンツ
│       └── favicon.ico
└── workflows/
    ├── pages.yml           # GitHub Pagesへの公開ワークフロー
    └── release-archive.yml # Zipアーカイブ生成ワークフロー

```

## generate_index.py の処理概要

以下の処理をまとめて行います。

### 1. トップページ生成
`pages/index.md`を処理してトップページの`index.html`を生成します。
`index.md`にはバージョン一覧を挿入するプレースホルダ`<!-- FILE_LIST -->`が含まれており、後述のバージョン一覧リンクが埋め込まれます。

### 2. リリースバージョンの展開
Gitのタグ（`v*`形式）からリリースを取得し、トップページにはタグの作成日付順に並べることで、バージョン一覧は新しい順に表示されます。

なお、メジャーバージョン1（`v1.*`）はインデックスに含まれません。
これらのリリースはGitHubリポジトリのReleasesから引き続き取得可能です。

### 3. バージョンごとのindex.html生成
各バージョンフォルダ内の`README.md`をもとに、各フォルダの`index.html`を生成します。
`index.html`にはフォルダ内のコンテンツ一覧とリンクが含まれます（ディレクトリリスト風）。

### 4. Mermaidファイルのビジュアライズ
`.mmd`ファイルが含まれる場合、Mermaid.jsで可視化されるHTMLを生成します。

## バージョン番号の方針

バージョン2系には`2.01`のようなバージョンが存在します。以後、セマンティックバージョニング（`MAJOR.MINOR.PATCH`）に準拠してください。

## ワークフロー

### pages.yml（ビルド・デプロイ）

`workflow_dispatch`による手動実行のみ対応しています。実行時に`publish_pages`オプションを選択できます。

| `publish_pages` | 動作 |
|---|---|
| `false`（デフォルト） | ビルドのみ。成果物を`gif-site-{実行番号}`としてArtifactsに1日間保存 |
| `true` | ビルド後にGitHub Pagesへデプロイ |

成果物を公開前にダウンロードしてローカルで確認してからデプロイすることが推奨されます。
ビルド処理の概要は以下のとおりです。

1. `pages/`に`index.md`と`favicon.ico`を展開
1. `v*`形式のタグからメジャーバージョン2以降のコンテンツを`pages/{version}/`に展開（`.github`フォルダは除外）
2. Pythonの`markdown`ライブラリを使用してHTMLを生成
3. `generate_index.py`を実行

### release-archive.yml（Zipアーカイブ生成）

`v*`形式のタグが付いたリリース時に自動実行され、GitHubリリースのアーティファクトとして登録されます。
以下のフォルダはアーカイブから除外されます。

- `.github/`

## HTMLテンプレート

`index_template.html`はPythonの`str.format()`構文を使用しています。
CSSブロックの`{`と`}`は`{{`と`}}`でエスケープされているため、VS CodeでCSSの警告が表示される場合があります。
`.vscode/settings.json`に以下を追加してください。

```json
{
  "css.validate": false,
  "html.validate.scripts": false,
  "html.validate.styles": false
}
```
