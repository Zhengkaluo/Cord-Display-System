const scenes = [...document.querySelectorAll("[data-scene]")];
const visualPanels = [...document.querySelectorAll("[data-visual-panel]")];
const connections = [...document.querySelectorAll("[data-connection]")];
const promotionScene = document.querySelector('[data-scene="promotion"]');
const promotionImage = document.querySelector("[data-promotion-image]");

function setText(selector, value, fallback = "—") {
  document.querySelectorAll(selector).forEach((element) => {
    element.textContent = value || fallback;
  });
}

function setLines(selector, value, fallback = "—") {
  document.querySelectorAll(selector).forEach((element) => {
    element.replaceChildren();
    String(value || fallback).split(/\r?\n/).forEach((line, index) => {
      if (index) element.append(document.createElement("br"));
      element.append(document.createTextNode(line));
    });
  });
}

function formatTime(value) {
  if (!Number.isFinite(value) || value < 0) return "—:—";
  const seconds = Math.floor(value);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function setConnection(status) {
  connections.forEach((element) => {
    element.textContent = status === "online" ? "LIVE" : "RECONNECTING";
    element.classList.toggle("is-online", status === "online");
    element.classList.toggle("is-offline", status !== "online");
  });
}

function renderVisual(state) {
  const track = state.track || {};
  const config = state.config || {};
  const mode = config.visual_mode || "album_cover";
  const customUrl = String(config.visual_url || "");
  const useVideo = mode === "video" && customUrl;

  const imageUrl = mode === "image" ? customUrl : String(track.cover_url || "");
  visualPanels.forEach((panel) => {
    const art = panel.querySelector("[data-visual-art]");
    const video = panel.querySelector("[data-visual-video]");
    panel.classList.toggle("is-video", useVideo);
    panel.setAttribute(
      "aria-label",
      useVideo ? "自定义循环视频" : (mode === "image" ? "自定义图片" : "专辑封面")
    );
    if (useVideo) {
      if (video.getAttribute("src") !== customUrl) {
        video.src = customUrl;
        video.load();
      }
      video.play().catch(() => {});
      return;
    }
    video.pause();
    art.style.backgroundImage = imageUrl ? `url(${JSON.stringify(imageUrl)})` : "";
    art.classList.toggle("has-cover", Boolean(imageUrl));
  });
}

function renderScene(mode, transitionMs) {
  const safeMode = ["now_playing", "artist_notice", "promotion"].includes(mode)
    ? mode
    : "now_playing";
  document.documentElement.style.setProperty("--transition-ms", `${transitionMs}ms`);
  scenes.forEach((scene) => {
    const active = scene.dataset.scene === safeMode;
    scene.classList.toggle("is-active", active);
    scene.setAttribute("aria-hidden", active ? "false" : "true");
  });
}

function render(state) {
  const track = state.track || {};
  const notice = state.content?.artist_notice || {};
  const promotion = state.content?.promotion || {};
  setText("[data-track-title]", track.title, "No track information");
  setText("[data-track-artist]", track.artist);
  setText("[data-track-album]", track.album, "Unknown album");
  setText("[data-position]", formatTime(track.position));
  setText("[data-duration]", formatTime(track.duration));
  setText("[data-playback-status]", String(track.playback_status || "waiting").toUpperCase());
  setText("[data-source]", `${track.app_name || "unknown player"} · ${state.system?.source || "local source"}`.toUpperCase());
  setText("[data-revision]", `REV ${state.revision ?? "—"}`);

  setText("[data-notice-eyebrow]", notice.eyebrow, "ARTIST IN TOWN");
  setText("[data-notice-date]", notice.date_label, "DATE TBA");
  setText("[data-notice-time]", notice.time_label, "TBA");
  setText("[data-notice-venue]", notice.venue, "VENUE TBA");
  setText("[data-notice-city]", notice.city, "CITY TBA");
  setText("[data-notice-footer]", notice.footer, "UPCOMING PERFORMANCE");

  setText("[data-promotion-eyebrow]", promotion.eyebrow, "CORD UPDATE");
  setLines("[data-promotion-title]", promotion.title, "CORD");
  setLines("[data-promotion-details]", promotion.details, "");
  setText("[data-promotion-callout]", promotion.callout, "Ask the barista");
  setText("[data-promotion-footer]", promotion.footer, "CORD COFFEE");
  const promotionImageUrl = String(promotion.image_url || "");
  promotionScene.classList.toggle("has-image", Boolean(promotionImageUrl));
  if (promotionImage.getAttribute("src") !== promotionImageUrl) {
    if (promotionImageUrl) promotionImage.src = promotionImageUrl;
    else promotionImage.removeAttribute("src");
  }

  const duration = Number(track.duration);
  const position = Number(track.position);
  const progress = Number.isFinite(duration) && duration > 0 && Number.isFinite(position)
    ? Math.max(0, Math.min(100, (position / duration) * 100))
    : 0;
  document.querySelectorAll("[data-progress]").forEach((bar) => {
    bar.style.width = `${progress}%`;
  });

  renderVisual(state);
  renderScene(state.display?.mode, Number(state.config?.transition_ms ?? 750));
}

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

loadInitialState().catch(() => setConnection("offline"));
connectEvents();
