const apiBase = "/api";

const state = {
  libraries: [],
  currentLibrary: null,
  media: [],
  tags: [],
  selected: new Set(),
  detail: null,
};

const elements = {
  librarySelect: document.getElementById("librarySelect"),
  createLibraryBtn: document.getElementById("createLibraryBtn"),
  uploadBtn: document.getElementById("uploadBtn"),
  fileInput: document.getElementById("fileInput"),
  gallery: document.getElementById("gallery"),
  galleryItemTemplate: document.getElementById("galleryItemTemplate"),
  searchInput: document.getElementById("searchInput"),
  tagFilter: document.getElementById("tagFilter"),
  takenFrom: document.getElementById("takenFrom"),
  takenTo: document.getElementById("takenTo"),
  sortSelect: document.getElementById("sortSelect"),
  deleteSelectedBtn: document.getElementById("deleteSelectedBtn"),
  downloadSelectedBtn: document.getElementById("downloadSelectedBtn"),
  modal: document.getElementById("detailModal"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  detailPreview: document.getElementById("detailPreview"),
  detailTitle: document.getElementById("detailTitle"),
  metadataList: document.getElementById("metadataList"),
  tagEditorInput: document.getElementById("tagEditorInput"),
  saveTagsBtn: document.getElementById("saveTagsBtn"),
  deleteMediaBtn: document.getElementById("deleteMediaBtn"),
  downloadMediaBtn: document.getElementById("downloadMediaBtn"),
};

document.addEventListener("DOMContentLoaded", () => {
  elements.createLibraryBtn.addEventListener("click", onCreateLibrary);
  elements.librarySelect.addEventListener("change", onSelectLibrary);
  elements.uploadBtn.addEventListener("click", () => elements.fileInput.click());
  elements.fileInput.addEventListener("change", onUploadFiles);
  elements.searchInput.addEventListener("input", debounce(reloadMedia, 300));
  elements.tagFilter.addEventListener("change", reloadMedia);
  elements.takenFrom.addEventListener("change", reloadMedia);
  elements.takenTo.addEventListener("change", reloadMedia);
  elements.sortSelect.addEventListener("change", reloadMedia);
  elements.deleteSelectedBtn.addEventListener("click", onDeleteSelected);
  elements.downloadSelectedBtn.addEventListener("click", onDownloadSelected);
  elements.closeModalBtn.addEventListener("click", closeModal);
  elements.saveTagsBtn.addEventListener("click", onSaveTags);
  elements.deleteMediaBtn.addEventListener("click", onDeleteMedia);
  elements.downloadMediaBtn.addEventListener("click", onDownloadMedia);
  elements.modal.addEventListener("click", (event) => {
    if (event.target === elements.modal) {
      closeModal();
    }
  });

  loadLibraries();
});

async function loadLibraries() {
  try {
    const response = await fetch(`${apiBase}/libraries`);
    if (!response.ok) throw new Error("Failed to load libraries");
    state.libraries = await response.json();
    renderLibraryOptions();
    if (state.libraries.length > 0) {
      const first = state.libraries[0];
      state.currentLibrary = first.id;
      elements.librarySelect.value = first.id;
      await Promise.all([loadTags(), reloadMedia()]);
    }
  } catch (error) {
    console.error(error);
    alert("Unable to load libraries. Create one to get started.");
  }
}

function renderLibraryOptions() {
  elements.librarySelect.innerHTML = "";
  state.libraries.forEach((library) => {
    const option = document.createElement("option");
    option.value = library.id;
    option.textContent = library.name;
    elements.librarySelect.appendChild(option);
  });
}

async function onCreateLibrary() {
  const name = prompt("Library name");
  if (!name) return;
  try {
    const response = await fetch(`${apiBase}/libraries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) throw new Error("Failed to create library");
    const library = await response.json();
    state.libraries.push(library);
    renderLibraryOptions();
    state.currentLibrary = library.id;
    elements.librarySelect.value = library.id;
    await Promise.all([loadTags(), reloadMedia()]);
  } catch (error) {
    console.error(error);
    alert("Unable to create library");
  }
}

async function onSelectLibrary() {
  state.currentLibrary = elements.librarySelect.value;
  state.selected.clear();
  updateSelectionState();
  await Promise.all([loadTags(), reloadMedia()]);
}

async function loadTags() {
  if (!state.currentLibrary) return;
  const response = await fetch(`${apiBase}/libraries/${state.currentLibrary}/tags`);
  if (!response.ok) return;
  state.tags = await response.json();
  renderTagFilter();
}

function renderTagFilter() {
  elements.tagFilter.innerHTML = "";
  state.tags.forEach((tag) => {
    const option = document.createElement("option");
    option.value = tag.name;
    option.textContent = tag.name;
    elements.tagFilter.appendChild(option);
  });
}

async function reloadMedia() {
  if (!state.currentLibrary) return;
  const params = new URLSearchParams();
  const search = elements.searchInput.value.trim();
  if (search) params.set("search", search);
  const selectedTags = Array.from(elements.tagFilter.selectedOptions).map((option) => option.value);
  selectedTags.forEach((tag) => params.append("tags", tag));
  const takenFrom = elements.takenFrom.value;
  const takenTo = elements.takenTo.value;
  if (takenFrom) params.set("takenFrom", Math.floor(new Date(takenFrom).getTime() / 1000));
  if (takenTo) params.set("takenTo", Math.floor(new Date(takenTo).getTime() / 1000) + 86399);
  const sort = elements.sortSelect.value;
  if (sort) params.set("sort", sort);

  const query = params.toString();
  const url = `${apiBase}/libraries/${state.currentLibrary}/media${query ? `?${query}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    console.error("Failed to load media");
    return;
  }
  state.media = await response.json();
  state.selected.clear();
  renderGallery();
  updateSelectionState();
}

function renderGallery() {
  elements.gallery.innerHTML = "";
  if (state.media.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "This library has no media yet. Upload to get started.";
    elements.gallery.appendChild(empty);
    return;
  }

  state.media.forEach((item) => {
    const node = elements.galleryItemTemplate.content.firstElementChild.cloneNode(true);
    const thumbnailContainer = node.querySelector(".thumbnail");
    const filename = node.querySelector(".filename");
    const infoBtn = node.querySelector(".info-btn");
    const checkbox = node.querySelector(".select-checkbox");

    filename.textContent = item.original_filename;
    checkbox.checked = state.selected.has(item.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.selected.add(item.id);
      } else {
        state.selected.delete(item.id);
      }
      updateSelectionState();
    });

    infoBtn.addEventListener("click", () => openDetail(item.id));
    thumbnailContainer.addEventListener("dblclick", () => openDetail(item.id));

    if (item.media_type === "photo") {
      const img = document.createElement("img");
      img.src = `${apiBase}/libraries/${state.currentLibrary}/media/${item.id}/thumbnail`;
      img.alt = item.original_filename;
      thumbnailContainer.appendChild(img);
    } else if (item.media_type === "video") {
      const video = document.createElement("video");
      video.src = `${apiBase}/libraries/${state.currentLibrary}/media/${item.id}/content`;
      video.muted = true;
      video.loop = true;
      video.autoplay = true;
      video.playsInline = true;
      thumbnailContainer.appendChild(video);
    } else {
      const placeholder = document.createElement("span");
      placeholder.textContent = item.mime_type;
      thumbnailContainer.appendChild(placeholder);
    }

    elements.gallery.appendChild(node);
  });
}

async function onUploadFiles(event) {
  if (!state.currentLibrary) return;
  const files = Array.from(event.target.files || []);
  if (files.length === 0) return;

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  try {
    const response = await fetch(`${apiBase}/libraries/${state.currentLibrary}/media`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("Upload failed");
    event.target.value = "";
    await Promise.all([loadTags(), reloadMedia()]);
  } catch (error) {
    console.error(error);
    alert("Upload failed");
  }
}

function updateSelectionState() {
  const hasSelection = state.selected.size > 0;
  elements.deleteSelectedBtn.disabled = !hasSelection;
  elements.downloadSelectedBtn.disabled = !hasSelection;
}

async function onDeleteSelected() {
  if (!state.currentLibrary || state.selected.size === 0) return;
  if (!confirm(`Delete ${state.selected.size} item(s)?`)) return;

  const ids = Array.from(state.selected);
  try {
    const response = await fetch(`${apiBase}/libraries/${state.currentLibrary}/media/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    if (!response.ok) throw new Error("Failed to delete");
    state.selected.clear();
    await reloadMedia();
  } catch (error) {
    console.error(error);
    alert("Failed to delete items");
  }
}

async function onDownloadSelected() {
  if (!state.currentLibrary || state.selected.size === 0) return;
  await triggerDownload(Array.from(state.selected));
}

async function openDetail(mediaId) {
  if (!state.currentLibrary) return;
  const response = await fetch(`${apiBase}/libraries/${state.currentLibrary}/media/${mediaId}`);
  if (!response.ok) {
    alert("Media not found");
    return;
  }
  const item = await response.json();
  state.detail = item;

  elements.detailTitle.textContent = item.original_filename;
  elements.tagEditorInput.value = item.tags.join(", ");
  renderMetadata(item);
  renderPreview(item);
  elements.modal.classList.remove("hidden");
}

function renderMetadata(item) {
  elements.metadataList.innerHTML = "";
  const metadata = {
    "Media type": item.media_type,
    "Mime type": item.mime_type,
    "Imported": formatTimestamp(item.imported_at),
    "Taken": item.taken_at ? formatTimestamp(item.taken_at) : "Unknown",
    Size: formatBytes(item.size_bytes),
    Dimensions: item.width && item.height ? `${item.width}×${item.height}` : "",
    Camera: [item.camera_make, item.camera_model].filter(Boolean).join(" "),
    Latitude: item.gps_lat ?? "",
    Longitude: item.gps_lon ?? "",
  };

  Object.entries(metadata).forEach(([key, value]) => {
    if (value === "" || value === null || typeof value === "undefined") return;
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    elements.metadataList.appendChild(dt);
    elements.metadataList.appendChild(dd);
  });
}

function renderPreview(item) {
  elements.detailPreview.innerHTML = "";
  if (item.media_type === "photo") {
    const img = document.createElement("img");
    img.src = `${apiBase}/libraries/${state.currentLibrary}/media/${item.id}/content`;
    img.alt = item.original_filename;
    elements.detailPreview.appendChild(img);
  } else if (item.media_type === "video") {
    const video = document.createElement("video");
    video.controls = true;
    video.src = `${apiBase}/libraries/${state.currentLibrary}/media/${item.id}/content`;
    elements.detailPreview.appendChild(video);
  } else {
    const link = document.createElement("a");
    link.href = `${apiBase}/libraries/${state.currentLibrary}/media/${item.id}/content`;
    link.textContent = "Download file";
    link.target = "_blank";
    elements.detailPreview.appendChild(link);
  }
}

function closeModal() {
  state.detail = null;
  elements.modal.classList.add("hidden");
}

async function onSaveTags() {
  if (!state.detail) return;
  const tags = elements.tagEditorInput.value
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);

  try {
    const response = await fetch(
      `${apiBase}/libraries/${state.currentLibrary}/media/${state.detail.id}/tags`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags }),
      }
    );
    if (!response.ok) throw new Error("Failed to save tags");
    state.detail.tags = await response.json();
    await loadTags();
    await reloadMedia();
  } catch (error) {
    console.error(error);
    alert("Failed to save tags");
  }
}

async function onDeleteMedia() {
  if (!state.detail) return;
  if (!confirm("Delete this media?")) return;
  try {
    const response = await fetch(
      `${apiBase}/libraries/${state.currentLibrary}/media/${state.detail.id}`,
      {
        method: "DELETE",
      }
    );
    if (!response.ok) throw new Error("Failed to delete media");
    closeModal();
    await reloadMedia();
  } catch (error) {
    console.error(error);
    alert("Failed to delete media");
  }
}

async function onDownloadMedia() {
  if (!state.detail) return;
  await triggerDownload([state.detail.id]);
}

async function triggerDownload(ids) {
  try {
    const response = await fetch(`${apiBase}/libraries/${state.currentLibrary}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "media-download.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error(error);
    alert("Download failed");
  }
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(null, args), delay);
  };
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value * 1000);
  return date.toLocaleString();
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  let value = bytes;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value < 10 && index > 0 ? 1 : 0)} ${units[index]}`;
}
