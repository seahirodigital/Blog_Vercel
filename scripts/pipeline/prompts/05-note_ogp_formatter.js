(() => {
    class NoteFinalFormatter {
        constructor() {
            this.fixedMarkdownCount = 0;
            this.processedUrls = [];
            this.fixedLineBreaks = 0;
            this.convertedHeaders = 0;
            this.titleSet = false;
        }

        getEditor() {
            return document.querySelector('.note-editable, [contenteditable="true"]');
        }

        getTitleInput() {
            return document.querySelector('.note-editor__title-input');
        }

        // STEP 0: タイトルを本文の1行目から取得してセット (日本語入力バグ回避)
        processTitle(editor) {
            const titleInput = this.getTitleInput();
            if (!titleInput) return;

            // すでにタイトルがある程度入っている（10文字以上）なら上書きしない
            if (titleInput.textContent.trim().length > 10) return;

            const firstP = editor.querySelector('p');
            if (firstP) {
                let text = firstP.textContent.trim();
                text = text.replace(/^#+\s*/, ''); // MD記号除去
                titleInput.textContent = text;
                titleInput.dispatchEvent(new Event('input', { bubbles: true }));
                this.titleSet = true;
                console.log(`📌 タイトルをセットしました: ${text}`);
            }
        }

        // STEP 1: Markdown記法の変換 (H2, H3, 太字)
        convertMarkdownToHtml(editor) {
            console.log("🔧 見出しと太字の変換を開始...");
            const paragraphs = Array.from(editor.querySelectorAll('p'));

            paragraphs.forEach(p => {
                let text = p.textContent.trim();
                let newElement = null;

                // ## -> h2 (大見出し), ### -> h3 (見出し)
                if (text.startsWith('### ')) {
                    newElement = document.createElement('h3');
                    newElement.textContent = text.replace('### ', '');
                } else if (text.startsWith('## ')) {
                    newElement = document.createElement('h2');
                    newElement.textContent = text.replace('## ', '');
                } else if (text.startsWith('# ')) {
                    newElement = document.createElement('h2');
                    newElement.textContent = text.replace('# ', '');
                }

                if (newElement) {
                    p.parentNode.replaceChild(newElement, p);
                    this.convertedHeaders++;
                }
            });

            // 太字の変換 (**text** -> <strong>text</strong>)
            const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
            const nodesToFix = [];
            let node;
            while ((node = walker.nextNode())) {
                if (node.textContent.includes('**')) {
                    nodesToFix.push(node);
                }
            }

            nodesToFix.forEach(textNode => {
                const parent = textNode.parentNode;
                if (!parent) return;

                const parts = textNode.textContent.split(/(\*\*.*?\*\*)/g);
                const fragment = document.createDocumentFragment();

                parts.forEach(part => {
                    if (part.startsWith('**') && part.endsWith('**')) {
                        const strong = document.createElement('strong');
                        strong.textContent = part.slice(2, -2);
                        fragment.appendChild(strong);
                        this.fixedMarkdownCount++;
                    } else {
                        fragment.appendChild(document.createTextNode(part));
                    }
                });

                parent.replaceChild(fragment, textNode);
            });
        }

        extractUrlsWithPositions(editor) {
            const urls = [];
            const regex = /(https?:\/\/[^\s\n\r]+)/g;
            const text = editor.innerText;
            let match;
            while ((match = regex.exec(text)) !== null) {
                urls.push({ url: match[1], position: match.index });
            }
            return urls;
        }

        moveCaretToUrl(editor, url, occurrence) {
            const selection = window.getSelection();
            const range = document.createRange();
            const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
            let node, count = 0;

            while ((node = walker.nextNode())) {
                let searchText = node.textContent;
                let startIdx = 0;
                let idx;
                while ((idx = searchText.indexOf(url, startIdx)) !== -1) {
                    count++;
                    if (count === occurrence) {
                        range.setStart(node, idx + url.length);
                        range.setEnd(node, idx + url.length);
                        selection.removeAllRanges();
                        selection.addRange(range);
                        return true;
                    }
                    startIdx = idx + 1;
                }
            }
            return false;
        }

        simulateEnter(editor) {
            const ev = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true };
            editor.dispatchEvent(new KeyboardEvent("keydown", ev));
            editor.dispatchEvent(new KeyboardEvent("keyup", ev));
        }

        normalizeLineBreaks(editor) {
            let removed = 0;
            const pTags = Array.from(editor.querySelectorAll('p'));
            pTags.forEach(p => {
                if (p.textContent.trim() === '' && p.nextElementSibling && p.nextElementSibling.tagName === 'P' && p.nextElementSibling.textContent.trim() === '') {
                    p.remove();
                    removed++;
                }
            });
            this.fixedLineBreaks = removed;
        }

        async run() {
            const editor = this.getEditor();
            if (!editor) return console.error("❌ エディタが見つかりません");

            // タイトル設定 (本文1行目がタイトルの場合を想定)
            this.processTitle(editor);

            // 見出し・太字
            this.convertMarkdownToHtml(editor);
            await new Promise(r => setTimeout(r, 500));

            // OGP展開
            const urls = this.extractUrlsWithPositions(editor);
            for (const item of urls) {
                const url = item.url;
                if (!url.includes('amzn.to') && !url.includes('amazon.co.jp') && !url.includes('apple.com') && !url.includes('youtube.com')) continue;

                const found = this.processedUrls.find(u => u.url === url);
                const count = found ? ++found.count : (this.processedUrls.push({ url, count: 1 }), 1);

                if (this.moveCaretToUrl(editor, url, count)) {
                    this.simulateEnter(editor);
                    await new Promise(r => setTimeout(r, 200));
                }
            }

            // 最終整理
            this.normalizeLineBreaks(editor);
            console.log(`✅ 完了: 見出し(${this.convertedHeaders}), 太字(${this.fixedMarkdownCount}), タイトルセット(${this.titleSet})`);
        }
    }

    new NoteFinalFormatter().run();
})();
