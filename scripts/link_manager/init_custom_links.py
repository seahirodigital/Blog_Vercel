import re

with open("public/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# 1. customLinks の state を追加
sidebar_state_anchor = "const [showFolderPicker, setShowFolderPicker] = useState(false);\n      const [showLinkPicker, setShowLinkPicker] = useState(false);"
custom_links_state = """const [showFolderPicker, setShowFolderPicker] = useState(false);
      const [showLinkPicker, setShowLinkPicker] = useState(false);
      const [customLinks, setCustomLinks] = useState(() => {
        try {
          const saved = JSON.parse(localStorage.getItem('sb_customLinks'));
          if (saved && Array.isArray(saved) && saved.length > 0) return saved;
        } catch {}
        return [
          { id: 'mobile-links', title: 'モバイルリンク集', url: '/links.html' },
          { id: 'note', title: 'note', url: 'https://note.com/startupm' },
          { id: 'yt-sheet', title: 'YouTube動画取得シート', url: 'https://docs.google.com/spreadsheets/d/1cw6RC1XX4nAYvfZrBq7nmTtrr2oGFsSI0r_pVIxGxAc/edit?pli=1&gid=983578135#gid=983578135' }
        ];
      });"""

content = content.replace(sidebar_state_anchor, custom_links_state)

# 2. リンク集パネルを置き換え
link_panel_regex = re.compile(r"\{\/\* リンク集パネル \*\/\}.*?\{\/\* フォルダ管理 \*\/\}", re.DOTALL)

new_link_panel = """{/* リンク集パネル */}
          {showLinkPicker && (
            <div
              ref={linkPickerRef}
              onPointerDown={(e) => e.stopPropagation()}
              style={mobileSidebarOpen
                ? { position:'fixed', left:'12px', right:'12px', bottom:'84px', zIndex:99999, background:'white', border:'1px solid #e2e8f0', borderRadius:'10px', boxShadow:'0 8px 32px rgba(0,0,0,0.22)', display:'flex', flexDirection:'column' }
                : { position:'absolute', bottom:'100%', left:'8px', right:'8px', zIndex:9998, background:'white', border:'1px solid #e2e8f0', borderRadius:'10px', boxShadow:'0 8px 32px rgba(0,0,0,0.15)', display:'flex', flexDirection:'column', marginBottom:'4px' }
              }
            >
              <div style={{ padding:'10px 12px 8px', borderBottom:'1px solid #f1f5f9', fontSize:'12px', fontWeight:700, color:'#7C4DFF', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span>リンク集</span>
                <button onClick={() => {
                  const title = prompt('追加するリンクのタイトルを入力:');
                  if (!title || !title.trim()) return;
                  const url = prompt('URLを入力:');
                  if (url && url.trim()) {
                    const newLinks = [...customLinks, { id: 'link_' + Date.now(), title: title.trim(), url: url.trim() }];
                    setCustomLinks(newLinks);
                    try { localStorage.setItem('sb_customLinks', JSON.stringify(newLinks)); } catch {}
                  }
                }} style={{ background:'none', border:'none', color:'#7C4DFF', cursor:'pointer', fontSize:'11px', fontWeight:700 }}>＋ 追加</button>
              </div>
              <div style={{ padding:'8px', display:'flex', flexDirection:'column', gap:'4px', maxHeight:'250px', overflowY:'auto' }}>
                {customLinks.map((link, idx) => (
                  <div key={link.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', background:'white', padding:'2px 4px', borderRadius:'6px' }}>
                    <a
                      href={link.url}
                      target={link.url.startsWith('/') ? '_self' : '_blank'}
                      rel="noopener noreferrer"
                      onClick={(e) => {
                         if (link.url.startsWith('/')) {
                           e.preventDefault();
                           setShowLinkPicker(false);
                           if (typeof onMobileClose === 'function') onMobileClose();
                           window.location.assign(link.url);
                         }
                      }}
                      className="flex items-center gap-2 text-xs text-slate-600 hover:text-[#7C4DFF] hover:bg-purple-50 rounded-md px-2 py-1.5 transition-all w-full"
                      style={{ textDecoration: 'none', flex: 1, minWidth: 0 }}
                      title={link.url}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}>
                        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
                      </svg>
                      <span style={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{link.title}</span>
                    </a>
                    <button onClick={() => {
                      const newTitle = prompt('タイトルを編集:', link.title);
                      if (newTitle === null) return;
                      const newUrl = prompt('URLを編集:', link.url);
                      if (newUrl === null) return;
                      if (newTitle.trim() && newUrl.trim()) {
                         const newLinks = [...customLinks];
                         newLinks[idx] = { ...newLinks[idx], title: newTitle.trim(), url: newUrl.trim() };
                         setCustomLinks(newLinks);
                         try { localStorage.setItem('sb_customLinks', JSON.stringify(newLinks)); } catch {}
                      }
                    }} style={{ fontSize:'10px', color:'#64748b', cursor:'pointer', background:'#f1f5f9', border:'none', padding:'2px 6px', borderRadius:'4px', flexShrink:0 }}>編集</button>
                    <button onClick={() => {
                      if (confirm('このリンクを削除しますか？')) {
                        const newLinks = customLinks.filter((_, i) => i !== idx);
                        setCustomLinks(newLinks);
                        try { localStorage.setItem('sb_customLinks', JSON.stringify(newLinks)); } catch {}
                      }
                    }} style={{ fontSize:'10px', color:'#ef4444', cursor:'pointer', background:'#fff1f2', border:'none', padding:'2px 6px', borderRadius:'4px', flexShrink:0 }}>削除</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* フォルダ管理 */}"""

content = link_panel_regex.sub(new_link_panel, content)

with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("done")
