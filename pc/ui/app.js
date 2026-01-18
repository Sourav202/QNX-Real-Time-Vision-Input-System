const $ = (id) => document.getElementById(id);

const secondsEl = $("seconds");
const expectedEl = $("expected");
const triggerBtn = $("triggerBtn");
const refreshBtn = $("refreshBtn");
const statusText = $("statusText");
const progressBar = $("progressBar");
const lastResult = $("lastResult");
const lastClip = $("lastClip");
const clipList = $("clipList");
const player = $("player");
const selectedName = $("selectedName");
const serverPill = $("serverPill");

let pollTimer = null;

function setStatus(text, pct=null) {
  statusText.textContent = text;
  if (pct === null) return;
  progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

async function api(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return await r.json();
}

function fmtBytes(bytes){
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

function renderClips(clips) {
  clipList.innerHTML = "";

  if (!clips.length) {
    clipList.innerHTML = `<div class="mono">No clips yet.</div>`;
    return;
  }

  for (const c of clips) {
    const el = document.createElement("div");
    el.className = "clipItem";
    el.innerHTML = `
      <div class="clipLeft">
        <div class="clipTitle">${c.name}</div>
        <div class="clipSub">${new Date(c.mtime_ms).toLocaleString()} • ${fmtBytes(c.size_bytes)}</div>
      </div>
      <div class="badge">Play</div>
    `;
    el.onclick = () => {
      const url = `/incoming/${encodeURIComponent(c.name)}`;
      player.src = url;
      selectedName.textContent = c.name;
      player.play().catch(()=>{});
    };
    clipList.appendChild(el);
  }
}

async function refresh() {
  try {
    const info = await api("/api/info");
    serverPill.textContent = `Server: ${info.server} • Incoming: ${info.incoming_dir}`;
  } catch {
    serverPill.textContent = "Server: offline?";
  }

  try {
    const clips = await api("/api/clips");
    renderClips(clips);
  } catch (e) {
    clipList.innerHTML = `<div class="mono">Failed to load clips: ${e.message}</div>`;
  }
}

async function trigger() {
  const seconds = Number(secondsEl.value || 5);
  const expected = Number(expectedEl.value || 0);

  setStatus("Triggering Pi…", 8);
  triggerBtn.disabled = true;

  try {
    // Start trigger
    const r = await api(`/trigger?seconds=${encodeURIComponent(seconds)}&expected=${encodeURIComponent(expected)}&json=1`);
    setStatus(`Triggered. Waiting for upload… (${r.command})`, 20);

    // Start polling server-side “last upload”
    const start = Date.now();
    const timeoutMs = 90_000;

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const st = await api("/api/status");
        if (st.last_upload_name) {
          lastClip.textContent = st.last_upload_name;
        }
        if (st.last_result !== null && st.last_upload_name) {
          // done
          clearInterval(pollTimer);
          pollTimer = null;

          lastResult.textContent = String(st.last_result);
          lastClip.textContent = st.last_upload_name;
          setStatus("Done ✔", 100);

          await refresh();

          // auto load video
          player.src = `/incoming/${encodeURIComponent(st.last_upload_name)}`;
          selectedName.textContent = st.last_upload_name;
          player.play().catch(()=>{});
          triggerBtn.disabled = false;
        } else {
          // still waiting
          const elapsed = Date.now() - start;
          const pct = 20 + Math.min(70, (elapsed / timeoutMs) * 70);
          setStatus("Waiting for upload / classification…", pct);
          if (elapsed > timeoutMs) {
            clearInterval(pollTimer);
            pollTimer = null;
            setStatus("Timed out waiting for result.", 0);
            triggerBtn.disabled = false;
          }
        }
      } catch {
        // keep trying
      }
    }, 700);

  } catch (e) {
    setStatus(`Error: ${e.message}`, 0);
    triggerBtn.disabled = false;
  }
}

triggerBtn.addEventListener("click", trigger);
refreshBtn.addEventListener("click", refresh);

refresh();
