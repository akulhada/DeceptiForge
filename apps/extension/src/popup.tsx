// Purpose: extension popup — enrollment, connection/policy status, privacy explanation, and a
//   pause/resume control when policy allows.
// Responsibilities: enroll with a one-time token + backend URL, show sensor/policy/registry health
//   and monitored domains, and toggle pause. Renders only safe status — never pasted text, trace
//   details, or the secret. Dependencies: storage, types, chrome.runtime.
import { useEffect, useState } from 'react';

import { loadState, saveState } from '~lib/storage';
import type { StoredState } from '~lib/types';

const VERSION =
  typeof chrome !== 'undefined' && chrome.runtime?.getManifest
    ? chrome.runtime.getManifest().version
    : '0.0.0';

export default function Popup() {
  const [state, setState] = useState<StoredState | null>(null);
  const [baseUrl, setBaseUrl] = useState('http://localhost:8000');
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadState().then(setState);
  }, []);

  async function enroll() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${baseUrl}/browser-sensors/enroll`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          token,
          name: 'browser',
          installation_id: crypto.randomUUID(),
          browser_family: 'chromium',
          extension_version: VERSION,
        }),
      });
      if (!res.ok) {
        setError('Enrollment failed. Check the token and try again.');
        return;
      }
      const data = (await res.json()) as {
        sensor_public_id: string;
        organization_id: string;
        signing_secret: string;
        api_key: string;
      };
      const next: StoredState = {
        sensor_public_id: data.sensor_public_id,
        signing_secret: data.signing_secret,
        api_key: data.api_key,
        organization_id: data.organization_id,
        base_url: baseUrl,
        paused: false,
      };
      await saveState(next);
      setState(next);
      setToken('');
    } catch {
      setError(`Cannot reach the backend at ${baseUrl}.`);
    } finally {
      setBusy(false);
    }
  }

  async function togglePause() {
    if (!state) return;
    const next = { ...state, paused: !state.paused };
    await saveState(next);
    setState(next);
  }

  const wrap = { padding: 12, width: 320, fontFamily: 'system-ui, sans-serif', fontSize: 13 };

  if (!state) {
    return (
      <div style={wrap}>
        <h3>DeceptiForge sensor</h3>
        <p>Enroll this browser with a one-time token from your administrator.</p>
        <label>
          Backend URL
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: '100%' }}
          />
        </label>
        <label>
          Enrollment token
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: '100%' }}
          />
        </label>
        {error && <p style={{ color: 'crimson' }}>{error}</p>}
        <button disabled={busy || !token} onClick={() => void enroll()}>
          {busy ? 'Enrolling…' : 'Enroll'}
        </button>
        <p style={{ color: '#666' }}>
          This extension observes only explicit pastes into approved AI domains and reports only a
          trace identifier and destination classification. It never captures your prompts, pasted
          text, AI responses, browsing history, or clipboard.
        </p>
      </div>
    );
  }

  const policy = state.policy;
  const allowPause = policy?.allow_pause ?? true;
  return (
    <div style={wrap}>
      <h3>DeceptiForge sensor</h3>
      <p>
        Status: <strong>{state.paused ? 'Paused' : policy?.enabled ? 'Active' : 'Idle'}</strong>
        {' · '}v{VERSION}
      </p>
      <p>Sensor: {state.sensor_public_id}</p>
      <p>Policy version: {policy?.policy_version ?? '—'}</p>
      <p>Monitored AI domains: {policy?.monitored_domains?.join(', ') || 'none configured'}</p>
      <p>Registry entries: {state.registry?.entries.length ?? 0}</p>
      <p>Last policy sync: {state.last_policy_sync?.slice(0, 19) ?? 'never'}</p>
      {allowPause && (
        <button onClick={() => void togglePause()}>{state.paused ? 'Resume' : 'Pause'}</button>
      )}
      <p style={{ color: '#666' }}>
        Only a matched trace identifier and the destination classification are reported. Pasted
        text, prompts, AI responses, history, and clipboard are never captured or sent.
      </p>
    </div>
  );
}
