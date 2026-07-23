import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

// «Sign in with Google» via Google Identity Services (GIS). The library renders
// its own button into `ref`; on success it hands back a Google ID token (a JWT)
// which we pass to `onCredential` to exchange for our own session.
//
// The client id is public (it ships in the bundle) and set at build time via
// VITE_GOOGLE_CLIENT_ID. With no id configured the button simply doesn't render,
// so email/password stays the only option until Google is set up.
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

export default function GoogleSignInButton({ onCredential, onError }) {
  const { i18n } = useTranslation();
  const holderRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!CLIENT_ID) return undefined;
    let cancelled = false;

    loadGis()
      .then(() => {
        if (cancelled || !holderRef.current) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => {
            // response.credential is the Google ID token (JWT).
            if (response?.credential) onCredential(response.credential);
          },
        });
        window.google.accounts.id.renderButton(holderRef.current, {
          type: 'standard',
          theme: 'filled_black',
          size: 'large',
          shape: 'pill',
          text: 'continue_with',
          logo_alignment: 'center',
          width: holderRef.current.offsetWidth || 320,
          locale: i18n.language,
        });
        setReady(true);
      })
      .catch((err) => onError?.(err));

    return () => {
      cancelled = true;
    };
    // Re-render the button when the UI language changes so its label follows.
  }, [onCredential, onError, i18n.language]);

  if (!CLIENT_ID) return null;

  // The GIS button is injected into this div. min-height keeps the layout from
  // jumping before the async script paints it.
  return (
    <div
      ref={holderRef}
      className="flex min-h-[44px] w-full justify-center overflow-hidden rounded-full"
      aria-busy={!ready}
    />
  );
}
