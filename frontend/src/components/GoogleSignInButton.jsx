import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

// «Continue with Google» in the app's own style. Google Identity Services only
// styles its own widget, which clashes with the theme — so we render the real
// GIS button hidden and overlay our own. Clicking ours programmatically clicks
// the hidden one, which still hands back a Google ID token through the callback.
//
// The client id is public (it ships in the bundle) and set at build time via
// VITE_GOOGLE_CLIENT_ID. With no id the button doesn't render, so email/password
// stays the only option until Google is set up.
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GIS_SRC = 'https://accounts.google.com/gsi/client';

let gisLoading = null;
function loadGis() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (gisLoading) return gisLoading;
  gisLoading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = GIS_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Failed to load Google Identity Services'));
    document.head.appendChild(s);
  });
  return gisLoading;
}

// Google's four-colour «G». Inline so it needs no network request.
function GoogleIcon() {
  return (
    <svg viewBox="0 0 48 48" className="h-5 w-5 flex-shrink-0" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

export default function GoogleSignInButton({ onCredential, onError }) {
  const { i18n, t } = useTranslation();
  const hiddenRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!CLIENT_ID) return undefined;
    let cancelled = false;

    loadGis()
      .then(() => {
        if (cancelled || !hiddenRef.current) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => {
            if (response?.credential) onCredential(response.credential);
          },
        });
        // The real widget, rendered into a hidden holder purely to capture the
        // click → ID token. Our own button forwards clicks to it.
        window.google.accounts.id.renderButton(hiddenRef.current, {
          type: 'standard',
          theme: 'filled_black',
          size: 'large',
          text: 'continue_with',
          width: 320,
          locale: i18n.language,
        });
        setReady(true);
      })
      .catch((err) => onError?.(err));

    return () => {
      cancelled = true;
    };
  }, [onCredential, onError, i18n.language]);

  if (!CLIENT_ID) return null;

  const forwardClick = () => {
    // The GIS widget renders as an iframe (or a div with a clickable role);
    // find the first clickable element inside our hidden holder and click it.
    const el =
      hiddenRef.current?.querySelector('div[role="button"]') ||
      hiddenRef.current?.querySelector('iframe') ||
      hiddenRef.current?.firstElementChild;
    el?.click?.();
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={forwardClick}
        disabled={!ready}
        className="flex w-full items-center justify-center gap-3 rounded-full border border-edge bg-raised px-4 py-3 text-sm font-semibold text-fg transition-colors hover:border-edge-soft hover:bg-panel disabled:opacity-60"
      >
        <GoogleIcon />
        {t('auth.google.continue')}
      </button>
      {/* The real GIS button, kept out of view but present so its click handler
          runs. Not display:none — GIS won't wire up a hidden button — so it's
          clipped to a 1px box under our own. */}
      <div
        ref={hiddenRef}
        aria-hidden="true"
        className="pointer-events-none absolute left-0 top-0 h-px w-px overflow-hidden opacity-0"
      />
    </div>
  );
}
