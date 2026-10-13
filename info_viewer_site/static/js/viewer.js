(() => {
  const body = document.body;
  const pageKind = body.dataset.pageKind || "list";
  const articleDataNode = document.getElementById("viewer-data");
  const articles = articleDataNode ? JSON.parse(articleDataNode.textContent || "[]") : [];
  const rootPath = "/";
  const state = {
    channel: "all",
    person: "",
    query: "",
    searchIndex: null,
    searchPromise: null,
  };

  const getQueryParams = () => new URLSearchParams(window.location.search);
  const normalize = (value) => String(value || "").toLocaleLowerCase("ja-JP");
  const escapeHtml = (value) => String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const toolSheet = document.getElementById("tool-sheet");
  const toolBackdrop = document.querySelector(".tool-backdrop");
  const toolTitle = document.getElementById("tool-title");
  const toolButtons = [...document.querySelectorAll("[data-tool]")];
  const toolPanels = [...document.querySelectorAll("[data-tool-panel]")];
  const searchInput = document.getElementById("search-input");
  const searchStatus = document.getElementById("search-status");
  const searchResults = document.getElementById("search-results");
  const personTags = document.getElementById("person-tags");
  const titleByTool = { search: "検索", people: "人物タグ", submit: "即時URL" };

  function closeTool() {
    if (!toolSheet || !toolBackdrop) return;
    toolSheet.hidden = true;
    toolBackdrop.hidden = true;
    toolButtons.forEach((button) => button.classList.remove("is-active"));
  }

  function openTool(name) {
    if (!toolSheet || !toolBackdrop) return;
    toolSheet.hidden = false;
    toolBackdrop.hidden = false;
    toolTitle.textContent = titleByTool[name] || "操作";
    toolPanels.forEach((panel) => {
      panel.hidden = panel.dataset.toolPanel !== name;
    });
    toolButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.tool === name));
    if (name === "people") renderPeopleTags();
    if (name === "search") {
      ensureSearchIndex();
      window.setTimeout(() => searchInput?.focus(), 30);
    }
  }

  toolButtons.forEach((button) => {
    button.addEventListener("click", () => openTool(button.dataset.tool));
  });
  document.querySelectorAll("[data-close-tool]").forEach((button) => button.addEventListener("click", closeTool));

  function activeCards() {
    return [...document.querySelectorAll(".article-card")];
  }

  function baseMatches(card) {
    const channelMatches = state.channel === "all" || card.dataset.channel === state.channel;
    const people = (card.dataset.persons || "").split(",").filter(Boolean);
    const personMatches = !state.person || people.includes(state.person);
    return channelMatches && personMatches;
  }

  function updateListFilters() {
    if (pageKind !== "list") return;
    const query = normalize(state.query);
    const resultIds = state.searchIndex && query
      ? new Set(state.searchIndex.filter((item) => normalize([item.title, item.channelName, ...(item.persons || []), item.text].join(" ")).includes(query)).map((item) => item.id))
      : null;
    let visible = 0;
    activeCards().forEach((card) => {
      const queryMatches = !query || (resultIds ? resultIds.has(card.dataset.articleId) : normalize(`${card.dataset.title} ${card.dataset.persons}`).includes(query));
      const show = baseMatches(card) && queryMatches;
      card.hidden = !show;
      if (show) visible += 1;
    });
    const count = document.getElementById("result-count");
    const filter = document.getElementById("active-filter");
    const empty = document.getElementById("empty-state");
    if (count) count.textContent = `${visible}件`;
    if (filter) filter.textContent = state.query || state.person || (state.channel === "all" ? "新着順" : state.channel);
    if (empty) empty.hidden = visible !== 0;
  }

  function setChannel(channel) {
    state.channel = channel || "all";
    document.querySelectorAll(".channel-tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.channel === state.channel);
    });
    updateListFilters();
    const params = getQueryParams();
    if (state.channel === "all") params.delete("channel"); else params.set("channel", state.channel);
    if (state.query) params.set("q", state.query); else params.delete("q");
    window.history.replaceState({}, "", `${rootPath}${params.toString() ? `?${params.toString()}` : ""}`);
  }

  document.querySelectorAll(".channel-tab").forEach((button) => {
    button.addEventListener("click", () => setChannel(button.dataset.channel));
  });

  function renderPeopleTags() {
    if (!personTags) return;
    const people = [...new Set(articles.flatMap((article) => article.persons || []))].sort((left, right) => left.localeCompare(right, "ja"));
    if (!people.length) {
      personTags.innerHTML = "<p class=\"tool-help\">人物タグ付きの記事はまだありません。</p>";
      return;
    }
    personTags.innerHTML = people.map((person) => `<button class="person-tag${person === state.person ? " is-active" : ""}" type="button" data-person="${escapeHtml(person)}">${escapeHtml(person)}</button>`).join("");
    personTags.querySelectorAll("[data-person]").forEach((button) => {
      button.addEventListener("click", () => {
        state.person = state.person === button.dataset.person ? "" : button.dataset.person;
        renderPeopleTags();
        updateListFilters();
        if (pageKind === "list") closeTool();
      });
    });
  }

  async function ensureSearchIndex() {
    if (state.searchIndex) return state.searchIndex;
    if (!state.searchPromise) {
      if (searchStatus) searchStatus.textContent = "検索インデックスを読み込んでいます。";
      state.searchPromise = fetch(`${rootPath}search.json`, { cache: "force-cache" })
        .then((response) => {
          if (!response.ok) throw new Error(`検索インデックスを取得できません (${response.status})`);
          return response.json();
        })
        .then((index) => {
          state.searchIndex = Array.isArray(index) ? index : [];
          if (searchStatus) searchStatus.textContent = "本文を含めて検索できます。";
          return state.searchIndex;
        })
        .catch((error) => {
          if (searchStatus) searchStatus.textContent = "本文検索を読み込めませんでした。タイトル検索へ切り替えます。";
          state.searchIndex = [];
          return state.searchIndex;
        });
    }
    return state.searchPromise;
  }

  function renderSearchResults() {
    if (!searchResults) return;
    const query = normalize(state.query);
    if (!query || !state.searchIndex) {
      searchResults.innerHTML = "";
      return;
    }
    const matches = state.searchIndex
      .filter((item) => normalize([item.title, item.channelName, ...(item.persons || []), item.text].join(" ")).includes(query))
      .slice(0, 20);
    if (!matches.length) {
      searchResults.innerHTML = "<p class=\"tool-help\">一致する記事はありません。</p>";
      return;
    }
    searchResults.innerHTML = matches.map((item) => `<a class="search-result" href="${escapeHtml(item.url)}"><span>${escapeHtml(item.channelTab)}</span><strong>${escapeHtml(item.title)}</strong></a>`).join("");
  }

  searchInput?.addEventListener("input", async () => {
    state.query = searchInput.value.trim();
    if (state.query) await ensureSearchIndex();
    updateListFilters();
    renderSearchResults();
  });

  async function submitVideo() {
    const input = document.getElementById("video-url");
    const secret = document.getElementById("admin-secret");
    const status = document.getElementById("submit-status");
    const button = document.getElementById("submit-video");
    const endpoint = body.dataset.triggerEndpoint || "";
    const videoUrl = input?.value.trim() || "";
    const adminSecret = secret?.value || "";
    let parsedUrl;
    try {
      parsedUrl = new URL(videoUrl);
    } catch {
      if (status) status.textContent = "YouTube URLを正しく入力してください。";
      return;
    }
    if (!/(^|\.)youtube\.com$|(^|\.)youtu\.be$/i.test(parsedUrl.hostname)) {
      if (status) status.textContent = "YouTubeの動画URLだけを受け付けます。";
      return;
    }
    if (!adminSecret) {
      if (status) status.textContent = "管理シークレットを入力してください。";
      return;
    }
    if (!endpoint) {
      if (status) status.textContent = "起動エンドポイントが設定されていません。";
      return;
    }
    button.disabled = true;
    if (status) status.textContent = "GitHub Actionsを起動しています。";
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-info-viewer-admin-secret": adminSecret,
        },
        body: JSON.stringify({ video_url: videoUrl }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) throw new Error(payload.error || `起動に失敗しました (${response.status})`);
      if (status) status.textContent = "起動しました。完了後、Cloudflare Pagesへ新しい記事が自動公開されます。";
      if (input) input.value = "";
      if (secret) secret.value = "";
    } catch (error) {
      if (status) status.textContent = error.message || "起動に失敗しました。";
    } finally {
      button.disabled = false;
    }
  }

  document.getElementById("submit-video")?.addEventListener("click", submitVideo);

  function bindArticleSwipe() {
    if (pageKind !== "article") return;
    const articleId = body.dataset.articleId || "";
    const channelKey = document.querySelector(".article-page")?.dataset.channelKey || "";
    const currentIndex = articles.findIndex((article) => article.id === articleId);
    if (currentIndex < 0) return;
    const scoped = articles.filter((article) => article.channelKey === channelKey);
    const position = scoped.findIndex((article) => article.id === articleId);
    if (position < 0 || scoped.length < 2) return;
    let startX = 0;
    let startY = 0;
    const surface = document.querySelector(".article-page");
    surface?.addEventListener("touchstart", (event) => {
      const touch = event.changedTouches[0];
      startX = touch.clientX;
      startY = touch.clientY;
    }, { passive: true });
    surface?.addEventListener("touchend", (event) => {
      const touch = event.changedTouches[0];
      const diffX = touch.clientX - startX;
      const diffY = touch.clientY - startY;
      if (Math.abs(diffX) < 72 || Math.abs(diffY) > 56) return;
      const nextPosition = diffX < 0 ? position + 1 : position - 1;
      const next = scoped[nextPosition];
      if (next?.url) window.location.assign(next.url);
    }, { passive: true });
  }

  function initializeList() {
    if (pageKind !== "list") return;
    const params = getQueryParams();
    const requestedChannel = params.get("channel") || "all";
    const requestedQuery = params.get("q") || "";
    if (document.querySelector(`.channel-tab[data-channel="${CSS.escape(requestedChannel)}"]`)) {
      state.channel = requestedChannel;
    }
    if (requestedQuery) {
      state.query = requestedQuery;
      if (searchInput) searchInput.value = requestedQuery;
      ensureSearchIndex().then(() => updateListFilters());
    }
    document.querySelectorAll(".channel-tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.channel === state.channel);
    });
    updateListFilters();
  }

  initializeList();
  bindArticleSwipe();
})();
