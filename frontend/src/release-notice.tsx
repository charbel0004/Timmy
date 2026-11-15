import { useEffect, useState } from 'react';
import { freshApplicationUrl } from './release-cache';

export function ReleaseNotice() {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    if (import.meta.env.DEV) return;
    let disposed = false, pending = false;
    const controller = new AbortController();
    async function check() {
      if (pending || document.visibilityState === 'hidden') return;
      pending = true;
      try {
        const response = await fetch(`/app-version.json?t=${Date.now()}`, { cache: 'no-store', signal: controller.signal });
        if (response.ok) {
          const data = await response.json();
          if (!disposed && typeof data.version === 'string' && data.version !== import.meta.env.VITE_RELEASE_ID) setAvailable(true);
        }
      } catch { /* Version checks must never interrupt operational requests. */ }
      finally { pending = false; }
    }
    void check();
    const timer = setInterval(check, 60000);
    window.addEventListener('focus', check);
    return () => { disposed = true; controller.abort(); clearInterval(timer); window.removeEventListener('focus', check); };
  }, []);
  return available ? <aside className="release-notice" role="status"><span>A new version of Timmy is available.</span>
    <button onClick={() => window.location.assign(freshApplicationUrl(window.location.href))}>Reload app</button></aside> : null;
}
