/**
 * Nine Frogs — keyboard shortcuts for card review.
 *   A / a  →  Approve current card
 *   R / r  →  Reject current card
 *
 * Only active when focus is NOT in a text input or textarea.
 */
document.addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  if (e.key === "a" || e.key === "A") {
    const btn = document.getElementById("btn-approve");
    if (btn) { btn.click(); }
  }

  if (e.key === "r" || e.key === "R") {
    const btn = document.getElementById("btn-reject");
    if (btn) { btn.click(); }
  }
});
