# Open Library Format (OLF)

*A native desktop suite for managing self‑contained libraries for Documents, Photos, Movies/TV, Music, Projects, etc. Entirely offline with optional, decentralized sync. Libraries are portable bundles; albums/collections can export as independent libraries; multiple libraries can be opened together in merged views.*

*C++/Qt‑Oriented Architecture (Local‑first & Native)*

---
###### Current Ideas and brainstorming:
---

## Architecture Overview

**1) LibraryManager (Main Application)**
* Native desktop application that lists libraries, creates new ones, opens multiple at once, and connects to remote libraries when networking is enabled.
* Selecting a **Library Type** at creation time (Photo, Movie/TV, Music, Documents, etc.) chooses an **Engine** that defines schema, behaviors, and UI affordances for that type.

**2) Library Engines (modular)**

* Each engine implements: on‑disk layout, metadata schema (SQLite), scanner/indexer, and type‑specific UI panels.
* Engines are discoverable plug‑ins. Third parties can add engines without changing the core.

**3) Self‑contained Libraries**

* Each library is a portable bundle (folder or single‑file archive) that holds originals, thumbnails, metadata DB, and edit data.
* **Albums/Collections** are many‑to‑many (one item can appear in multiple). Exporting an album/collection creates a **new library** that may include multiple albums and its own people/tags DB, no dependency on the source library.

**4) Multi‑Library Workspace**

* The Manager can open N libraries concurrently. Views (e.g., Photos timeline) show **merged results** across libraries while each library’s DB remains isolated. No global DB is required; results are composed at runtime.

---

## Tech Stack (C++/Qt)

**Language & UI**

* **C++20** (or C++17 for older toolchains).
* **Qt 6 LTS (Widgets or QML)** for cross‑platform native UI, file dialogs, file watching, image I/O helpers, and internationalization.

**Core libs**

* **SQLite** (WAL mode) for each library’s metadata DB.
* **Exiv2** for EXIF/XMP; **libjpeg‑turbo**, **libpng**, **libtiff**, **libraw** for image formats.
* **fmt** and **spdlog** for logging; **OpenMP** or **QtConcurrent** for parallel tasks.
* Platform file watchers (inotify/FSEvents/ReadDirectoryChangesW) via Qt or small native shims.

**Build & packaging**

* **CMake** project; dependency management via **vcpkg** or **Conan**.
* Installers: Windows (MSIX/Wix), macOS (signed .dmg), Linux (AppImage/Flatpak).

**Licensing**

* Project code under a permissive license (**Apache‑2.0** or **MPL‑2.0**).
* Link to **Qt under LGPL** via dynamic linking; provide license text and offer object files for relinking if needed.
* All third‑party libs chosen for OSS‑friendly licenses; avoid copyleft taint in the core unless explicitly desired.

\[Comment 1] *Confirm the exact license combo (e.g., Apache‑2.0 + Qt LGPL + dynamic linking) and note any static‑link exceptions. This keeps the project open‑source and free to use while avoiding Qt commercial terms.*

---

## On‑Disk Library (per‑engine)

**Directory layout (folder; can be archived to a single file for transport):**

```
<LibraryName>.olf/
  manifest.json            # identity, type, engine version, features
  meta.db                  # SQLite for this library only (WAL enabled)
  objects/                 # originals & derived, content‑addressed
  thumbs/                  # caches/derivatives
  edits/                   # parametric edit stacks (JSON or binary)
  indexes/                 # FTS, thumbnail manifests
  export/                  # (optional) staging for album/collection export
  logs/                    # operation journal for recovery & sync
```

**Library Manifest:**

```json
{
  "olf_version": 1,
  "library_uuid": "8b3f…",
  "engine": {
    "type": "photos",
    "engine_id": "olf-photos",
    "engine_version": 1
  },
  "created_utc": "2025-09-09T00:00:00Z",
  "features": {
    "edits_parametric": true,
    "smart_collections": true,
    "encryption": false
  },
  "provenance": {
    "subset_of": null,
    "export_filter": null
  },
  "paths": {
    "db": "meta.db",
    "objects": "objects/",
    "thumbs": "thumbs/",
    "edits": "edits/"
  }
}
```

---

## Photo Engine Schema (SQLite) - albums as views

**Design principles:**
- Assets stored once; albums/tags/people are metadata views
- Exports copy assets + dependent metadata to new library
- All identifiers are UUIDs (RFC 4122) stored as TEXT
- Column naming: `entity_uuid` pattern, no integer PKs

```sql
CREATE TABLE assets (
  asset_uuid TEXT PRIMARY KEY,
  object_hash TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  ext TEXT,
  width INTEGER, height INTEGER,
  captured_at_utc TEXT,               -- ISO8601
  imported_at_utc TEXT NOT NULL,
  source_uri TEXT,
  deleted INTEGER DEFAULT 0
);

CREATE TABLE albums (
  album_uuid TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  kind TEXT DEFAULT 'static',         -- 'static'|'smart'
  filter_json TEXT,
  created_utc TEXT NOT NULL
);

CREATE TABLE album_items (
  album_uuid TEXT NOT NULL,
  asset_uuid TEXT NOT NULL,
  position INTEGER,
  added_utc TEXT NOT NULL,
  PRIMARY KEY (album_uuid, asset_uuid)
);

CREATE TABLE tags (
  tag_uuid TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  parent_tag_uuid TEXT
);

CREATE TABLE asset_tags (
  asset_uuid TEXT NOT NULL,
  tag_uuid TEXT NOT NULL,
  PRIMARY KEY (asset_uuid, tag_uuid)
);

CREATE TABLE people (
  person_uuid TEXT PRIMARY KEY,
  display_name TEXT NOT NULL
);

CREATE TABLE faces (
  face_uuid TEXT PRIMARY KEY,
  asset_uuid TEXT NOT NULL,
  person_uuid TEXT,
  bbox TEXT NOT NULL,
  confidence REAL
);

CREATE TABLE edits (
  edit_uuid TEXT PRIMARY KEY,
  asset_uuid TEXT NOT NULL,
  stack_json TEXT NOT NULL,
  created_utc TEXT NOT NULL
);

CREATE VIRTUAL TABLE search USING fts5(asset_uuid, title, description, tags);
```

**Performance consideration:** Store timestamps as integer epoch microseconds for fast range queries. ISO8601 strings can be computed views for readability.

---

## Manager: Multi‑Library Composition

* Keep an in‑memory **workspace index** that represents the union of the currently opened libraries (read‑only projections over each SQLite DB).
* UI shows merged views (e.g., Photo timeline across two libraries) by executing the same query against each DB and stitching results.
* Batch operations route to the selected library’s engine; cross‑library operations are repeated single‑library operations.

**Performance optimization needed:** Per-session ephemeral index to avoid O(N) scans on every UI scroll. Invalidate on library modifications.

---

## Edits & Versioning (Photos)

**Edit Stack Architecture:**
- Originals immutable; edits stored as parametric operations
- Virtual copies = additional edit stacks referencing same original
- Rendered derivatives cached by `(original_hash + stack_hash + output_size)`

**Critical requirement:** Versioned edit-stack schema with canonical serialization ensures deterministic hashing across platforms and safe cache reuse.

---

## Local‑only MVP (priorities)

1. **Manager**: create/open libraries; open multiple concurrently; merged photo timeline.
2. **Photo Engine v1**: import files; EXIF read; thumbnails; albums; tags; simple search; non‑destructive edits (crop/rotate/exposure).
3. **Album → Library export**: share a subset as an independent portable library.
4. **Documents Engine v1**: flat storage + tags as collections; full‑text index later.
5. Packaging: single‑folder library + “pack to archive” for sharing/backup.

Stretch: Smart Albums; People (offline face detect/cluster); per‑library encryption.

---

## Networking (later; design constraints only)

* **No central service requirement.** Must work on LAN or across the internet with user‑provided infra only.
* **Pluggable transports:**

  * WireGuard‑style direct mesh (user supplies endpoint keys; STUN/TURN optional, not mandatory).
  * LAN discovery via mDNS/UDP broadcast.
  * **BitTorrent distribution mode** for read‑only or append‑only libraries: magnet links for snapshot releases; optional signed update manifests for deltas; streaming of large media when partially available.
* Auth via public‑key identities; signed operation logs; no SaaS login needed.

**Architecture decision:** Separate read-only distribution (BitTorrent snapshots) from multi-writer replication (conflict resolution required). Different use cases need different consistency guarantees.

---

## Design Benefits

- **Local-first:** No web dependencies, works offline
- **Portable:** Libraries are self-contained units for backup/sharing
- **Modular:** Engine system allows specialized evolution per media type
- **Decentralized:** Future sync remains optional and user-controlled

---

## Next Decisions Required

**Technical choices:**
- C++ standard: C++17 (broader compatibility) vs C++20 (better features)
- Qt framework: Widgets (stable, familiar) vs QML (modern, declarative)
- Export strategy: copy-on-write (space efficient) vs copy-by-value (simpler)

**Architecture decisions:**
- Plugin ABI: stable C interface vs C++ (easier but fragile)
- Image processing: CPU-only first vs GPU acceleration from start
- Packaging targets: prioritize which platforms for initial release
