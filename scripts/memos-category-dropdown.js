// ============================================================================
// FILE: memos-category-dropdown.js
// PURPOSE: Inject a category picker dropdown into the Memos editor
// INSTALL: Paste into Memos Admin > Settings > Custom Script
// ============================================================================
//
// ROUTER_URL DISCOVERY:
// 1. Tries /web-config on same origin (works if reverse-proxied on same domain)
// 2. Tries router.DOMAIN/web-config (convention: replace first subdomain with "router")
// 3. Falls back to ROUTER_URL_OVERRIDE if set below
//
// To hardcode the router URL, set this before pasting:
//   var ROUTER_URL_OVERRIDE = "https://router.chonkie.io";
// ============================================================================

(function () {
    let ROUTER_URL = "";
    let TAG_PREFIX = "box/";
    let POLL_INTERVAL_MS = 2000;
    let REFRESH_INTERVAL_MS = 300000;
    let DEBOUNCE_MS = 1000;

    let categories = [];
    let dropdownInjected = false;

    async function loadConfig() {
        var candidates = [];

        // If user set an override, try that first
        if (typeof ROUTER_URL_OVERRIDE !== "undefined" && ROUTER_URL_OVERRIDE) {
            candidates.push(ROUTER_URL_OVERRIDE);
        }

        // Convention: replace first subdomain with "router"
        // e.g. memos.chonkie.io → router.chonkie.io
        var host = window.location.hostname;
        var parts = host.split(".");
        if (parts.length >= 2) {
            parts[0] = "router";
            var routerHost = window.location.protocol + "//" + parts.join(".");
            candidates.push(routerHost);
        }

        // Also try same host on port 8780 (for local/dev without reverse proxy)
        candidates.push(window.location.protocol + "//" + host + ":8780");

        for (var i = 0; i < candidates.length; i++) {
            try {
                var resp = await fetch(candidates[i] + "/web-config");
                if (!resp.ok) continue;
                var cfg = await resp.json();
                ROUTER_URL = candidates[i];
                TAG_PREFIX = cfg.tag_prefix || TAG_PREFIX;
                POLL_INTERVAL_MS = cfg.poll_interval_ms || POLL_INTERVAL_MS;
                REFRESH_INTERVAL_MS = cfg.refresh_interval_ms || REFRESH_INTERVAL_MS;
                DEBOUNCE_MS = cfg.debounce_ms || DEBOUNCE_MS;
                console.log("[MemoRouter] Config loaded from " + ROUTER_URL);
                return;
            } catch (err) {
                continue;
            }
        }

        console.warn("[MemoRouter] Could not reach router at any candidate URL");
    }

    async function fetchCategories() {
        if (!ROUTER_URL) return [];
        try {
            var resp = await fetch(ROUTER_URL + "/categories");
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            var data = await resp.json();
            categories = data.categories || [];
            console.log(
                "[MemoRouter] Loaded " + categories.length + " categories"
            );
            return categories;
        } catch (err) {
            console.warn("[MemoRouter] Failed to fetch categories:", err.message);
            return [];
        }
    }

    function injectDropdown() {
        var editorToolbar = document.querySelector(
            ".memo-editor .editor-header, .memo-editor-header, .editor-actions"
        );

        if (!editorToolbar) return false;

        if (document.getElementById("memo-category-picker")) return true;

        var container = document.createElement("div");
        container.id = "memo-category-picker";
        container.style.cssText =
            "display:flex; gap:4px; padding:4px 8px; flex-wrap:wrap; " +
            "border-bottom:1px solid var(--border-color, #e0e0e0); " +
            "background:var(--bg-secondary, #f9f9f9); align-items:center;";

        var label = document.createElement("span");
        label.textContent = "Box:";
        label.style.cssText =
            "font-size:12px; color:var(--text-secondary, #888); " +
            "font-weight:600; margin-right:4px;";
        container.appendChild(label);

        categories.forEach(function (cat) {
            var btn = document.createElement("button");
            btn.textContent = "#" + cat.slug;
            btn.title = cat.description || cat.slug;
            btn.style.cssText =
                "font-size:11px; padding:2px 8px; border-radius:12px; " +
                "border:1px solid var(--border-color, #ddd); cursor:pointer; " +
                "background:var(--bg-primary, #fff); " +
                "color:var(--text-primary, #333); transition:all 0.15s;";

            btn.addEventListener("mouseenter", function () {
                btn.style.background = "var(--color-primary, #4a90d9)";
                btn.style.color = "#fff";
                btn.style.borderColor = "var(--color-primary, #4a90d9)";
            });
            btn.addEventListener("mouseleave", function () {
                btn.style.background = "var(--bg-primary, #fff)";
                btn.style.color = "var(--text-primary, #333)";
                btn.style.borderColor = "var(--border-color, #ddd)";
            });

            btn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                insertTag(TAG_PREFIX + cat.slug);
            });

            container.appendChild(btn);
        });

        editorToolbar.parentNode.insertBefore(container, editorToolbar);
        console.log("[MemoRouter] Category dropdown injected");
        return true;
    }

    function insertTag(tag) {
        var textarea = document.querySelector(
            ".memo-editor textarea, .editor-inputer textarea"
        );

        if (textarea) {
            var hashTag = "#" + tag + " ";
            var currentContent = textarea.value;

            if (currentContent.includes("#" + tag)) {
                console.log("[MemoRouter] Tag already present: #" + tag);
                return;
            }

            textarea.value = hashTag + currentContent;

            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype,
                "value"
            ).set;
            nativeInputValueSetter.call(textarea, hashTag + currentContent);
            textarea.dispatchEvent(new Event("input", { bubbles: true }));

            textarea.focus();
            textarea.setSelectionRange(hashTag.length, hashTag.length);

            console.log("[MemoRouter] Inserted tag: #" + tag);
            return;
        }

        var editable = document.querySelector(
            '.memo-editor [contenteditable="true"], .cm-content'
        );

        if (editable) {
            var hashTag = "#" + tag + " ";

            if (editable.textContent.includes("#" + tag)) {
                console.log("[MemoRouter] Tag already present: #" + tag);
                return;
            }

            var textNode = document.createTextNode(hashTag);
            if (editable.firstChild) {
                editable.insertBefore(textNode, editable.firstChild);
            } else {
                editable.appendChild(textNode);
            }

            editable.dispatchEvent(new Event("input", { bubbles: true }));
            console.log("[MemoRouter] Inserted tag: #" + tag);
            return;
        }

        console.warn("[MemoRouter] Could not find editor element");
    }

    function startObserver() {
        var lastCheck = 0;

        var observer = new MutationObserver(function () {
            var now = Date.now();
            if (now - lastCheck < DEBOUNCE_MS) return;
            lastCheck = now;

            var editor = document.querySelector(".memo-editor");
            var picker = document.getElementById("memo-category-picker");

            if (editor && !picker && categories.length > 0) {
                injectDropdown();
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    async function init() {
        await loadConfig();
        await fetchCategories();

        if (categories.length === 0) {
            console.warn(
                "[MemoRouter] No categories loaded. Is the router running?"
            );
        }

        injectDropdown();
        startObserver();

        setInterval(async function () {
            await fetchCategories();
            var existing = document.getElementById("memo-category-picker");
            if (existing) existing.remove();
            injectDropdown();
        }, REFRESH_INTERVAL_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
