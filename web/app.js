const statusEl = document.getElementById('status');
const libSelect = document.getElementById('librarySelect');
const newLibraryBtn = document.getElementById('newLibraryBtn');
const uploadInput = document.getElementById('uploadInput');
const typeFilter = document.getElementById('typeFilter');
const searchInput = document.getElementById('searchInput');
const galleryEl = document.getElementById('gallery');
const tagsListEl = document.getElementById('tagsList');
const tagModeEl = document.getElementById('tagMode');
const deleteSelectedBtn = document.getElementById('deleteSelected');
const downloadSelectedBtn = document.getElementById('downloadSelected');

// Modal elements
const modal = document.getElementById('detailModal');
const closeModalBtn = document.getElementById('closeModal');
const viewerEl = document.getElementById('viewer');
const metaEl = document.getElementById('meta');
const mediaTagsEl = document.getElementById('mediaTags');
const newTagNameEl = document.getElementById('newTagName');
const addTagBtn = document.getElementById('addTagBtn');
const deleteOneBtn = document.getElementById('deleteOne');
const downloadOneA = document.getElementById('downloadOne');

let currentLib = null;
let page = 1;
let selected = new Set();
let activeTags = new Set();
let currentDetail = null;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res;
}

async function loadLibraries() {
  const res = await api('/api/libraries');
  const libs = await res.json();
  libSelect.innerHTML = '';
  libs.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.id;
    opt.textContent = `${l.name}`;
    libSelect.appendChild(opt);
  });
  if (!currentLib && libs.length) {
    currentLib = libs[0].id;
    libSelect.value = currentLib;
    renderGallery(true);
    loadTags();
  }
}

async function createLibrary() {
  const name = prompt('Library name?');
  if (!name) return;
  await api('/api/libraries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  await loadLibraries();
}

async function uploadFiles(files) {
  if (!currentLib) return;
  const fd = new FormData();
  for (const f of files) fd.append('files', f);
  try {
    const res = await api(`/api/libraries/${currentLib}/upload`, { method: 'POST', body: fd });
    const json = await res.json();
    statusEl.textContent = `Uploaded ${json.inserted?.length ?? 0} item(s)`;
    await renderGallery(true);
  } catch (e) {
    statusEl.textContent = `Upload failed: ${e}`;
  }
}

async function loadTags() {
  if (!currentLib) return;
  const res = await api(`/api/libraries/${currentLib}/tags`);
  const tags = await res.json();
  tagsListEl.innerHTML = '';
  tags.forEach(t => {
    const span = document.createElement('span');
    span.className = 'tag' + (activeTags.has(t.id) ? ' selected' : '');
    span.textContent = t.name;
    span.onclick = () => {
      if (activeTags.has(t.id)) activeTags.delete(t.id); else activeTags.add(t.id);
      renderGallery(true);
      renderTags(tags);
    };
    tagsListEl.appendChild(span);
  });
}

function renderTags(tags) {
  let idx = 0;
  tagsListEl.childNodes.forEach(node => {
    if (node.classList && node.classList.contains('tag')) {
      const tagId = tags[idx]?.id;
      node.classList.toggle('selected', !!(tagId && activeTags.has(tagId)));
      idx++;
    }
  });
}

async function renderGallery(reset = false) {
  if (!currentLib) return;
  if (reset) {
    page = 1;
    galleryEl.innerHTML = '';
    selected.clear();
  }
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('size', '50');
  params.set('sort', 'newest');
  if (typeFilter.value) params.set('type', typeFilter.value);
  if (searchInput.value) params.set('q', searchInput.value);
  if (activeTags.size) [...activeTags].forEach(t => params.append('tagIds', t));
  params.set('tagMode', tagModeEl.value);
  const res = await api(`/api/libraries/${currentLib}/media?${params.toString()}`);
  const data = await res.json();
  statusEl.textContent = `Total: ${data.total}`;
  data.items.forEach(item => {
    const tile = document.createElement('div');
    tile.className = 'tile';
    const thumb = document.createElement(item.type === 'video' ? 'video' : 'img');
    thumb.src = `/api/libraries/${currentLib}/media/${item.id}/thumb`;
    if (item.type === 'video') thumb.muted = true;
    tile.appendChild(thumb);
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = item.original_filename;
    tile.appendChild(meta);
    tile.onclick = (e) => {
      if (e.shiftKey || e.ctrlKey) {
        if (selected.has(item.id)) selected.delete(item.id); else selected.add(item.id);
        tile.classList.toggle('selected');
      } else {
        openDetail(item);
      }
    };
    galleryEl.appendChild(tile);
  });
}

async function openDetail(item) {
  currentDetail = item;
  const detailRes = await api(`/api/libraries/${currentLib}/media/${item.id}`);
  const detail = await detailRes.json();
  viewerEl.innerHTML = '';
  const playRes = await api(`/api/libraries/${currentLib}/media/${item.id}/play`);
  const play = await playRes.json();
  if (playRes.status === 202) {
    // preparing proxy, poll a few times
    for (let i = 0; i < 8; i++) {
      await new Promise(r => setTimeout(r, 1000));
      const tryRes = await fetch(`/api/libraries/${currentLib}/media/${item.id}/play`);
      if (tryRes.ok) {
        const tryJson = await tryRes.json();
        if (tryJson.url) {
          viewerEl.innerHTML = '';
          const v = document.createElement('video');
          v.controls = true;
          v.src = tryJson.url;
          viewerEl.appendChild(v);
          break;
        }
      }
    }
  }
  if (play.kind === 'image') {
    const img = document.createElement('img');
    img.src = play.url;
    viewerEl.appendChild(img);
  } else if (play.kind === 'video' && play.url) {
    const v = document.createElement('video');
    v.controls = true;
    v.src = play.url;
    viewerEl.appendChild(v);
  }
  metaEl.textContent = `${detail.original_filename} • ${(detail.width||'')}${detail.width?'x':''}${detail.height||''}`;
  renderMediaTags(detail.tags || []);
  downloadOneA.href = `/api/libraries/${currentLib}/media/${item.id}/download`;
  modal.classList.remove('hidden');
}

function renderMediaTags(tags) {
  mediaTagsEl.innerHTML = '';
  tags.forEach(t => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.textContent = t.name;
    span.title = 'Click to remove';
    span.onclick = async () => {
      await api(`/api/libraries/${currentLib}/media/${currentDetail.id}/tags/${t.id}`, { method: 'DELETE' });
      const d = await (await api(`/api/libraries/${currentLib}/media/${currentDetail.id}`)).json();
      renderMediaTags(d.tags || []);
      loadTags();
      renderGallery(true);
    };
    mediaTagsEl.appendChild(span);
  });
}

addTagBtn.addEventListener('click', async () => {
  const name = (newTagNameEl.value || '').trim();
  if (!name || !currentDetail) return;
  await api(`/api/libraries/${currentLib}/tags?name=${encodeURIComponent(name)}`, { method: 'POST' });
  const all = await (await api(`/api/libraries/${currentLib}/tags`)).json();
  const tag = all.find(t => t.name.toLowerCase() === name.toLowerCase());
  if (tag) await api(`/api/libraries/${currentLib}/media/${currentDetail.id}/tags`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tagIds: [tag.id] }) });
  const d = await (await api(`/api/libraries/${currentLib}/media/${currentDetail.id}`)).json();
  renderMediaTags(d.tags || []);
  newTagNameEl.value = '';
  await loadTags();
  await renderGallery(true);
});

deleteOneBtn.addEventListener('click', async () => {
  if (!currentDetail) return;
  await api(`/api/libraries/${currentLib}/media/${currentDetail.id}`, { method: 'DELETE' });
  modal.classList.add('hidden');
  await renderGallery(true);
});

closeModalBtn.addEventListener('click', () => modal.classList.add('hidden'));

deleteSelectedBtn.addEventListener('click', async () => {
  if (!selected.size) return;
  await api(`/api/libraries/${currentLib}/media/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
  selected.clear();
  await renderGallery(true);
});

downloadSelectedBtn.addEventListener('click', async () => {
  if (!selected.size) return;
  // simple redirect with POST is tricky; open batch via fetch and blob
  const res = await api(`/api/libraries/${currentLib}/media/batch-download`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'media.zip';
  a.click();
  URL.revokeObjectURL(url);
});

libSelect.addEventListener('change', () => { currentLib = libSelect.value; renderGallery(true); loadTags(); });
newLibraryBtn.addEventListener('click', createLibrary);
uploadInput.addEventListener('change', (e) => uploadFiles(e.target.files));
typeFilter.addEventListener('change', () => renderGallery(true));
searchInput.addEventListener('change', () => renderGallery(true));
tagModeEl.addEventListener('change', () => renderGallery(true));

(async function init() {
  try {
    const res = await api('/api/health');
    const json = await res.json();
    statusEl.textContent = `OK – libraries root: ${json.libraries_root}`;
    await loadLibraries();
    await loadTags();
  } catch (e) {
    statusEl.textContent = 'Server not reachable';
  }
})();


