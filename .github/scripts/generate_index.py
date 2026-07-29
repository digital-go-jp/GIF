#!/usr/bin/env python3
"""
GIF HTML Generator - デジタル庁デザインシステム対応版
政府相互運用性フレームワーク (GIF) のHTMLインデックス生成スクリプト
設計方針: 本スクリプトは「文書登録→タグ→公開」のCI/CD用途。
固有条件は不変・単一ワークフローのため、総量最小を優先する。
意図的に不採用: DI / 設定外部化 / テスト資産 / Jinja2 / JS・CSSの分離。
定数はこのファイル冒頭に集約。検証はexperimentalリポジトリでの生成HTML目視やローカル実行で行う。
"""
import os
import re
import subprocess
import markdown
from pathlib import Path
from datetime import datetime

# 定数は外部設定化せず冒頭にベタ書き（設定ファイル＝第2の管理対象を避けるため）
PLACEHOLDER = "<!-- FILE_LIST -->"
VERSIONHOLDER = "<!-- LATEST_VERSION -->"
INDEX_HTML = "index.html"
README_MD = "README.md"

# 名称
GIF_NAME="GIF"
GIF_FULL_NAME="政府相互運用性フレームワーク"

# サイト設定
SITE_BASE_URL = "https://gif.digital.go.jp/"
SITE_NAME = "デジタル庁 政府相互運用性フレームワーク（GIF)"
SITE_AUTHOR = "デジタル庁"
SITE_DEFAULT_DESCRIPTION = "政府情報システムにおける相互運用性を確保するための技術標準"
SITE_DEFAULT_KEYWORDS = ["政府相互運用性フレームワーク", "GIF", "デジタル庁", "技術標準"]

# File paths for templates
SCRIPT_DIR = Path(__file__).parent
HTML_TEMPLATE_PATH = SCRIPT_DIR / "index_template.html"

# Load templates from files
HTML_TEMPLATE = HTML_TEMPLATE_PATH.read_text(encoding="utf-8")

# html templates
HTML_DETAILS = '<li><details{open}><summary><a href="{href}"{current}>{name}</a></summary><ul>{children}</ul></details></li>'
HTML_LEAF = '<li class="leaf"><a href="{href}"{current}>{name}</a></li>'
HTML_SIDEBAR_WRAPPER = '<a href="{href}" class="sidebar-version"{current}>{name}</a><ul class="tree-list">{inner}</ul>'
HTML_BODY_WITH_SIDEBAR = '<div class="page-layout">\n<nav class="sidebar">{sidebar}</nav>\n<main>\n{breadcrumb}\n{content}\n</main>\n</div>'

# テーブル行（デジタル庁DS対応）
HTML_TABLE_ROW_PARENT = '<tr class="row-parent"><td colspan="3"><a href="{href}">../</a></td></tr>'
HTML_TABLE_ROW_DIR = '<tr class="row-dir"><td><a href="{href}">{name}</a></td><td>-</td><td>{date}</td></tr>'
HTML_TABLE_ROW_FILE = '<tr class="row-file" data-ext="{ext}"><td><a href="{href}">{name}</a></td><td>{size}</td><td>{date}</td></tr>'
# 後方互換性
HTML_TABLE_ROW = HTML_TABLE_ROW_FILE
# プレビューリンク付きファイル行（.mmd など、ビューアHTMLが存在するファイル用）
HTML_TABLE_ROW_FILE_WITH_PREVIEW = (
    '<tr class="row-file" data-ext="{ext}">'
    '<td><a href="{href_raw}" download>{name}</a>'
    ' <a href="{href_html}" class="file-preview-link" target="_blank" rel="noopener noreferrer">プレビュー</a></td>'
    '<td>{size}</td><td>{date}</td></tr>'
)

# ファイルリストテーブル
FILE_LIST_HTML = '''<table role="table" aria-label="ファイル一覧">
<thead>
<tr><th scope="col">名前</th><th scope="col">サイズ</th><th scope="col">リリース日</th></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>'''

# ブレッドクラム
BREADCRUMB_HTML = '<nav class="breadcrumb" aria-label="パンくずリスト">{content}</nav>'

# インデックスに表示しないファイル群。
SKIP_NAMES = {INDEX_HTML, README_MD, "favicon.ico", "index.md", "sitemap.xml"}


def build_meta_seo(
    *,
    title: str,
    description: str,
    page_url: str,
    keywords: list[str] | None = None,
    og_type: str = "website",
) -> str:
    """
    </head> 直前に挿入するSEO・OGPメタタグブロックを生成する。

    Args:
        title:       <title> および og:title に使うページタイトル
        description: meta description および og:description
        page_url:    このページの正規URL（og:url, canonical に使用）
        keywords:    キーワードリスト（省略時はサイトデフォルト）
        og_type:     OGP の og:type（デフォルト "website"）

    Returns:
        メタタグのHTML文字列（<head>タグを含まない）
    """
    kw = keywords if keywords is not None else SITE_DEFAULT_KEYWORDS
    keywords_str = ",".join(kw)
    full_title = f"{title} | {SITE_NAME}"

    def esc(s: str) -> str:
        """
        属性値コンテキスト用エスケープ（& " <）。>は属性値内では不要。
        html.escapeに統一しない: mmd側と要件が異なり、コンテキスト別最適化を優先。
        """
        return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

    # sitemap.xmlは、generate_sitemap()で生成する。
    lines = [
        # --- 基本SEO ---
        f'  <meta name="description" content="{esc(description)}">',
        f'  <meta name="keywords" content="{esc(keywords_str)}">',
        f'  <meta name="author" content="{esc(SITE_AUTHOR)}">',
        f'  <meta name="robots" content="index, follow">',
        f'  <link rel="sitemap" type="application/xml" href="{SITE_BASE_URL}/sitemap.xml">',
        f'  <link rel="canonical" href="{esc(page_url)}">',
        # --- OGP ---
        f'  <meta property="og:title" content="{esc(full_title)}">',
        f'  <meta property="og:description" content="{esc(description)}">',
        f'  <meta property="og:type" content="{esc(og_type)}">',
        f'  <meta property="og:url" content="{esc(page_url)}">',
        f'  <meta property="og:site_name" content="{esc(SITE_NAME)}">',
        # --- タイトル ---
        f'  <title>{esc(full_title)}</title>',
    ]
    return "\n".join(lines)


def _page_url(dir_path: Path, releases_root: Path) -> str:
    """ページの正規URLを組み立てる。"""
    rel = dir_path.relative_to(releases_root)
    # releases_root 自体は SITE_BASE_URL/ に対応
    path_str = "/".join(rel.parts)
    if path_str:
        return f"{SITE_BASE_URL}/{path_str}/"
    return f"{SITE_BASE_URL}/"


def _page_description(title: str, dir_path: Path, releases_root: Path) -> str:
    """ページ種別に応じた description を返す。"""
    rel_parts = dir_path.relative_to(releases_root).parts
    if not rel_parts:
        # サイトルート
        return SITE_DEFAULT_DESCRIPTION
    version = rel_parts[0]
    if len(rel_parts) == 1:
        # バージョンルート（例: 2.3/）
        return f"政府相互運用性フレームワーク {version} のドキュメント一覧"
    # サブディレクトリ
    return f"{title} — 政府相互運用性フレームワーク {version}"


def _page_keywords(dir_path: Path, releases_root: Path) -> list[str]:
    """ページ種別に応じたキーワードリストを返す。"""
    rel_parts = dir_path.relative_to(releases_root).parts
    base = list(SITE_DEFAULT_KEYWORDS)
    if rel_parts:
        version = rel_parts[0]
        base.insert(0, f"GIF {version}")
        # サブディレクトリ名もキーワードに追加
        for part in rel_parts[1:]:
            base.append(part)
    return base


def load_all_metadata():
    """
    Build version metadata from git tags.
    Past versions does not use sementic versions,
    we do not sort by version:refname but sort by creatordate.
    eg. 2.01 and 2.1 are considered as a same version.
    """
    try:
        result = subprocess.run(
            ['git', 'for-each-ref', '--sort=creatordate',
            '--format=%(refname:short)\t%(creatordate:short)',
            'refs/tags/v*'],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return {}
    if result.returncode != 0:
        return {}
    metadata = {}
    lines = result.stdout.strip().splitlines()
    filtered = [l for l in lines if l and int(l.split('\t')[0][1:].split('.')[0]) >= 2]
    for i, line in enumerate(reversed(filtered)):  # 新しい順にインデックス化
        tag, date = line.split('\t')
        version = tag[1:]
        metadata[version] = {
            'release_date': date,
            'rank': i,          # 0が最新
            'is_latest': i == 0,
        }
    return metadata


def generate_sitemap(releases_root: Path, all_metadata: dict) -> None:
    """
    pages/sitemap.xml を生成する。
    """
    urls = []

    def add_url(dir_path: Path, priority: float, lastmod: str | None) -> None:
        """
        改訂は半期１回。最新ほど優先度高い。
        """
        page_url = _page_url(dir_path, releases_root)
        lastmod_tag = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        urls.append(
            f"  <url>\n"
            f"    <loc>{page_url}</loc>"
            f"{lastmod_tag}\n"
            f"    <changefreq>yearly</changefreq>\n"
            f"    <priority>{priority:.1f}</priority>\n"
            f"  </url>"
        )

    # ルート（バージョン一覧）
    add_url(releases_root, priority=0.9, lastmod=None)

    # 各ディレクトリを階層順に処理
    for dir_path in sorted(releases_root.rglob("*")):
        if not dir_path.is_dir():
            continue
        rel_parts = dir_path.relative_to(releases_root).parts
        depth = len(rel_parts)

        if depth == 1:
            meta = all_metadata.get(rel_parts[0])
            lastmod = str(meta["release_date"]) if meta else format_mtime(dir_path)
            rank = meta["rank"] if meta else len(all_metadata)
            priority = max(0.5, 1.0 - rank * 0.3)
        else:
            meta = all_metadata.get(rel_parts[0])
            lastmod = str(meta["release_date"]) if meta else format_mtime(dir_path)
            rank = meta["rank"] if meta else len(all_metadata)
            version_priority = max(0.5, 1.0 - rank * 0.3)
            priority = max(0.4, version_priority - 0.2)

        add_url(dir_path, priority=priority, lastmod=lastmod)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )

    sitemap_path = releases_root / "sitemap.xml"
    sitemap_path.write_text(xml, encoding="utf-8")
    print(f"  Generated: sitemap.xml")


def find_version_dir(dir_path, releases_root):
    try:
        rel = dir_path.relative_to(releases_root)
    except ValueError:
        return None
    if not rel.parts:
        return None
    return releases_root / rel.parts[0]


def _is_ancestor(ancestor, path):
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


def format_mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def build_sidebar_tree(version_dir, current_dir):
    """Return HTML for the sidebar directory tree of a release version."""

    def rel_href(target):
        return os.path.relpath(str(target), str(current_dir)) + "/" + INDEX_HTML

    def render_dirs(dir_path):
        subdirs = sorted(
            (e for e in dir_path.iterdir() if e.is_dir() and not e.name.startswith(".")),
            key=lambda p: p.name,
        )
        items = []
        for entry in subdirs:
            href = rel_href(entry)
            is_current = entry == current_dir
            is_open = is_current or _is_ancestor(entry, current_dir)
            current_attr = ' aria-current="page"' if is_current else ""
            children = render_dirs(entry)
            if children:
                open_attr = " open" if is_open else ""
                items.append(HTML_DETAILS.format(open=open_attr, href=href, current=current_attr, name=entry.name, children=children))
            else:
                items.append(HTML_LEAF.format(href=href, current=current_attr, name=entry.name))
        return "\n".join(items)

    version_href = rel_href(version_dir)
    is_version_root = current_dir == version_dir
    version_current = ' aria-current="page"' if is_version_root else ""
    inner = render_dirs(version_dir)
    return HTML_SIDEBAR_WRAPPER.format(href=version_href, current=version_current, name=version_dir.name, inner=inner)


def generate_file_list(dir_path, releases_root, all_metadata, is_root=False):
    """
    ディレクトリ内のファイル・フォルダ一覧テーブルを生成
    
    Args:
        dir_path: 対象ディレクトリのPath
        releases_root: リリースルートディレクトリのPath
        all_metadata: メタデータ辞書
        is_root: ルートディレクトリかどうか
    
    Returns:
        HTMLテーブル文字列
    """
    rows = []
    # 親ディレクトリリンク
    if not is_root:
        rows.append(HTML_TABLE_ROW_PARENT.format(href=f"../{INDEX_HTML}"))
    # バージョン情報の取得
    version_dir = find_version_dir(dir_path, releases_root)
    version_meta = all_metadata.get(version_dir.name) if version_dir else None
    version_date = (
        str(version_meta["release_date"])
        if version_meta and "release_date" in version_meta
        else None
    )
    # エントリの取得とソート（ディレクトリ優先、名前順）
    def sort_key(p):
        if is_root and p.is_dir():
            # ルートのディレクトリ（バージョン）はrankで昇順（0が最新）
            meta = all_metadata.get(p.name)
            rank = meta["rank"] if meta else len(all_metadata)
            return (0, rank, p.name)
        return (0 if p.is_dir() else 1, 0, p.name)

    entries = sorted(dir_path.iterdir(), key=sort_key)
    for entry in entries:
        name = entry.name
        # スキップ対象のチェック
        if name.startswith(".") or name in SKIP_NAMES:
            continue
        # 日付の決定
        if is_root and entry.is_dir():
            meta = all_metadata.get(entry.name)
            date = (
                str(meta["release_date"])
                if meta and "release_date" in meta
                else format_mtime(entry)
            )
        else:
            date = version_date or format_mtime(entry)
        if entry.is_dir():
            rows.append(HTML_TABLE_ROW_DIR.format(href=f"{name}/{INDEX_HTML}", name=f"{name}/", size="-", date=date))
        elif entry.suffix in (".mmd", ".svg"):
            # ダウンロードリンク＋プレビューリンク
            rows.append(HTML_TABLE_ROW_FILE_WITH_PREVIEW.format(
                href_raw=name,
                href_html=(entry.with_suffix(".html") if entry.suffix == ".mmd" else entry).name,
                name=name,
                ext=entry.suffix.lower(),
                size=format_size(entry.stat().st_size),
                date=date,
            ))
        elif entry.suffix == ".html" and entry.with_suffix(".mmd").exists():
            # .mmd 由来の .html はリストに表示しない（.mmd 行で代替済み）
            continue
        else:
            rows.append(HTML_TABLE_ROW_FILE.format(href=name, name=name, size=format_size(entry.stat().st_size), date=date, ext=entry.suffix.lower()))
    return FILE_LIST_HTML.format(rows="\n".join(rows))


def build_breadcrumb(dir_path, releases_root):
    """
    パンくずリストの生成。
    """
    rel = dir_path.relative_to(releases_root)
    parts = rel.parts
    if not parts:
        return '<nav class="breadcrumb">GIF</nav>'

    total = len(parts)
    crumbs = ['<nav class="breadcrumb">']
    crumbs.append(f'<a href="{"../" * total}' + INDEX_HTML + '">GIF</a>')
    for i, part in enumerate(parts):
        depth = total - i - 1
        if depth == 0:
            crumbs.append(f" / <span>{part}</span>")
        else:
            crumbs.append(f' / <a href="{"../" * depth}' + INDEX_HTML + f'">{part}</a>')
    crumbs.append("</nav>")
    return "".join(crumbs)


def find_latest_version(all_metadata: dict) -> str | None:
    """
    all_metadata の中から rank=0（最新）のバージョン名を返す。
    存在しない場合は None。
    """
    for version, meta in all_metadata.items():
        if meta.get("rank") == 0:
            return version
    return None


def build_older_banner(
    dir_path: Path,
    releases_root: Path,
    version_dir: Path,
    version_meta: dict,
    all_metadata: dict,
) -> str:
    """
    古いバージョン向けのバナーHTMLを生成する。

    - 同一相対パスが最新バージョンフォルダ内に存在する場合:
        → 最新バージョンの対応ページへのリンク付きバナー
    - 存在しない場合:
        → サイトルート（バージョン一覧）へのリンク付きバナー
    """
    if not version_meta or version_meta.get("is_latest", True):
        return ""

    latest_version = find_latest_version(all_metadata)

    # dir_path の version_dir からの相対パス（サブディレクトリ部分）を取得
    # 例: pages/2.0/appendix/ → relative = appendix/
    rel_from_version = dir_path.relative_to(version_dir)

    # 最新バージョンの対応ディレクトリが存在するか確認
    latest_target_path: Path | None = None
    if latest_version:
        candidate = releases_root / latest_version / rel_from_version
        if candidate.is_dir():
            latest_target_path = candidate

    # バナー内リンクの href を計算（現在ページからの相対パス）
    if latest_target_path is not None:
        # 現在ページ → 最新バージョンの対応ページ
        rel_href = os.path.relpath(str(latest_target_path), str(dir_path))
        link_href = rel_href.replace("\\", "/") + "/" + INDEX_HTML
        link_text = f"最新バージョン（{latest_version}）の対応ページへ"
    else:
        # 最新バージョンに対応パスがない → ルートへ
        depth = len(dir_path.relative_to(releases_root).parts)
        link_href = "../" * depth + INDEX_HTML
        link_text = "最新バージョンのファイル一覧へ"

    return (
        '<div class="older-version-banner" role="note">'
        "このバージョンは最新リリースではありません。"
        f'<a href="{link_href}">{link_text}</a>'
        "</div>"
    )


def _build_and_write_html(
    *,
    out_path: Path,
    html_body: str,
    dir_path: Path,
    releases_root: Path,
    all_metadata: dict,
    page_url: str,
    title: str,
    without_sidebar: bool,
) -> Path:
    """
    html_body からHTMLファイルを生成して書き出す共通処理。
    """
    is_root = dir_path == releases_root
    version_dir = None if is_root else find_version_dir(dir_path, releases_root)

    if without_sidebar:
        body = f'<main class="centered">\n{html_body}\n</main>'
    else:
        sidebar_html = build_sidebar_tree(version_dir, dir_path)
        breadcrumb = build_breadcrumb(dir_path, releases_root)
        body = HTML_BODY_WITH_SIDEBAR.format(
            sidebar=sidebar_html, breadcrumb=breadcrumb, content=html_body
        )

    version_meta = all_metadata.get(version_dir.name) if version_dir else None
    older_banner = build_older_banner(
        dir_path=dir_path,
        releases_root=releases_root,
        version_dir=version_dir,
        version_meta=version_meta,
        all_metadata=all_metadata,
    )

    meta_seo = build_meta_seo(
        title=title,
        description=_page_description(title, dir_path, releases_root),
        page_url=page_url,
        keywords=_page_keywords(dir_path, releases_root),
    )

    output = HTML_TEMPLATE.format(
        meta_seo=meta_seo,
        body=body,
        older_banner=older_banner,
    )

    out_path.write_text(output, encoding="utf-8")
    print(f"  Generated: {out_path.relative_to(releases_root)}")
    return out_path


def convert_mmd_to_html(mmd_path: Path, releases_root: Path, all_metadata: dict) -> Path:
    """
    単一の .mmd ファイルを読み込み、Mermaid図を表示する .html を生成する。
    """
    dir_path = mmd_path.parent
    mmd_text = mmd_path.read_text(encoding="utf-8")
    title = mmd_path.stem

    # ブラウザがHTMLエンティティ・特殊文字を解釈しないようエスケープしてから埋め込む
    # 要素内容コンテキスト用エスケープ（& < >）。GIFのクラス名"名前空間:キー名"の
    # コロンがMermaidクラス図定義と衝突する問題への直接対処。
    safe_mmd = mmd_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Mermaidダイアグラムとして埋め込む
    html_body = f'<div id="mermaid-wrapper" class="mermaid">\n{safe_mmd}\n</div>'

    rel = mmd_path.relative_to(releases_root)
    page_url = f"{SITE_BASE_URL}/{'/'.join(rel.with_suffix('.html').parts)}"

    return _build_and_write_html(
        out_path=mmd_path.with_suffix(".html"),
        html_body=html_body,
        dir_path=dir_path,
        releases_root=releases_root,
        all_metadata=all_metadata,
        page_url=page_url,
        title=title,
        without_sidebar=True,
    )


def process_directory(dir_path, releases_root, all_metadata, repo_root=None):
    is_root = dir_path == releases_root
    readme = dir_path / ("index.md" if is_root else README_MD)
    file_list_html = generate_file_list(dir_path, releases_root, all_metadata, is_root=is_root)

    if readme.exists():
        md_text = readme.read_text(encoding="utf-8")
        html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
        if PLACEHOLDER in html_body:
            latest = find_latest_version(all_metadata)
            html_body = html_body.replace(PLACEHOLDER, file_list_html).replace(VERSIONHOLDER, f'最新版はバージョン{latest}です。')
        else:
            html_body += file_list_html
        title_match = re.search(r"<h1[^>]*>(.+?)</h1>", html_body)
        title = (
            re.sub(r"<[^>]+>", "", title_match.group(1))
            if title_match
            else dir_path.name
        )
    else:
        title = dir_path.name
        html_body = f"<h1>{title}</h1>\n{file_list_html}"

    return _build_and_write_html(
        out_path=dir_path / INDEX_HTML,
        html_body=html_body,
        dir_path=dir_path,
        releases_root=releases_root,
        all_metadata=all_metadata,
        page_url=_page_url(dir_path, releases_root),
        title=title,
        without_sidebar=(dir_path == releases_root),
    )


def main():
    repo_root = Path(__file__).resolve().parents[2]
    releases_root = repo_root / "pages"

    if not releases_root.is_dir():
        raise SystemExit(f"Error: {releases_root} not found")

    all_metadata = load_all_metadata()

    print("Converting Mermaid files to HTML...")
    for mmd_path in sorted(releases_root.rglob("*.mmd")):
        convert_mmd_to_html(mmd_path, releases_root, all_metadata)

    print("Generating HTML index files...")
    process_directory(releases_root, releases_root, all_metadata, repo_root=repo_root)
    for dir_path in sorted(releases_root.rglob("*")):
        if dir_path.is_dir():
            process_directory(dir_path, releases_root, all_metadata)
    print("Generating sitemap...")
    generate_sitemap(releases_root, all_metadata)

    print("Done.")


if __name__ == "__main__":
    main()
