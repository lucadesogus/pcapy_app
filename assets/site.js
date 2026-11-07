// Progressive enhancement only: every page works without JavaScript.
// Adds a "Copy" button to code blocks marked data-copy.
(function () {
  document.querySelectorAll("pre[data-copy]").forEach(function (pre) {
    if (!navigator.clipboard) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy this command");
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(pre.innerText.replace(/^\$ /gm, "").trim()).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1800);
      });
    });
    pre.appendChild(button);
  });
})();
