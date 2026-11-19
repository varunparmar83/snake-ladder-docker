(function () {
  const API_URL = "/api/chat";

  const box = document.createElement("div");
  box.innerHTML = `
    <div style="position:fixed;bottom:16px;right:16px;width:280px;background:#fff;
         border:1px solid #888;border-radius:8px;font:14px sans-serif;z-index:9999;color:#000">
      <div style="padding:8px;background:#1e3a8a;color:#fff;border-radius:8px 8px 0 0">Snakey helper</div>
      <div id="snakey-log" style="height:160px;overflow:auto;padding:8px"></div>
      <form id="snakey-form" style="display:flex;border-top:1px solid #ccc">
        <input id="snakey-input" maxlength="300" placeholder="Ask about the rules..." style="flex:1;border:0;padding:8px">
        <button style="border:0;padding:8px">Send</button>
      </form>
    </div>`;
  document.body.appendChild(box);

  const logEl = document.getElementById("snakey-log");
  const add = (who, text) => {
    const p = document.createElement("p");
    p.style.margin = "4px 0";
    p.textContent = who + ": " + text;
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
  };

  document.getElementById("snakey-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("snakey-input");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    add("You", message);
    try {
      const r = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!r.ok) throw new Error("bad status " + r.status);
      const data = await r.json();
      add("Snakey", data.reply);
    } catch (err) {
      add("Snakey", "Sorry, I can't answer right now.");
      console.error(err);
    }
  });
})();
