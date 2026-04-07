const urlStr = "https://onedrive.live.com/?id=%2Fpersonal%2Fffcc26dedbba4e70%2FDocuments%2F%E9%96%8B%E7%99%BA%2FBlog%5FVercel%2FTEST%2Fseo%5Ffactory%2Foutput&viewid=d481e60b%2D6260%2D423d%2D994d%2D3c53058bc06d&view=0";
const u = new URL(urlStr);
const folderId = u.searchParams.get('id');
console.log("folderId:", folderId);

if (folderId && folderId.startsWith('/')) {
  const match = folderId.match(/\/Documents\/(.+)$/i);
  if (match) {
    const path = encodeURIComponent(match[1]);
    console.log("path:", path);
  } else {
    console.log("match failed");
  }
}
