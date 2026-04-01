import sys
import os
import random
import re

def insert_affiliate_links(link_file, article_file):
    if not os.path.exists(link_file) or not os.path.exists(article_file):
        print(f"❌ ファイルが見つかりません: {link_file} または {article_file}")
        return

    # 1. データの準備
    with open(link_file, 'r', encoding='utf-8') as f:
        link_content = f.read().replace('\r\n', '\n')
    
    raw_blocks = re.findall(r'▼.*?(?=\n▼|$)', link_content, re.DOTALL)
    affiliate_blocks = [b.strip() for b in raw_blocks if b.strip() and not b.startswith('(Amazon')]
    
    disclaimer = "(Amazonのアソシエイトとして本アカウントは適格販売により収入を得ています。)"
    
    # 除外パターンの作成（既存リンクの削除用）
    exclude_patterns = [
        re.escape(disclaimer),
        r'https?://(www\.)?amazon\.co\.jp/dp/\w+/ref=nosim\?tag=hiroshit-22',
        r'https?://amzn\.to/\w+',
        r'▼.*?\n?https?://amzn\.to/\w+',
        r'\(Amazonのアソシエイト.*?\)'
    ]
    # affiliate_blocks の各行も除外対象にする
    for b in affiliate_blocks:
        for line in b.split('\n'):
            s = line.strip()
            if s and len(s) > 10: # 短すぎる行は誤爆防止で除外しない
                exclude_patterns.append(re.escape(s))

    all_text = "\n\n".join(affiliate_blocks)
    random_pool = affiliate_blocks[:]
    random.shuffle(random_pool)

    with open(article_file, 'r', encoding='utf-8') as f:
        article_lines = f.readlines()

    # 2. メインリンクの抽出
    main_link = ""
    for line in article_lines:
        match = re.search(r'https?://(www\.)?amazon\.co\.jp/dp/(\w+)/ref=nosim\?tag=hiroshit-22', line)
        if not match: match = re.search(r'https?://amzn\.to/\w+', line)
        if match:
            main_link = match.group(0).strip()
            break
    
    # 3. クリーンアップ
    clean_lines = []
    in_block = False
    for line in article_lines:
        s = line.strip()
        if not s:
            clean_lines.append(line)
            continue
        
        should_skip = False
        for p in exclude_patterns:
            if re.search(p, s):
                should_skip = True
                break
        if should_skip: continue
        
        if s.startswith('---'): # 最後の区切り線以降を除去（再度追加するため）
            break
        clean_lines.append(line)

    # 連続空行除去
    final_clean = []
    last_empty = False
    for line in clean_lines:
        is_empty = not line.strip()
        if is_empty and last_empty: continue
        final_clean.append(line)
        last_empty = is_empty

    # 4. 種別判定と見出しの特定
    h2_indices = [i for i, line in enumerate(final_clean) if line.startswith('## ')]
    is_info = any("主要課題の論点" in final_clean[i] for i in h2_indices)
    
    def get_index(keyword):
        for idx in h2_indices:
            if keyword in final_clean[idx]: return idx
        return -1

    insertions = {} # index: text
    def get_block(): return random_pool.pop(0) if random_pool else ""

    if is_info:
        print("ℹ️ 「情報」種別のレイアウトを適用します")
        # 「情報」のルール:
        # ・全文挿入: 「結論」H2の直前
        # ・1ブロック挿入: 結論から数えて2つ目(論点)、4つ目(詳細)、6つ目(FAQ)のセクション最後
        conclusion_idx = -1
        for i, h_idx in enumerate(h2_indices):
            if "結論" in final_clean[h_idx]:
                conclusion_idx = i
                break
        
        if conclusion_idx != -1:
            # 1. 結論の直前に全文
            insertions[h2_indices[conclusion_idx]] = f"\n{all_text}\n\n{disclaimer}\n\n"
            
            # 2. 指定の見出しのセクション末尾に1ブロック
            # 「2つ目, 4つ目, 6つ目」はインデックスベースだと conclusion_idx + 1, + 3, + 5
            for offset in [1, 3, 5]:
                target_h_idx = conclusion_idx + offset
                if target_h_idx < len(h2_indices):
                    # 次の見出しの直前が挿入ポイント
                    insert_before_idx = h2_indices[target_h_idx + 1] if target_h_idx + 1 < len(h2_indices) else len(final_clean)
                    # insertionsは「直前」に挿入するので、insert_before_idx をキーにする
                    block_text = f"\n{get_block()}\n\n"
                    if insert_before_idx in insertions:
                        insertions[insert_before_idx] += block_text
                    else:
                        insertions[insert_before_idx] = block_text
    else:
        print("📦 「単品」種別のレイアウトを適用します")
        idx_map = {k: get_index(k) for k in ['結論', '利用シーン', '比較', 'メリット', 'デメリット', 'FAQ', '評判', 'まとめ']}
        if idx_map['結論'] != -1:
            insertions[idx_map['結論']] = f"\n{main_link}\n\n{all_text}\n\n{disclaimer}\n\n"
        if idx_map['利用シーン'] != -1:
            insertions[idx_map['利用シーン']] = f"\n{main_link}\n\n"
        if idx_map['比較'] != -1:
            insertions[idx_map['比較']] = f"\n{get_block()}\n\n"
        if idx_map['メリット'] != -1:
            insertions[idx_map['メリット']] = f"\n{main_link}\n\n"
        if idx_map['デメリット'] != -1:
            insertions[idx_map['デメリット']] = f"\n{get_block()}\n\n"
        if idx_map['FAQ'] != -1:
            insertions[idx_map['FAQ']] = f"\n{main_link}\n\n"
        if idx_map['評判'] != -1:
            insertions[idx_map['評判']] = f"\n{get_block()}\n\n"
        if idx_map['まとめ'] != -1:
            insertions[idx_map['まとめ']] = f"\n{main_link}\n\n"

    # 5. 最終出力
    output_lines = []
    for i in range(len(final_clean) + 1):
        if i in insertions:
            output_lines.append(insertions[i])
        if i < len(final_clean):
            output_lines.append(final_clean[i])

    # 最後尾
    output_lines.append(f"\n\n---\n\n{get_block()}\n\n{all_text}\n")

    with open(article_file, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)
    
    print(f"✅ {os.path.basename(article_file)} のアフィリエイトブロックを完全に適用しました")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        # 従来通りの引数渡し
        insert_affiliate_links(sys.argv[1], sys.argv[2])
    else:
        # 引数なし（ターボ実行モード）: target_job.txt から読み込む
        job_file = "target_job.txt"
        if os.path.exists(job_file):
            with open(job_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            if len(lines) >= 2:
                insert_affiliate_links(lines[0], lines[1])
            else:
                print(f"❌ {job_file} の形式が不正です（リンクファイルパスと記事パスの2行が必要です）")
        else:
            print("❌ 引数が指定されておらず、target_job.txt も見つかりません。")
