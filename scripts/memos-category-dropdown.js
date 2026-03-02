// ============================================================================
// FILE: memos-category-dropdown.js
// PURPOSE: Inject a category picker into the Memos editor (v0.26+)
// INSTALL: Paste into Memos Admin > Settings > System > "Additional script"
// ============================================================================
//
// ROUTER_URL DISCOVERY (tried in order):
// 1. ROUTER_URL_OVERRIDE (if set before this script)
// 2. router.<domain> (convention: replace first subdomain with "router")
// 3. Same host on port 8780 (local/dev without reverse proxy)
//
// To hardcode the router URL, set this BEFORE pasting this script:
//   var ROUTER_URL_OVERRIDE = "https://router.chonkie.io";
// ============================================================================

(function () {
    "use strict";

    var ROUTER_URL = "";
    var TAG_PREFIX = "box/";
    var POLL_INTERVAL_MS = 2000;
    var REFRESH_INTERVAL_MS = 300000;
    var DEBOUNCE_MS = 800;

    var categories = [];

    // ---- Router discovery & config ----

    async function loadConfig() {
        var candidates = [];

        if (typeof ROUTER_URL_OVERRIDE !== "undefined" && ROUTER_URL_OVERRIDE) {
            candidates.push(ROUTER_URL_OVERRIDE);
        }

        var host = window.location.hostname;
        var parts = host.split(".");
        if (parts.length >= 2) {
            parts[0] = "router";
            candidates.push(window.location.protocol + "//" + parts.join("."));
        }

        candidates.push(window.location.protocol + "//" + host + ":8780");

        for (var i = 0; i < candidates.length; i++) {
            try {
                var resp = await fetch(candidates[i] + "/web-config", {
                    signal: AbortSignal.timeout(3000),
                });
                if (!resp.ok) continue;
                var cfg = await resp.json();
                ROUTER_URL = candidates[i];
                TAG_PREFIX = cfg.tag_prefix || TAG_PREFIX;
                POLL_INTERVAL_MS = cfg.poll_interval_ms || POLL_INTERVAL_MS;
                REFRESH_INTERVAL_MS = cfg.refresh_interval_ms || REFRESH_INTERVAL_MS;
                DEBOUNCE_MS = cfg.debounce_ms || DEBOUNCE_MS;
                console.log("[MemoRouter] Config loaded from " + ROUTER_URL);
                return;
            } catch (_) {
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
            console.log("[MemoRouter] Loaded " + categories.length + " categories");
            return categories;
        } catch (err) {
            console.warn("[MemoRouter] Failed to fetch categories:", err.message);
            return [];
        }
    }

    // ---- DOM helpers for Memos v0.26 ----
    // v0.26 uses a plain <textarea> inside a flex column container.
    // There are no semantic class names — everything is Tailwind utility classes.
    // We find the textarea, then walk up to find the editor wrapper.

    function findEditorTextarea() {
        var textareas = document.querySelectorAll("textarea");
        for (var i = 0; i < textareas.length; i++) {
            var ta = textareas[i];
            if (
                ta.offsetHeight > 0 &&
                ta.offsetWidth > 0 &&
                !ta.readOnly &&
                !ta.disabled
            ) {
                return ta;
            }
        }
        return null;
    }

    function findEditorWrapper(textarea) {
        // Walk up from the textarea to find the outermost editor container.
        // In v0.26 the structure is roughly:
        //   div (editor wrapper with border/shadow)
        //     div (content area with textarea)
        //     div (metadata row)
        //     div (toolbar row with buttons)
        // We look for a parent that has multiple child divs (content + toolbar).
        var el = textarea.parentElement;
        for (var depth = 0; depth < 8 && el; depth++) {
            if (el.children.length >= 2) {
                var hasTextareaChild = el.querySelector("textarea") === textarea;
                var hasButtons = el.querySelector('button[type="submit"], button svg');
                if (hasTextareaChild && hasButtons) {
                    return el;
                }
            }
            el = el.parentElement;
        }
        return textarea.parentElement;
    }

    // ---- Dropdown injection ----

    function injectDropdown() {
        if (document.getElementById("memo-category-picker")) return true;

        var textarea = findEditorTextarea();
        if (!textarea) return false;

        var wrapper = findEditorWrapper(textarea);
        if (!wrapper) return false;

        var container = document.createElement("div");
        container.id = "memo-category-picker";
        container.style.cssText =
            "display:flex; gap:4px; padding:4px 8px; flex-wrap:wrap; " +
            "border-bottom:1px solid rgba(128,128,128,0.2); " +
            "align-items:center;";

        var label = document.createElement("span");
        label.textContent = "Box:";
        label.style.cssText =
            "font-size:12px; opacity:0.6; font-weight:600; margin-right:2px;";
        container.appendChild(label);

        categories.forEach(function (cat) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = "#" + cat.slug;
            btn.title = cat.description || cat.slug;
            btn.style.cssText =
                "font-size:11px; padding:1px 8px; border-radius:12px; " +
                "border:1px solid rgba(128,128,128,0.3); cursor:pointer; " +
                "background:transparent; transition:all 0.15s; line-height:1.6;";

            btn.addEventListener("mouseenter", function () {
                btn.style.background = "var(--color-primary, #4a90d9)";
                btn.style.color = "#fff";
                btn.style.borderColor = "var(--color-primary, #4a90d9)";
            });
            btn.addEventListener("mouseleave", function () {
                btn.style.background = "transparent";
                btn.style.color = "inherit";
                btn.style.borderColor = "rgba(128,128,128,0.3)";
            });

            btn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                insertTag(TAG_PREFIX + cat.slug, textarea);
            });

            container.appendChild(btn);
        });

        wrapper.insertBefore(container, wrapper.firstChild);
        console.log("[MemoRouter] Category picker injected");
        return true;
    }

    // ---- Tag insertion into textarea ----

    function insertTag(tag, textarea) {
        if (!textarea) {
            textarea = findEditorTextarea();
        }
        if (!textarea) {
            console.warn("[MemoRouter] No textarea found");
            return;
        }

        var hashTag = "#" + tag + " ";
        var current = textarea.value;

        if (current.includes("#" + tag)) {
            console.log("[MemoRouter] Tag already present: #" + tag);
            return;
        }

        var newValue = hashTag + current;

        // Use the native setter so React picks up the change
        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype,
            "value"
        ).set;
        nativeSetter.call(textarea, newValue);

        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        textarea.focus();
        textarea.setSelectionRange(hashTag.length, hashTag.length);

        console.log("[MemoRouter] Inserted tag: #" + tag);
    }

    // ---- MutationObserver to re-inject when DOM changes ----

    function startObserver() {
        var lastCheck = 0;

        var observer = new MutationObserver(function () {
            var now = Date.now();
            if (now - lastCheck < DEBOUNCE_MS) return;
            lastCheck = now;

            if (categories.length > 0 && !document.getElementById("memo-category-picker")) {
                injectDropdown();
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    // ---- Init ----

    async function init() {
        await loadConfig();
        await fetchCategories();

        if (categories.length === 0) {
            console.warn("[MemoRouter] No categories loaded — is the router running?");
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
        setTimeout(init, 500);
    }
})();
