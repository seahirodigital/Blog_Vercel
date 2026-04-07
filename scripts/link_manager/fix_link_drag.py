import re

with open("public/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Pointer系ステートをHTML5 DnD系ステートに置換
old_state_pattern = re.compile(r"// リンク集のドラッグ＆ドロップ（長押し対応）用ステート.*?const \[customLinks", re.DOTALL)
new_state = """// リンク集のドラッグ＆ドロップ（HTML5対応）用ステート
      const [linkDragState, setLinkDragState] = useState({ isDragging: false, startIndex: null, overIndex: null });
      const handleDragStartLink = (e, index) => {
        setLinkDragState({ isDragging: true, startIndex: index, overIndex: index });
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', index);
        if (navigator.vibrate) navigator.vibrate(40);
      };
      const handleDragOverLink = (e, index) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (linkDragState.overIndex !== index) {
          setLinkDragState(prev => ({ ...prev, overIndex: index }));
        }
      };
      const handleDropLink = (e, targetIndex) => {
        e.preventDefault();
        const { startIndex } = linkDragState;
        if (startIndex !== null && startIndex !== targetIndex) {
          setCustomLinks(links => {
            const newLinks = [...links];
            const [moved] = newLinks.splice(startIndex, 1);
            newLinks.splice(targetIndex, 0, moved);
            try { localStorage.setItem('sb_customLinks', JSON.stringify(newLinks)); } catch {}
            return newLinks;
          });
        }
        setLinkDragState({ isDragging: false, startIndex: null, overIndex: null });
      };
      const handleDragEndLink = () => {
        setLinkDragState({ isDragging: false, startIndex: null, overIndex: null });
      };

      const [customLinks"""

content = old_state_pattern.sub(new_state, content)

# 2. JSX部分の置換
old_jsx_pattern = re.compile(r'<div \s*key={link\.id}\s*className="custom-link-item".*?draggable=\{false\}.*?onDragStart=\{\(e\) => e\.preventDefault\(\)\}.*?<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2\.5" style=\{\{flexShrink:0\}\}>', re.DOTALL)

# もし直前の置換でaタグにdraggableとonDragStartを入れたので、もう一度広くマッチさせる
old_jsx_pattern2 = re.compile(r'<div \s*key={link\.id}\s*className="custom-link-item".*?<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2\.5" style=\{\{flexShrink:0\}\}>', re.DOTALL)

new_jsx = """<div 
                      key={link.id} 
                      className="custom-link-item" 
                      draggable={true}
                      onDragStart={(e) => handleDragStartLink(e, idx)}
                      onDragOver={(e) => handleDragOverLink(e, idx)}
                      onDrop={(e) => handleDropLink(e, idx)}
                      onDragEnd={handleDragEndLink}
                      style={{ 
                        display: 'flex', alignItems: 'center', gap: '6px', background:'white', padding:'4px 6px', 
                        borderRadius:'6px', border: linkDragState.overIndex === idx && linkDragState.startIndex !== idx ? '1px dashed #7C4DFF' : '1px solid #e2e8f0', 
                        boxShadow:'0 1px 2px rgba(0,0,0,0.02)',
                        opacity: linkDragState.startIndex === idx ? 0.4 : 1,
                        transition: 'border 0.2s, opacity 0.2s',
                        cursor: 'grab'
                      }}
                    >
                      <div 
                        style={{ cursor: 'grab', display: 'flex', alignItems: 'center', padding: '2px 4px', color: '#cbd5e1' }}
                        title="ここを掴んでドラッグして並び替え"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M8 6h8M8 12h8M8 18h8"/></svg>
                      </div>
                      <a
                        href={link.url}
                        target={link.url.startsWith('/') ? '_self' : '_blank'}
                        rel="noopener noreferrer"
                        draggable={false}
                        onDragStart={(e) => e.preventDefault()}
                        onClick={(e) => {
                           if (link.url.startsWith('/')) {
                             e.preventDefault();
                             setShowLinkPicker(false);
                             if (typeof onMobileClose === 'function') onMobileClose();
                             window.location.assign(link.url);
                           }
                        }}
                        className="flex items-center gap-2 text-[11px] text-slate-600 hover:text-[#7C4DFF] hover:bg-purple-50 rounded-md px-1.5 py-1 transition-all"
                        style={{ textDecoration: 'none', flex: 1, minWidth: 0, userSelect: 'none' }}
                        title={link.url}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{flexShrink:0, display:'none'}}>"""

# パターンに合致するかどうか確認
if old_jsx_pattern2.search(content):
    content = old_jsx_pattern2.sub(new_jsx, content)
else:
    print("JSX Regex failed!")

with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("done")
