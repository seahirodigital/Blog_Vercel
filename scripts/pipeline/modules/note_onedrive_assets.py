"""大志の記事と画像をOneDrive上で対応付ける。"""

import os
import re
import unicodedata
from pathlib import Path

import requests

GRAPH_API = 'https://graph.microsoft.com/v1.0'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def _normal(value):
    return unicodedata.normalize('NFC', value)


def find_article_assets(article_name, entries, need_thumbnail=True):
    article = Path(_normal(article_name))
    if article.suffix.lower() != '.md':
        raise ValueError('Markdownの記事名を確認できません')
    match = re.match(r'^([A-Za-z]+-\d+)_', article.stem)
    if not match:
        raise ValueError('記事番号を確認できません')
    prefix = match.group(1)
    body, thumbnails = [], []
    for entry in entries:
        name = _normal(entry.get('name', ''))
        image = Path(name)
        if 'file' not in entry or image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if image.stem == article.stem:
            body.append(entry)
        if image.stem.startswith(prefix + '_') and 'サムネイル' in image.stem:
            thumbnails.append(entry)
    if len(body) != 1:
        raise ValueError(f'記事と同名の本文画像は1件必要です（{len(body)}件）')
    if need_thumbnail and len(thumbnails) != 1:
        raise ValueError(f'{prefix}のサムネイルは1件必要です（{len(thumbnails)}件）')
    return body[0], thumbnails[0] if need_thumbnail else None


def download_article_assets(token, file_id, need_thumbnail=True):
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{GRAPH_API}/me/drive/items/{file_id}', headers=headers, timeout=60)
    response.raise_for_status()
    article = response.json()
    parent_id = (article.get('parentReference') or {}).get('id', '')
    if not parent_id:
        raise ValueError('記事の親フォルダを確認できません')
    next_url = f'{GRAPH_API}/me/drive/items/{parent_id}/children'
    entries = []
    while next_url:
        response = requests.get(next_url, headers=headers, timeout=60)
        response.raise_for_status()
        listing = response.json()
        entries.extend(listing.get('value', []))
        next_url = listing.get('@odata.nextLink')
    body, thumbnail = find_article_assets(article.get('name', ''), entries, need_thumbnail)
    for entry, directory_name, base_name in (
        (body, 'TAISHI_BODY_IMAGE_DIR', 'article-image'),
        (thumbnail, 'TAISHI_THUMBNAIL_DIR', 'thumbnail'),
    ):
        if entry is None:
            continue
        destination_dir = Path(os.environ[directory_name])
        destination_dir.mkdir(parents=True, exist_ok=True)
        response = requests.get('{}/me/drive/items/{}/content'.format(GRAPH_API, entry['id']), headers=headers, timeout=120)
        response.raise_for_status()
        if not response.content:
            raise ValueError('画像が空です')
        destination = destination_dir / (base_name + Path(entry['name']).suffix.lower())
        destination.write_bytes(response.content)
        print(f'✅ 画像取得完了: {entry["name"]}')
