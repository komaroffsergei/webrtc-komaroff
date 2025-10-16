(function(){
  // Whitelist-only logger. Accepts events strictly related to WebRTC connection and server responses.
  // Allowed tags (first argument):
  //   [pc], [ice], [signaling], [server]
  const ALLOWED_PREFIXES = ['[pc]', '[ice]', '[signaling]', '[server]'];

  function ts(){ return /*new Date().toISOString()*/ ''; }

  function format(arg){
    if (arg instanceof Error){ return `${arg.name}: ${arg.message}`; }
    if (arg && typeof arg === 'object'){
      try { return JSON.stringify(arg); } catch{ return String(arg); }
    }
    return String(arg);
  }

  const state = { el: null, auto: true, maxLines: 2000 };

  function write(line){
    if (!state.el) return;
    state.el.textContent += line + '\n';
    const lines = state.el.textContent.split(/\n/);
    if (lines.length > state.maxLines){
      state.el.textContent = lines.slice(lines.length - state.maxLines).join('\n');
    }
    if (state.auto){ state.el.scrollTop = state.el.scrollHeight; }
  }

  function allowed(tag){
    return typeof tag === 'string' && ALLOWED_PREFIXES.some(p => tag.startsWith(p));
  }

  function emit(){
    if (arguments.length === 0) return;
    const tag = arguments[0];
    if (!allowed(tag)) return; // ignore everything except WebRTC connection and server events
    const parts = Array.from(arguments).map(format);
    write(parts.join(' '));
  }

  // Helper for logging server responses. Use as AppLog.server('offer', respOrError)
  function server(op, payload){
    try{
      if (payload && typeof payload === 'object' && 'ok' in payload && 'status' in payload){
        // Fetch Response-like
        emit('[server]', `${op}`, { ok: payload.ok, status: payload.status });
      } else {
        emit('[server]', `${op}`, payload);
      }
    }catch(e){ /* swallow */ }
  }

  function init(opts){
    state.el = opts.el;
    state.auto = !!opts.auto;
    state.maxLines = opts.maxLines || state.maxLines;
    if (opts.clearBtn){ opts.clearBtn.addEventListener('click', ()=>{ state.el.textContent = ''; }); }
    if (opts.autoChk){
      opts.autoChk.addEventListener('change', ()=>{ state.auto = !!opts.autoChk.checked; });
      state.auto = !!opts.autoChk.checked;
    }
  }

  window.AppLog = { emit, init, server };
})();
