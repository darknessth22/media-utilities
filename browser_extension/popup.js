(async () => {
  const dot = document.getElementById("dot");
  const status = document.getElementById("status");
  const line = document.getElementById("status-line");

  try {
    const res = await chrome.runtime.sendMessage({ type: "videl-ping" });
    if (res && res.ok) {
      dot.classList.add("ok");
      status.textContent = "Connected";
      line.textContent = "Videl is running on 127.0.0.1:17654";
    } else {
      dot.classList.add("err");
      status.textContent = "Not running";
      line.textContent = "Videl desktop app is not reachable. Start it and reopen this popup.";
    }
  } catch (e) {
    dot.classList.add("err");
    status.textContent = "Error";
    line.textContent = String(e && e.message || e);
  }
})();
