import re

with open("public/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Sidebar にドラッグステートを追加
state_anchor = "const [customLinks, setCustomLinks] = useState(() => {"
new_states = """      // リンク集のドラッグ＆ドロップ（長押し対応）用ステート
      const [linkDragState, setLinkDragState] = useState({ isDragging: false, startIndex: null, currentIndex: null });
      const linkTouchTimer = useRef(null);
      const handleLinkTouchStart = (e, index) => {
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        linkTouchTimer.current = setTimeout(() => {
          setLinkDragState({ isDragging: true, startIndex: index, currentIndex: index });
          if (navigator.vibrate) navigator.vibrate(40);
        }, 400);
      };
      const handleLinkTouchMove = (e) => {
        if (!linkDragState.isDragging) {
          clearTimeout(linkTouchTimer.current);
          return;
        }
        e.preventDefault();
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const el = document.elementFromPoint(clientX, clientY);
        const targetItem = el ? el.closest('.custom-link-item') : null;
        if (targetItem && targetItem.dataset.index !== undefined) {
          const newIndex = parseInt(targetItem.dataset.index, 10);
          if (newIndex !== linkDragState.currentIndex) {
            setLinkDragState(prev => ({ ...prev, currentIndex: newIndex }));
          }
        }
      };
      const handleLinkTouchEnd = (e) => {
        clearTimeout(linkTouchTimer.current);
        if (!linkDragState.isDragging) return;
        setLinkDragState(prev => {
          if (prev.startIndex !== null && prev.currentIndex !== null && prev.startIndex !== prev.currentIndex) {
            setCustomLinks(links => {
              const newLinks = [...links];
              const [moved] = newLinks.splice(prev.startIndex, 1);
              newLinks.splice(prev.currentIndex, 0, moved);
              try { localStorage.setItem('sb_customLinks', JSON.stringify(newLinks)); } catch {}
              return newLinks;
            });
          }
          return { isDragging: false, startIndex: null, currentIndex: null };
        });
      };

      const [customLinks, setCustomLinks] = useState(() => {"""

content = content.replace(state_anchor, new_states)

# 2. list item に適用
item_anchor = """<div key={link.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', background:'white', padding:'4px 6px', borderRadius:'6px', border:'1px solid #e2e8f0', boxShadow:'0 1px 2px rgba(0,0,0,0.02)' }}>"""
item_replacement = """<div 
                      key={link.id} 
                      className="custom-link-item" 
                      data-index={idx}
                      onPointerDown={(e) => handleLinkTouchStart(e, idx)}
                      onPointerMove={handleLinkTouchMove}
                      onPointerUp={handleLinkTouchEnd}
                      onPointerCancel={handleLinkTouchEnd}
                      style={{ 
                        display: 'flex', alignItems: 'center', gap: '6px', background:'white', padding:'4px 6px', 
                        borderRadius:'6px', border:'1px solid #e2e8f0', boxShadow:'0 1px 2px rgba(0,0,0,0.02)',
                        transform: linkDragState.isDragging && linkDragState.currentIndex === idx && linkDragState.startIndex !== idx ? 'scale(1.02)' : 'none',
                        opacity: linkDragState.isDragging && linkDragState.startIndex === idx ? 0.5 : 1,
                        transition: 'transform 0.1s, opacity 0.1s',
                        zIndex: linkDragState.isDragging && linkDragState.startIndex === idx ? 10 : 1,
                        position: 'relative',
                        touchAction: 'none' // スクロール防止
                      }}
                    >"""

content = content.replace(item_anchor, item_replacement)

with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("done")
