const form = document.querySelector("#track-form");
const message = document.querySelector("#form-message");
const stateJson = document.querySelector("#state-json");
const connection = document.querySelector("#connection");
const togglePlay = document.querySelector("#toggle-play");
const visualForm = document.querySelector("#visual-form");
const visualMessage = document.querySelector("#visual-message");
const visualPreviewArt = document.querySelector("#visual-preview-art");
const visualPreviewVideo = document.querySelector("#visual-preview-video");
const sceneMessage = document.querySelector("#scene-message");
const schedulerForm = document.querySelector("#scheduler-form");
const schedulerMessage = document.querySelector("#scheduler-message");
const artistEventForm = document.querySelector("#artist-event-form");
const eventMessage = document.querySelector("#event-message");
const eventTableBody = document.querySelector("#event-table-body");
const eventMatchStatus = document.querySelector("#event-match-status");
const displayItemForm = document.querySelector("#display-item-form");
const displayItemMessage = document.querySelector("#display-item-message");
const displayItemTableBody = document.querySelector("#display-item-table-body");
const displayItemImagePreview = document.querySelector("#display-item-image-preview");

const playlist = [
  { title: "Subterranean Homesick Alien", artist: "Radiohead", album: "OK Computer", duration: 267 },
  { title: "Friday Morning", artist: "Khruangbin", album: "The Universe Smiles Upon You", duration: 158 },
  { title: "People Everywhere (Still Alive)", artist: "Khruangbin", album: "The Universe Smiles Upon You", duration: 472 },
  { title: "A Walk", artist: "Tycho", album: "Dive", duration: 316 },
];

let latestState = null;
let playlistIndex = 0;
let formInitialized = false;
let visualFormInitialized = false;
let schedulerFormInitialized = false;
let artistEvents = [];
let displayItems = [];
let displayItemPreviewObjectUrl = "";

function setConnection(status) {
  connection.textContent = status === "online" ? "LIVE" : "RECONNECTING";
  connection.classList.toggle("is-online", status === "online");
  connection.classList.toggle("is-offline", status !== "online");
}

function formatTime(value) {
  if (!Number.isFinite(value)) return "—";
  const seconds = Math.floor(value);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function renderVisualPreview(mode, visualUrl, track = {}) {
  const imageUrl = mode === "album_cover" ? String(track.cover_url || "") : String(visualUrl || "");
  const useVideo = mode === "video" && Boolean(visualUrl);
  visualPreviewVideo.style.display = useVideo ? "block" : "none";
  visualPreviewArt.style.display = useVideo ? "none" : "grid";

  if (useVideo) {
    if (visualPreviewVideo.getAttribute("src") !== visualUrl) {
      visualPreviewVideo.src = visualUrl;
      visualPreviewVideo.load();
    }
    visualPreviewVideo.play().catch(() => {});
    return;
  }

  visualPreviewVideo.pause();
  visualPreviewArt.style.backgroundImage = imageUrl
    ? `url(${JSON.stringify(imageUrl)})`
    : "";
  visualPreviewArt.querySelector("span").style.display = imageUrl ? "none" : "block";
}

function render(state) {
  latestState = state;
  const track = state.track || {};
  document.querySelector("#revision").textContent = `REV ${state.revision ?? "—"}`;
  document.querySelector("#display-mode").textContent = state.display?.mode || "—";
  document.querySelectorAll("[data-scene-mode]").forEach((button) => {
    button.classList.toggle(
      "is-active",
      state.display?.control_mode === "manual" && button.dataset.sceneMode === state.display?.mode
    );
  });
  document.querySelector("[data-control-mode='auto']").classList.toggle(
    "is-active",
    state.display?.control_mode === "auto"
  );
  if (state.display?.control_mode === "auto" && state.display?.insert_source === "scheduler") {
    eventMatchStatus.textContent = `自动插播：${state.display.display_item_name || "豆子／活动"} · ${state.display.insert_duration_seconds || "—"} 秒。结束后回到最新曲目。`;
    eventMatchStatus.classList.add("has-match");
  } else if (state.display?.control_mode === "auto" && state.display?.artist_event_id) {
    eventMatchStatus.textContent = `自动匹配：${state.display.matched_artist || track.artist || "当前音乐人"} → ${state.content?.artist_notice?.venue || "演出提示"} · ${state.content?.artist_notice?.date_label || ""}`;
    eventMatchStatus.classList.add("has-match");
  } else if (state.display?.control_mode === "auto") {
    eventMatchStatus.textContent = `自动匹配：${track.artist || "当前音乐人"} 未命中有效演出，显示普通播放界面。`;
    eventMatchStatus.classList.remove("has-match");
  } else {
    eventMatchStatus.textContent = `当前为手动预览：${state.display?.mode || "—"}。完成后请恢复自动匹配。`;
    eventMatchStatus.classList.remove("has-match");
  }
  document.querySelector("#source-mode").textContent = state.config?.source_mode || "—";
  document.querySelector("#platform").textContent = state.system?.platform || "—";
  document.querySelector("#source-status").textContent = `${state.system?.connection || "—"} · ${state.system?.message || ""}`;
  document.querySelector("#player-app").textContent = track.app_name || "—";
  document.querySelector("#current-track").textContent = `${track.title || "—"} — ${track.artist || "—"}`;
  document.querySelector("#current-playback").textContent = `${track.playback_status || "—"} · ${formatTime(track.position)} / ${formatTime(track.duration)}`;
  document.querySelector("#position-accuracy").textContent = track.position_accuracy || "—";
  document.querySelector("#updated-at").textContent = state.updated_at || "—";
  const visualMode = state.config?.visual_mode || "album_cover";
  const visualUrl = state.config?.visual_url || "";
  document.querySelector("#current-visual-mode").textContent = visualMode.replace("_", " ").toUpperCase();
  stateJson.textContent = JSON.stringify(state, null, 2);
  togglePlay.textContent = track.is_playing ? "暂停" : "播放";

  if (!formInitialized) {
    form.elements.title.value = track.title || "";
    form.elements.artist.value = track.artist || "";
    form.elements.album.value = track.album || "";
    form.elements.position.value = track.position ?? "";
    form.elements.duration.value = track.duration ?? "";
    formInitialized = true;
  }

  if (!visualFormInitialized) {
    visualForm.elements.visual_mode.value = visualMode;
    visualForm.elements.visual_url.value = visualUrl;
    visualFormInitialized = true;
  }
  if (!schedulerFormInitialized) {
    schedulerForm.elements.auto_insert_enabled.checked = Boolean(state.config?.auto_insert_enabled);
    schedulerForm.elements.insert_min_interval_minutes.value = state.config?.insert_min_interval_minutes ?? 20;
    schedulerForm.elements.non_music_hourly_max_percent.value = state.config?.non_music_hourly_max_percent ?? 10;
    schedulerFormInitialized = true;
  }
  renderVisualPreview(visualMode, visualUrl, track);
}

async function postJSON(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `request failed: ${response.status}`);
  return result;
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `request failed: ${response.status}`);
  return result;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  try {
    await postJSON("/api/mock/track", {
      title: String(data.get("title") || ""),
      artist: String(data.get("artist") || ""),
      album: String(data.get("album") || ""),
      position: data.get("position") === "" ? null : Number(data.get("position")),
      duration: data.get("duration") === "" ? null : Number(data.get("duration")),
    });
    message.textContent = "已推送到显示端。";
  } catch (error) {
    message.textContent = error.message;
  }
});

visualForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  let mode = visualForm.elements.visual_mode.value;
  let visualUrl = visualForm.elements.visual_url.value.trim();
  const file = visualForm.elements.media_file.files[0];

  try {
    if (file) {
      visualMessage.textContent = "正在上传素材…";
      const uploadResponse = await fetch("/api/media", {
        method: "PUT",
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      const upload = await uploadResponse.json();
      if (!uploadResponse.ok) {
        throw new Error(upload.error || `upload failed: ${uploadResponse.status}`);
      }
      visualUrl = upload.url;
      mode = upload.media_type;
      visualForm.elements.visual_mode.value = mode;
      visualForm.elements.visual_url.value = visualUrl;
    }

    if (mode !== "album_cover" && !visualUrl) {
      throw new Error("自定义图片或视频需要先选择文件，或填写素材地址。");
    }
    await postJSON("/api/config", {
      visual_mode: mode,
      visual_url: visualUrl,
    });
    visualMessage.textContent = mode === "album_cover"
      ? "已切换为跟随专辑封面。"
      : "左侧视觉已更新。";
    visualForm.elements.media_file.value = "";
  } catch (error) {
    visualMessage.textContent = error.message;
  }
});

visualForm.addEventListener("input", () => {
  if (!latestState) return;
  renderVisualPreview(
    visualForm.elements.visual_mode.value,
    visualForm.elements.visual_url.value.trim(),
    latestState.track || {}
  );
});

document.querySelector(".scene-buttons").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  try {
    if (button.dataset.controlMode === "auto") {
      await postJSON("/api/display", { control_mode: "auto" });
      sceneMessage.textContent = "已恢复自动运行：演出匹配和自然结束插播均按规则执行。";
    } else if (button.dataset.sceneMode) {
      await postJSON("/api/display", { mode: button.dataset.sceneMode, control_mode: "manual" });
      sceneMessage.textContent = `已切换到“${button.textContent.trim()}”手动预览。`;
    }
  } catch (error) {
    sceneMessage.textContent = error.message;
  }
});

schedulerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await postJSON("/api/config", {
      auto_insert_enabled: schedulerForm.elements.auto_insert_enabled.checked,
      insert_min_interval_minutes: Number(schedulerForm.elements.insert_min_interval_minutes.value || 0),
      non_music_hourly_max_percent: Number(schedulerForm.elements.non_music_hourly_max_percent.value || 0),
    });
    schedulerMessage.textContent = "曲间插播规则已保存。";
  } catch (error) {
    schedulerMessage.textContent = error.message;
  }
});

function formPayload(targetForm) {
  return Object.fromEntries(
    [...new FormData(targetForm).entries()].map(([key, value]) => [key, String(value)])
  );
}

function resetArtistEventForm() {
  artistEventForm.reset();
  artistEventForm.elements.id.value = "";
  artistEventForm.elements.enabled.checked = true;
  artistEventForm.elements.priority.value = "0";
  artistEventForm.elements.eyebrow.value = "ARTIST IN TOWN";
  artistEventForm.elements.footer.value = "UPCOMING PERFORMANCE · VERIFIED LISTING";
  document.querySelector("#event-form-title").textContent = "新增演出";
  eventMessage.textContent = "";
}

function editArtistEvent(record) {
  resetArtistEventForm();
  Object.entries(record).forEach(([key, value]) => {
    const field = artistEventForm.elements[key];
    if (!field) return;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = Array.isArray(value) ? value.join(", ") : value ?? "";
  });
  document.querySelector("#event-form-title").textContent = `编辑：${record.artist_name}`;
  artistEventForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cell(text, className = "") {
  const element = document.createElement("td");
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function renderArtistEvents() {
  eventTableBody.replaceChildren();
  if (!artistEvents.length) {
    const row = document.createElement("tr");
    const empty = cell("还没有演出记录。新增后，系统会自动匹配当前音乐人。", "empty-cell");
    empty.colSpan = 5;
    row.append(empty);
    eventTableBody.append(row);
    return;
  }
  artistEvents.forEach((record) => {
    const row = document.createElement("tr");
    const status = document.createElement("span");
    status.className = `status-chip ${record.enabled ? "is-enabled" : ""}`;
    status.textContent = record.enabled ? "启用" : "停用";
    const statusCell = document.createElement("td");
    statusCell.append(status);

    const artistCell = document.createElement("td");
    const artistName = document.createElement("strong");
    artistName.textContent = record.artist_name;
    const aliases = document.createElement("small");
    aliases.textContent = record.aliases.length ? record.aliases.join(" · ") : "无别名";
    artistCell.append(artistName, aliases);

    const eventCell = document.createElement("td");
    eventCell.append(document.createTextNode(`${record.date_label} · ${record.time_label || "时间待定"}`));
    const venue = document.createElement("small");
    venue.textContent = [record.venue, record.city].filter(Boolean).join(" · ") || "场地待定";
    eventCell.append(venue);

    const activeUntil = record.active_until || record.event_date;
    const rangeCell = cell(`${record.active_from || "不限"} → ${activeUntil}`);

    const actionsCell = document.createElement("td");
    actionsCell.className = "row-actions";
    [
      ["preview", "预览"],
      ["edit", "编辑"],
      ["toggle", record.enabled ? "停用" : "启用"],
      ["delete", "删除"],
    ].forEach(([action, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.eventAction = action;
      button.dataset.eventId = String(record.id);
      button.textContent = label;
      actionsCell.append(button);
    });
    row.append(statusCell, artistCell, eventCell, rangeCell, actionsCell);
    eventTableBody.append(row);
  });
}

async function loadArtistEvents() {
  const result = await requestJSON("/api/artist-events", { cache: "no-store" });
  artistEvents = result.items || [];
  renderArtistEvents();
}

artistEventForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formPayload(artistEventForm);
  const eventId = data.id;
  delete data.id;
  data.enabled = artistEventForm.elements.enabled.checked;
  data.priority = Number(data.priority || 0);
  try {
    const method = eventId ? "PUT" : "POST";
    const url = eventId ? `/api/artist-events/${eventId}` : "/api/artist-events";
    await requestJSON(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await loadArtistEvents();
    resetArtistEventForm();
    eventMessage.textContent = eventId ? "演出记录已更新。" : "演出记录已新增。";
  } catch (error) {
    eventMessage.textContent = error.message;
  }
});

eventTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-event-action]");
  if (!button) return;
  const record = artistEvents.find((item) => item.id === Number(button.dataset.eventId));
  if (!record) return;
  const action = button.dataset.eventAction;
  if (action === "edit") {
    editArtistEvent(record);
    return;
  }
  if (action === "delete" && !window.confirm(`确定删除 ${record.artist_name} 的这条演出记录吗？`)) return;
  try {
    if (action === "preview") {
      await postJSON(`/api/artist-events/${record.id}/preview`, {});
      eventMessage.textContent = `正在预览 ${record.artist_name} 的演出提示。`;
    } else if (action === "toggle") {
      await requestJSON(`/api/artist-events/${record.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !record.enabled }),
      });
      await loadArtistEvents();
    } else if (action === "delete") {
      await requestJSON(`/api/artist-events/${record.id}`, { method: "DELETE" });
      await loadArtistEvents();
      eventMessage.textContent = "演出记录已删除。";
    }
  } catch (error) {
    eventMessage.textContent = error.message;
  }
});

document.querySelector("#new-event").addEventListener("click", () => {
  resetArtistEventForm();
  artistEventForm.scrollIntoView({ behavior: "smooth", block: "start" });
});
document.querySelector("#cancel-event-edit").addEventListener("click", resetArtistEventForm);

function resetDisplayItemForm() {
  if (displayItemPreviewObjectUrl) URL.revokeObjectURL(displayItemPreviewObjectUrl);
  displayItemPreviewObjectUrl = "";
  displayItemForm.reset();
  displayItemForm.elements.id.value = "";
  displayItemForm.elements.enabled.checked = true;
  displayItemForm.elements.content_type.value = "bean";
  displayItemForm.elements.eyebrow.value = "NEW BEAN · CURRENT ROTATION";
  displayItemForm.elements.footer.value = "ASK THE BARISTA · WHILE AVAILABLE";
  displayItemForm.elements.priority.value = "0";
  displayItemForm.elements.display_seconds.value = "10";
  renderDisplayItemImagePreview("");
  document.querySelector("#display-item-form-title").textContent = "新增豆子／活动内容";
  displayItemMessage.textContent = "";
}

function editDisplayItem(record) {
  resetDisplayItemForm();
  Object.entries(record).forEach(([key, value]) => {
    const field = displayItemForm.elements[key];
    if (!field) return;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = value ?? "";
  });
  renderDisplayItemImagePreview(record.image_url || "");
  document.querySelector("#display-item-form-title").textContent = `编辑：${record.name}`;
  displayItemForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderDisplayItems() {
  displayItemTableBody.replaceChildren();
  if (!displayItems.length) {
    const row = document.createElement("tr");
    const empty = cell("还没有豆子或活动内容。点击右上角新增第一条。", "empty-cell");
    empty.colSpan = 5;
    row.append(empty);
    displayItemTableBody.append(row);
    return;
  }

  displayItems.forEach((record) => {
    const row = document.createElement("tr");
    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `status-chip ${record.enabled ? "is-enabled" : ""}`;
    status.textContent = !record.enabled ? "停用" : record.eligible ? "有效" : "未生效";
    statusCell.append(status);

    const nameCell = document.createElement("td");
    const name = document.createElement("strong");
    name.textContent = record.name;
    const type = document.createElement("small");
    type.textContent = record.content_type === "event" ? "门店活动" : "豆子";
    nameCell.append(name, type);

    const contentCell = document.createElement("td");
    const titleSummary = record.title.replaceAll("\n", " / ") || "默认活动信息";
    contentCell.append(document.createTextNode(
      record.image_url ? `带图片 · ${titleSummary}` : titleSummary
    ));
    const detail = document.createElement("small");
    detail.textContent = record.image_url
      ? `左侧视觉 · ${record.image_url}`
      : (record.details.replaceAll("\n", " · ") || record.eyebrow || "—");
    contentCell.append(detail);

    const rangeCell = document.createElement("td");
    rangeCell.append(document.createTextNode(`${record.active_from || "不限"} → ${record.active_until || "不限"}`));
    const duration = document.createElement("small");
    duration.textContent = `${record.display_seconds} 秒 · 优先级 ${record.priority}`;
    rangeCell.append(duration);

    const actionsCell = document.createElement("td");
    actionsCell.className = "row-actions";
    [
      ["preview", "预览"],
      ["edit", "编辑"],
      ["toggle", record.enabled ? "停用" : "启用"],
      ["delete", "删除"],
    ].forEach(([action, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.displayItemAction = action;
      button.dataset.displayItemId = String(record.id);
      button.textContent = label;
      actionsCell.append(button);
    });
    row.append(statusCell, nameCell, contentCell, rangeCell, actionsCell);
    displayItemTableBody.append(row);
  });
}

async function loadDisplayItems() {
  const result = await requestJSON("/api/display-items", { cache: "no-store" });
  displayItems = result.items || [];
  renderDisplayItems();
}

function renderDisplayItemImagePreview(url) {
  const image = displayItemImagePreview.querySelector("img");
  const hasImage = Boolean(url);
  displayItemImagePreview.classList.toggle("has-image", hasImage);
  if (hasImage) image.src = url;
  else image.removeAttribute("src");
}

displayItemForm.elements.image_url.addEventListener("input", () => {
  renderDisplayItemImagePreview(displayItemForm.elements.image_url.value.trim());
});

displayItemForm.elements.image_file.addEventListener("change", () => {
  if (displayItemPreviewObjectUrl) URL.revokeObjectURL(displayItemPreviewObjectUrl);
  const file = displayItemForm.elements.image_file.files[0];
  displayItemPreviewObjectUrl = file ? URL.createObjectURL(file) : "";
  renderDisplayItemImagePreview(
    displayItemPreviewObjectUrl || displayItemForm.elements.image_url.value.trim()
  );
});

displayItemForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formPayload(displayItemForm);
  const itemId = data.id;
  delete data.id;
  delete data.image_file;
  data.enabled = displayItemForm.elements.enabled.checked;
  data.priority = Number(data.priority || 0);
  data.display_seconds = Number(data.display_seconds || 10);
  try {
    const imageFile = displayItemForm.elements.image_file.files[0];
    if (imageFile) {
      displayItemMessage.textContent = "正在上传图片…";
      const uploadResponse = await fetch("/api/media", {
        method: "PUT",
        headers: {
          "Content-Type": imageFile.type || "application/octet-stream",
          "X-Filename": encodeURIComponent(imageFile.name),
        },
        body: imageFile,
      });
      const upload = await uploadResponse.json();
      if (!uploadResponse.ok) {
        throw new Error(upload.error || `upload failed: ${uploadResponse.status}`);
      }
      if (upload.media_type !== "image") {
        throw new Error("豆子／活动内容只能上传图片素材。");
      }
      data.image_url = upload.url;
      displayItemForm.elements.image_url.value = upload.url;
    }
    const method = itemId ? "PUT" : "POST";
    const url = itemId ? `/api/display-items/${itemId}` : "/api/display-items";
    await requestJSON(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    await loadDisplayItems();
    resetDisplayItemForm();
    displayItemMessage.textContent = itemId ? "内容已更新。" : "内容已新增。";
  } catch (error) {
    displayItemMessage.textContent = error.message;
  }
});

displayItemTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-display-item-action]");
  if (!button) return;
  const record = displayItems.find((item) => item.id === Number(button.dataset.displayItemId));
  if (!record) return;
  const action = button.dataset.displayItemAction;
  if (action === "edit") {
    editDisplayItem(record);
    return;
  }
  if (action === "delete" && !window.confirm(`确定删除“${record.name}”吗？`)) return;
  try {
    if (action === "preview") {
      await postJSON(`/api/display-items/${record.id}/preview`, {});
      displayItemMessage.textContent = `正在预览“${record.name}”。`;
    } else if (action === "toggle") {
      await requestJSON(`/api/display-items/${record.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !record.enabled }),
      });
      await loadDisplayItems();
    } else if (action === "delete") {
      await requestJSON(`/api/display-items/${record.id}`, { method: "DELETE" });
      await loadDisplayItems();
      displayItemMessage.textContent = "内容已删除。";
    }
  } catch (error) {
    displayItemMessage.textContent = error.message;
  }
});

document.querySelector("#new-display-item").addEventListener("click", () => {
  resetDisplayItemForm();
  displayItemForm.scrollIntoView({ behavior: "smooth", block: "start" });
});
document.querySelector("#cancel-display-item-edit").addEventListener("click", resetDisplayItemForm);

document.querySelector(".transport").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !latestState) return;
  const action = button.dataset.action;
  let payload;
  if (action === "toggle") {
    payload = { is_playing: !latestState.track.is_playing };
  } else if (action === "finish") {
    const duration = Number(latestState.track.duration);
    if (!Number.isFinite(duration) || duration <= 0) {
      message.textContent = "当前曲目没有有效总时长，无法模拟自然结束。";
      return;
    }
    try {
      await postJSON("/api/mock/track", {
        position: Math.max(0, duration - 1),
        duration,
        playback_status: "playing",
      });
      playlistIndex = (playlistIndex + 1) % playlist.length;
      const state = await postJSON("/api/mock/track", {
        ...playlist[playlistIndex],
        position: 0,
        playback_status: "playing",
      });
      message.textContent = state.display?.insert_source === "scheduler"
        ? `已触发自动插播：${state.display.display_item_name || "豆子／活动"}。`
        : "已模拟自然结束；当前规则下没有触发插播。";
    } catch (error) {
      message.textContent = error.message;
    }
    return;
  } else {
    playlistIndex += action === "next" ? 1 : -1;
    playlistIndex = (playlistIndex + playlist.length) % playlist.length;
    payload = { ...playlist[playlistIndex], position: 0, playback_status: "playing" };
  }
  try {
    await postJSON("/api/mock/track", payload);
    message.textContent = action === "toggle" ? "播放状态已更新。" : "模拟换曲已完成。";
  } catch (error) {
    message.textContent = error.message;
  }
});

async function loadInitialState() {
  const response = await fetch("/api/state", { cache: "no-store" });
  if (!response.ok) throw new Error(`state request failed: ${response.status}`);
  render(await response.json());
}

function connectEvents() {
  const source = new EventSource("/api/events");
  source.addEventListener("open", () => setConnection("online"));
  source.addEventListener("state", (event) => render(JSON.parse(event.data)));
  source.addEventListener("error", () => setConnection("offline"));
}

loadInitialState().catch((error) => {
  message.textContent = error.message;
  setConnection("offline");
});
loadArtistEvents().catch((error) => {
  eventTableBody.replaceChildren();
  const row = document.createElement("tr");
  const failed = cell(error.message, "empty-cell");
  failed.colSpan = 5;
  row.append(failed);
  eventTableBody.append(row);
});
loadDisplayItems().catch((error) => {
  displayItemTableBody.replaceChildren();
  const row = document.createElement("tr");
  const failed = cell(error.message, "empty-cell");
  failed.colSpan = 5;
  row.append(failed);
  displayItemTableBody.append(row);
});
connectEvents();
