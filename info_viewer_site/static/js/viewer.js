(() => {
  const body = document.body;
  const pageKind = body.dataset.pageKind || "list";
  const articleDataNode = document.getElementById("viewer-data");
  const articles = articleDataNode ? JSON.parse(articleDataNode.textContent || "[]") : [];
  const rootPath = "/";
  const indexVersion = body.dataset.indexVersion || "1";
  const adminSecretStorageKey = "info-viewer.admin-secret.v1";
  const state = {
    channel: "all",
    person: "",
    query: "",
    sort: "newest",
    searchIndex: null,
    searchPromise: null,
  };

  const getQueryParams = () => new URLSearchParams(window.location.search);
  const normalize = (value) => String(value || "").toLocaleLowerCase("ja-JP").replace(/\s+/g, " ").trim();
  const escapeHtml = (value) => String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function articleTimestamp(article, sortMode = state.sort) {
    const candidates = sortMode === "date"
      ? [article.publishedAt, article.recordedAt, article.lastModified]
      : [article.recordedAt, article.lastModified, article.publishedAt];
    for (const value of candidates) {
      const parsed = Date.parse(String(value || ""));
      if (Number.isFinite(parsed)) return parsed;
    }
    return 0;
  }

  function compareArticles(left, right) {
    const timeDifference = articleTimestamp(right) - articleTimestamp(left);
    if (timeDifference) return timeDifference;
    const modifiedDifference = articleTimestamp(right, "newest") - articleTimestamp(left, "newest");
    if (modifiedDifference) return modifiedDifference;
    return normalize(left.title).localeCompare(normalize(right.title), "ja");
  }

  function sortedArticles(items) {
    return [...items].sort(compareArticles);
  }

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

  function currentListParams(includeDefaults = false) {
    const params = new URLSearchParams();
    if (includeDefaults || state.channel !== "all") params.set("channel", state.channel);
    if (includeDefaults || state.sort !== "newest") params.set("sort", state.sort);
    if (state.person) params.set("person", state.person);
    if (state.query) params.set("q", state.query);
    return params;
  }

  function listUrl() {
    const params = currentListParams();
    return `${rootPath}${params.toString() ? `?${params.toString()}` : ""}`;
  }

  function articleUrl(rawUrl) {
    const params = currentListParams(true);
    return `${rawUrl}${rawUrl.includes("?") ? "&" : "?"}${params.toString()}`;
  }

  function syncToolButtons() {
    toolButtons.forEach((button) => {
      button.classList.toggle("has-filter", button.dataset.tool === "people" && Boolean(state.person));
    });
  }

  function closeTool() {
    if (!toolSheet || !toolBackdrop) return;
    toolSheet.hidden = true;
    toolBackdrop.hidden = true;
    toolButtons.forEach((button) => button.classList.remove("is-active"));
    syncToolButtons();
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
    syncToolButtons();
    if (name === "people") renderPeopleTags();
    if (name === "search") {
      ensureSearchIndex().then(renderSearchResults);
      window.setTimeout(() => searchInput?.focus(), 30);
    }
    if (name === "submit") restoreAdminSecret();
  }

  toolButtons.forEach((button) => {
    button.addEventListener("click", () => openTool(button.dataset.tool));
  });
  document.querySelectorAll("[data-close-tool]").forEach((button) => button.addEventListener("click", closeTool));

  function activeCards() {
    return [...document.querySelectorAll(".article-card")];
  }

  function cardAsArticle(card) {
    return {
      title: card.dataset.title || "",
      publishedAt: card.dataset.publishedAt || "",
      recordedAt: card.dataset.recordedAt || "",
      lastModified: card.dataset.lastModified || "",
    };
  }

  function applyCardOrder() {
    const list = document.getElementById("article-list");
    if (!list) return;
    activeCards()
      .sort((left, right) => compareArticles(cardAsArticle(left), cardAsArticle(right)))
      .forEach((card) => list.appendChild(card));
  }

  function updateArticleLinks() {
    if (pageKind !== "list") return;
    activeCards().forEach((card) => {
      const baseUrl = card.dataset.baseUrl || card.getAttribute("href") || "";
      card.dataset.baseUrl = baseUrl;
      card.setAttribute("href", articleUrl(baseUrl));
    });
  }

  function baseMatches(card) {
    const channelMatches = state.channel === "all" || card.dataset.channel === state.channel;
    const people = (card.dataset.persons || "").split(",").filter(Boolean);
    const personMatches = !state.person || people.includes(state.person);
    return channelMatches && personMatches;
  }

  function searchText(item) {
    return normalize([item.title, item.channelName, item.channelTab, item.duration, item.timeLabel, ...(item.persons || []), item.text].join(" "));
  }

  function matchedSearchIds() {
    const query = normalize(state.query);
    if (!query || !state.searchIndex) return null;
    return new Set(state.searchIndex.filter((item) => searchText(item).includes(query)).map((item) => item.id));
  }

  function updateListFilters() {
    if (pageKind !== "list") return;
    applyCardOrder();
    const query = normalize(state.query);
    const resultIds = matchedSearchIds();
    let visible = 0;
    activeCards().forEach((card) => {
      const queryMatches = !query || (resultIds
        ? resultIds.has(card.dataset.articleId)
        : normalize(`${card.dataset.title} ${card.dataset.persons}`).includes(query));
      const show = baseMatches(card) && queryMatches;
      card.hidden = !show;
      if (show) visible += 1;
    });
    const count = document.getElementById("result-count");
    const filter = document.getElementById("active-filter");
    const empty = document.getElementById("empty-state");
    if (count) count.textContent = `${visible}件`;
    if (filter) {
      filter.textContent = state.query
        ? `検索: ${state.query}`
        : state.person
          ? `人物: ${state.person}`
          : state.channel === "all"
            ? "すべて"
            : state.channel;
    }
    if (empty) empty.hidden = visible !== 0;
    updateArticleLinks();
    syncToolButtons();
  }

  function syncListUrl() {
    if (pageKind === "list") window.history.replaceState({}, "", listUrl());
  }

  function setChannel(channel) {
    state.channel = channel || "all";
    document.querySelectorAll(".channel-tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.channel === state.channel);
    });
    updateListFilters();
    syncListUrl();
  }

  document.querySelectorAll(".channel-tab").forEach((button) => {
    button.addEventListener("click", () => setChannel(button.dataset.channel));
  });

  function setSort(sortMode) {
    state.sort = sortMode === "date" ? "date" : "newest";
    document.querySelectorAll("[data-sort]").forEach((button) => {
      const active = button.dataset.sort === state.sort;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    updateListFilters();
    renderSearchResults();
    syncListUrl();
  }

  document.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => setSort(button.dataset.sort));
  });

  function setPerson(person) {
    state.person = person;
    if (pageKind !== "list") {
      window.location.assign(listUrl());
      return;
    }
    renderPeopleTags();
    updateListFilters();
    syncListUrl();
    closeTool();
  }

  function renderPeopleTags() {
    if (!personTags) return;
    const people = [...new Set(articles.flatMap((article) => article.persons || []))].sort((left, right) => left.localeCompare(right, "ja"));
    if (!people.length) {
      personTags.innerHTML = '<p class="tool-help">人物タグ付きの記事はまだありません。</p>';
      return;
    }
    personTags.innerHTML = people.map((person) => `<button class="person-tag${person === state.person ? " is-active" : ""}" type="button" data-person="${escapeHtml(person)}">${escapeHtml(person)}</button>`).join("");
    personTags.querySelectorAll("[data-person]").forEach((button) => {
      button.addEventListener("click", () => {
        setPerson(state.person === button.dataset.person ? "" : button.dataset.person);
      });
    });
  }

  async function ensureSearchIndex() {
    if (state.searchIndex) return state.searchIndex;
    if (!state.searchPromise) {
      if (searchStatus) searchStatus.textContent = "タイトル・人物・本文を読み込んでいます。";
      state.searchPromise = fetch(`${rootPath}search.json?v=${encodeURIComponent(indexVersion)}`, { cache: "no-cache" })
        .then((response) => {
          if (!response.ok) throw new Error(`検索インデックスを取得できません (${response.status})`);
          return response.json();
        })
        .then((index) => {
          state.searchIndex = Array.isArray(index) ? index : [];
          return state.searchIndex;
        })
        .catch(() => {
          state.searchIndex = [];
          if (searchStatus) searchStatus.textContent = "本文検索を読み込めませんでした。タイトル・人物タグで検索します。";
          return state.searchIndex;
        });
    }
    return state.searchPromise;
  }

  function renderSearchResults() {
    if (!searchResults) return;
    const query = normalize(state.query);
    if (!query) {
      searchResults.innerHTML = "";
      if (searchStatus) searchStatus.textContent = "タイトル・チャンネル名・人物・本文を検索できます。";
      return;
    }
    if (!state.searchIndex) {
      if (searchStatus) searchStatus.textContent = "検索インデックスを読み込んでいます。";
      return;
    }
    const matches = sortedArticles(state.searchIndex.filter((item) => searchText(item).includes(query)));
    if (searchStatus) searchStatus.textContent = `タイトル・人物・本文から ${matches.length}件見つかりました。`;
    if (!matches.length) {
      searchResults.innerHTML = '<p class="tool-help">一致する記事はありません。</p>';
      return;
    }
    searchResults.innerHTML = matches.slice(0, 50).map((item) => `<a class="search-result" href="${escapeHtml(articleUrl(item.url))}"><span>${escapeHtml(item.channelName || item.channelTab)}</span><strong>${escapeHtml(item.title)}</strong></a>`).join("");
  }

  searchInput?.addEventListener("input", async () => {
    state.query = searchInput.value.trim();
    if (state.query) await ensureSearchIndex();
    updateListFilters();
    renderSearchResults();
    syncListUrl();
  });

  function storedAdminSecret() {
    try {
      return window.localStorage.getItem(adminSecretStorageKey) || "";
    } catch {
      return "";
    }
  }

  function restoreAdminSecret() {
    const secret = document.getElementById("admin-secret");
    const status = document.getElementById("submit-status");
    const saved = storedAdminSecret();
    if (secret && saved && !secret.value) secret.value = saved;
    if (status && saved) status.textContent = "この端末に保存済みの管理シークレットを使います。";
  }

  function saveAdminSecret(secret) {
    try {
      window.localStorage.setItem(adminSecretStorageKey, secret);
      return true;
    } catch {
      return false;
    }
  }

  async function submitVideo() {
    const input = document.getElementById("video-url");
    const secret = document.getElementById("admin-secret");
    const status = document.getElementById("submit-status");
    const button = document.getElementById("submit-video");
    const endpoint = body.dataset.triggerEndpoint || "";
    const videoUrl = input?.value.trim() || "";
    const adminSecret = secret?.value.trim() || storedAdminSecret();
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
    if (status) status.textContent = "送信を確認中です。";
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
      if (response.status === 401) {
        throw new Error("管理シークレットがVercelの INFO_VIEWER_ADMIN_SECRET と一致しません。");
      }
      if (!response.ok || !payload.success) throw new Error(payload.error || `起動に失敗しました (${response.status})`);
      const stored = saveAdminSecret(adminSecret);
      if (status) status.textContent = stored
        ? "起動しました。管理シークレットをこの端末に保存しました。完了後、新しい記事が自動公開されます。"
        : "起動しました。完了後、新しい記事が自動公開されます。";
      if (input) input.value = "";
    } catch (error) {
      if (status) status.textContent = error.message || "起動に失敗しました。";
    } finally {
      button.disabled = false;
    }
  }

  document.getElementById("submit-video")?.addEventListener("click", submitVideo);

  function initializeArticleNavigation() {
    if (pageKind !== "article") return;
    const params = getQueryParams();
    state.channel = params.get("channel") || "all";
    state.person = params.get("person") || "";
    state.query = params.get("q") || "";
    state.sort = params.get("sort") === "date" ? "date" : "newest";
    const backLink = document.querySelector(".back-link");
    if (backLink) backLink.setAttribute("href", listUrl());
    syncToolButtons();
  }

  function bindArticleSwipe() {
    if (pageKind !== "article") return;
    const articleId = body.dataset.articleId || "";
    const requestedChannel = state.channel;
    const currentIndex = articles.findIndex((article) => article.id === articleId);
    if (currentIndex < 0) return;
    const scoped = sortedArticles(requestedChannel === "all"
      ? articles
      : articles.filter((article) => article.channelTab === requestedChannel));
    const position = scoped.findIndex((article) => article.id === articleId);
    if (position < 0 || scoped.length < 2) return;
    const hint = document.getElementById("swipe-hint");
    if (hint) hint.textContent = requestedChannel === "all"
      ? "左右スワイプで全記事を移動"
      : `左右スワイプで「${requestedChannel}」内を移動`;
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
      if (next?.url) window.location.assign(articleUrl(next.url));
    }, { passive: true });
  }

  function initializeList() {
    if (pageKind !== "list") return;
    const params = getQueryParams();
    const requestedChannel = params.get("channel") || "all";
    const requestedPerson = params.get("person") || "";
    const requestedQuery = params.get("q") || "";
    const requestedSort = params.get("sort") === "date" ? "date" : "newest";
    if ([...document.querySelectorAll(".channel-tab")].some((button) => button.dataset.channel === requestedChannel)) {
      state.channel = requestedChannel;
    }
    state.person = requestedPerson;
    state.query = requestedQuery;
    state.sort = requestedSort;
    if (searchInput) searchInput.value = requestedQuery;
    document.querySelectorAll(".channel-tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.channel === state.channel);
    });
    document.querySelectorAll("[data-sort]").forEach((button) => {
      const active = button.dataset.sort === state.sort;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    updateListFilters();
    if (requestedQuery) {
      ensureSearchIndex().then(() => {
        updateListFilters();
        renderSearchResults();
      });
    }
  }

  initializeList();
  initializeArticleNavigation();
  bindArticleSwipe();
  restoreAdminSecret();
})();
