"""Light / Dark / System selector in the top-right of the header.

Streamlit (1.66) has no Python API for changing the active theme: the switch lives in its browser
code, behind the ⋮ menu. So the selector drives that real switch instead of faking one: a click opens
the (invisible) menu, clicks Streamlit's own theme item and closes it again. Streamlit then applies
the theme immediately and remembers it across reruns, navigation and reloads, exactly as if the menu
had been used. The selector reads the remembered choice from the same place to show which is active.

This depends on Streamlit internals (the menu's data-testids and its localStorage key), which is
unavoidable without a public API; check it in a browser after upgrading Streamlit. The script is a
fixed string with no user data in it. It must not contain "<" followed by a letter or "/" (not even
in a comment): Streamlit's HTML sanitiser (DOMPurify) then drops the whole <script> silently.
"""
import streamlit as st

THEMES = ("Light", "Dark", "System")

_BUTTONS = "".join(
    f'<button type="button" role="radio" data-tt-theme="{name}">{name}</button>' for name in THEMES
)

_SCRIPT = """
<script>
(() => {
  if (window.__ttTheme) { window.__ttTheme.sync(); return; }
  const THEMES = ["Light", "Dark", "System"];

  // Streamlit stores the choice as JSON under "stActiveTheme-" + path + "-v" + version; none = System.
  const active = () => {
    try {
      const key = Object.keys(localStorage).find(k => k.startsWith("stActiveTheme-" + location.pathname + "-"));
      const value = key ? JSON.parse(localStorage.getItem(key)) : null;
      const name = value && typeof value === "object" ? value.name : value;
      return THEMES.includes(name) ? name : "System";
    } catch (e) {
      return "System";
    }
  };
  const sync = (name = active()) => document.querySelectorAll(".tt-theme [data-tt-theme]")
    .forEach(b => b.setAttribute("aria-checked", String(b.dataset.ttTheme === name)));

  // Resolve with the element once it is in the DOM (Streamlit renders the menu asynchronously).
  const whenPresent = (selector, done) => {
    const now = document.querySelector(selector);
    if (now) return done(now);
    const observer = new MutationObserver(() => {
      const el = document.querySelector(selector);
      if (el) { observer.disconnect(); clearTimeout(timer); done(el); }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    const timer = setTimeout(() => { observer.disconnect(); done(null); }, 2000);
  };
  const closeMenu = () => {
    const esc = () => new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true });
    const popover = document.querySelector('[data-testid="stMainMenuPopover"]');
    if (popover) popover.dispatchEvent(esc());
    document.dispatchEvent(esc());
  };
  const pick = name => {
    const menu = document.querySelector('[data-testid="stMainMenuButton"]');
    if (!menu) return console.warn("TubeTalk: Streamlit's theme menu was not found");
    menu.click();
    whenPresent(`[data-testid="stMainMenuItem-theme-${name}"]`, item => {
      if (item) item.click();
      else console.warn("TubeTalk: Streamlit's theme option was not found");
      closeMenu();
      sync();
    });
  };

  document.addEventListener("click", event => {
    const button = event.target.closest(".tt-theme [data-tt-theme]");
    // After this click has finished, so the menu does not treat it as a click outside and close.
    if (button) setTimeout(() => pick(button.dataset.ttTheme), 0);
  });
  // Streamlit may re-create the selector's markup (e.g. when switching pages); mark it again.
  new MutationObserver(() => {
    if (document.querySelector(".tt-theme [data-tt-theme]:not([aria-checked])")) sync();
  }).observe(document.body, { childList: true, subtree: true });

  window.__ttTheme = { sync };
  sync();
})();
</script>
"""

_HTML = f'<div class="tt-theme" role="radiogroup" aria-label="Theme">{_BUTTONS}</div>{_SCRIPT}'


def render() -> None:
    """Call once per run, early and in the same position on every page, so it is never re-created."""
    st.html(_HTML, unsafe_allow_javascript=True)
