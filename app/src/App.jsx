import { useEffect, useRef, useState } from "react";

// Touch and timing settings, kept in one place.
const LONG_PRESS_MS = 500; // finger held still this long = right click
const DRAG_PX = 10; // finger moved this far = drag, not a click
const SCROLL_STEP = 2; // wheel units per pixel of a two-finger move
const RECONNECT_MS = 2000; // live screen lost: try again after this long
const STATUS_EVERY_MS = 5000;
const KEY_STORE = "laptop-remote-key";
const TABS = ["Screen", "Sarah", "Controls", "Shell"];

// The key comes once in the link (#key=...) and is remembered on the phone.
function startKey() {
  const fromLink = new URLSearchParams(location.hash.slice(1)).get("key");
  if (fromLink) {
    localStorage.setItem(KEY_STORE, fromLink);
    history.replaceState(null, "", "/");
  }
  return localStorage.getItem(KEY_STORE) || "";
}

function useApi(key, onWrongKey) {
  return async (path, body) => {
    const response = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: body && JSON.stringify(body),
    });
    if (response.status === 401) onWrongKey();
    if (!response.ok) throw new Error(`${response.status}`);
    return response;
  };
}

export default function App() {
  const [key, setKey] = useState(startKey);
  const [tab, setTab] = useState(TABS[0]);
  const [info, setInfo] = useState(null);
  const [status, setStatus] = useState(null);
  const logout = () => {
    localStorage.removeItem(KEY_STORE);
    setKey("");
  };
  const api = useApi(key, logout);

  useEffect(() => {
    if (!key) return;
    api("/api/info").then((r) => r.json()).then(setInfo).catch(() => {});
    const poll = () => api("/api/status").then((r) => r.json()).then(setStatus).catch(() => setStatus(null));
    poll();
    const timer = setInterval(poll, STATUS_EVERY_MS);
    return () => clearInterval(timer);
  }, [key]);

  if (!key) return <Login onKey={(k) => (localStorage.setItem(KEY_STORE, k), setKey(k))} />;

  return (
    <div className="app">
      <header>
        <b>{info?.name || "Laptop"}</b>
        <span className={`dot ${status ? "on" : ""}`} />
        {status && (
          <span className="chips">
            {status.battery != null && <span>🔋{status.battery}%{status.plugged ? "⚡" : ""}</span>}
            <span>CPU {Math.round(status.cpu)}%</span>
            <span>RAM {Math.round(status.ram)}%</span>
          </span>
        )}
      </header>
      <main>
        {tab === "Screen" && <Screen keyValue={key} info={info} api={api} />}
        {tab === "Sarah" && <Sarah api={api} />}
        {tab === "Controls" && <Controls api={api} info={info} status={status} setStatus={setStatus} onLogout={logout} />}
        {tab === "Shell" && <Shell api={api} enabled={info?.shell} />}
      </main>
      <nav>
        {TABS.map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
    </div>
  );
}

function Login({ onKey }) {
  const [value, setValue] = useState("");
  return (
    <div className="login">
      <h1>Laptop Remote</h1>
      <p>Open the link from the ntfy notification, or paste the key from the laptop's logs\remote.log.</p>
      <input value={value} onChange={(e) => setValue(e.target.value.trim())} placeholder="Key" autoCapitalize="off" />
      <button disabled={!value} onClick={() => onKey(value)}>
        Connect
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ screen

function Screen({ keyValue, info, api }) {
  const img = useRef(null);
  const ws = useRef(null);
  const touch = useRef({});
  const [live, setLive] = useState(false);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");

  // One frame at a time: the next is asked for when this one is on screen.
  useEffect(() => {
    let closed = false;
    let retry;
    let lastUrl;
    const connect = () => {
      if (closed || document.hidden) return;
      const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?key=${encodeURIComponent(keyValue)}`);
      socket.binaryType = "blob";
      socket.onopen = () => (setLive(true), socket.send(JSON.stringify({ t: "frame" })));
      socket.onmessage = (event) => {
        const url = URL.createObjectURL(event.data);
        img.current.onload = () => {
          if (lastUrl) URL.revokeObjectURL(lastUrl);
          lastUrl = url;
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ t: "frame" }));
        };
        img.current.src = url;
      };
      socket.onclose = () => {
        setLive(false);
        retry = setTimeout(connect, RECONNECT_MS);
      };
      ws.current = socket;
    };
    // The phone app in the background: stop, so no mobile data is used.
    const onVisible = () => (document.hidden ? ws.current?.close() : connect());
    document.addEventListener("visibilitychange", onVisible);
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      document.removeEventListener("visibilitychange", onVisible);
      ws.current?.close();
    };
  }, [keyValue]);

  const send = (event) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(event));
  const where = (t) => {
    const r = img.current.getBoundingClientRect();
    const clamp = (v) => Math.min(1, Math.max(0, v));
    return { x: clamp((t.clientX - r.left) / r.width), y: clamp((t.clientY - r.top) / r.height) };
  };

  // One finger: tap = click, hold = right click, move = drag. Two fingers: scroll.
  const onTouchStart = (e) => {
    const s = touch.current;
    clearTimeout(s.hold);
    if (e.touches.length === 2) {
      Object.assign(s, { scrollY: (e.touches[0].clientY + e.touches[1].clientY) / 2, used: true, dragging: false });
      return;
    }
    const t = e.touches[0];
    Object.assign(s, { x0: t.clientX, y0: t.clientY, at: where(t), used: false, dragging: false, scrollY: null });
    s.hold = setTimeout(() => {
      s.used = true;
      send({ t: "click", b: "right", ...s.at });
    }, LONG_PRESS_MS);
  };
  const onTouchMove = (e) => {
    const s = touch.current;
    if (e.touches.length === 2 && s.scrollY != null) {
      const y = (e.touches[0].clientY + e.touches[1].clientY) / 2;
      const dy = (s.scrollY - y) * SCROLL_STEP;
      if (Math.abs(dy) >= 1) send({ t: "scroll", dy: Math.round(dy) }), (s.scrollY = y);
      return;
    }
    const t = e.touches[0];
    if (s.used && !s.dragging) return;
    if (!s.dragging && Math.hypot(t.clientX - s.x0, t.clientY - s.y0) > DRAG_PX) {
      clearTimeout(s.hold);
      Object.assign(s, { dragging: true, used: true });
      send({ t: "down", ...s.at });
    }
    if (s.dragging) send({ t: "move", ...(s.at = where(t)) });
  };
  const onTouchEnd = (e) => {
    const s = touch.current;
    clearTimeout(s.hold);
    if (e.touches.length) return;
    if (s.dragging) send({ t: "up", ...s.at });
    else if (!s.used) send({ t: "click", ...s.at });
    s.used = true;
  };

  const download = async () => {
    const blob = await (await api("/api/screenshot")).blob();
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `screen-${Date.now()}.png` });
    a.click();
  };

  return (
    <div className="screen">
      <div className="view">
        <img ref={img} alt="" onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd} onContextMenu={(e) => e.preventDefault()} />
        {!live && <div className="wait">Connecting…</div>}
      </div>
      <div className="bar">
        <button onClick={() => setTyping(!typing)}>⌨️ Keyboard</button>
        <button onClick={download}>📸 Screenshot</button>
      </div>
      {typing && (
        <div className="keyboard">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (text) send({ t: "text", s: text });
              setText("");
            }}
          >
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type on the laptop" autoCapitalize="off" autoCorrect="off" />
            <button>Send</button>
          </form>
          <div className="keys">
            {Object.keys(info?.keys || {}).map((k) => (
              <button key={k} onClick={() => send({ t: "keys", keys: info.keys[k] })}>
                {k}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- sarah

function Sarah({ api }) {
  const [said, setSaid] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const ask = async (e) => {
    e.preventDefault();
    if (!text || busy) return;
    const question = text;
    setText("");
    setBusy(true);
    setSaid((s) => [...s, { me: true, text: question }]);
    try {
      const { reply } = await (await api("/api/sarah", { text: question })).json();
      setSaid((s) => [...s, { text: reply || "(no answer)" }]);
    } catch {
      setSaid((s) => [...s, { text: "The laptop did not answer." }]);
    }
    setBusy(false);
  };
  return (
    <div className="sarah">
      <div className="talk">
        {!said.length && <p className="hint">Type what you would say after "Hey Sarah". The keyboard's 🎤 lets you speak it.</p>}
        {said.map((m, i) => (
          <div key={i} className={m.me ? "me" : "her"}>
            {m.text}
          </div>
        ))}
        {busy && <div className="her">…</div>}
      </div>
      <form onSubmit={ask}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="play despacito" />
        <button disabled={busy}>Send</button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- controls

function Controls({ api, info, status, setStatus, onLogout }) {
  const [level, setLevel] = useState(null);
  const shown = level ?? status?.volume ?? 0;
  const volume = (body) => api("/api/volume", body).then((r) => r.json()).then(setStatus).catch(() => {});
  const act = (a) => (!a.confirm || confirm(`Really ${a.name}?`)) && api("/api/action", { name: a.name }).catch(() => {});
  return (
    <div className="controls">
      <section>
        <h2>
          Volume {shown}% {status?.muted && "· muted"}
        </h2>
        <input type="range" min="0" max="100" value={shown} onChange={(e) => setLevel(+e.target.value)} onPointerUp={() => volume({ level: shown }).then(() => setLevel(null))} />
        <div className="row">
          <button onClick={() => volume({ mute: !status?.muted })}>{status?.muted ? "🔊 Unmute" : "🔇 Mute"}</button>
          {info?.media.map((m) => (
            <button key={m} onClick={() => api("/api/media", { name: m }).catch(() => {})}>
              {m}
            </button>
          ))}
        </div>
      </section>
      <section>
        <h2>Laptop</h2>
        <div className="row">
          {info?.actions.map((a) => (
            <button key={a.name} className={a.confirm ? "warn" : ""} onClick={() => act(a)}>
              {a.name}
            </button>
          ))}
        </div>
      </section>
      <button className="link" onClick={onLogout}>
        Log out on this phone
      </button>
    </div>
  );
}

// ------------------------------------------------------------------- shell

function Shell({ api, enabled }) {
  const [cmd, setCmd] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { output, code } = await (await api("/api/shell", { cmd })).json();
      setOut(`PS> ${cmd}\n${output}\n(exit ${code})`);
    } catch {
      setOut("The laptop did not answer.");
    }
    setBusy(false);
  };
  if (enabled === false) return <p className="hint">The PowerShell box is switched off in config.yaml.</p>;
  return (
    <div className="shell">
      <form onSubmit={run}>
        <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder="Get-Process | Sort CPU -desc | Select -First 5" autoCapitalize="off" autoCorrect="off" />
        <button disabled={busy || !cmd}>{busy ? "…" : "Run"}</button>
      </form>
      <pre>{out}</pre>
    </div>
  );
}
