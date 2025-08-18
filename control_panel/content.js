(function() {
  const panel = document.createElement("div");
  panel.id = "trace-monster-panel";
  panel.innerHTML = `
    <button id="toggle-panel">TraceMonster</button>
    <div id="env-panel" style="display:none;">
      <h2>ENVIRONMENT CONTROL PANEL</h2>
      <div class="row"><span>Cookies</span>
        <select id="cookies-setting">
          <option value="keep">Keep</option>
          <option value="clear">Clear</option>
        </select>
      </div>
      <div class="row">
        <span>Proxy Pool</span>
        <select id="proxy-setting">
          <option value="US-East">US-East</option>
          <option value="Korea">Korea</option>
        </select>
      </div>
      <div class="row">
        <span>UA Profile</span>
        <select id="ua-setting">
          <option value="Desktop">Desktop</option>
          <option value="Mobile">Mobile</option>
        </select>
      </div>
      <div class="row" style="justify-content: center;">
        <button id="apply-settings">Apply</button>
      </div>
    </div>
  `;
  document.body.appendChild(panel);

  const toggleBtn = document.getElementById("toggle-panel");
  const envPanel = document.getElementById("env-panel");
  toggleBtn.onclick = () => {
    envPanel.style.display = envPanel.style.display === "none" ? "block" : "none";
  };

  document.getElementById("apply-settings").onclick = () => {
    const cookies = document.getElementById("cookies-setting").value;
    const proxy = document.getElementById("proxy-setting").value;
    const ua = document.getElementById("ua-setting").value;

    alert(`Settings applied:\nCookies: ${cookies}\nProxy: ${proxy}\nUA: ${ua}`);
    // You can add actual logic here to manipulate cookie, proxy, UA if needed
  };
})();