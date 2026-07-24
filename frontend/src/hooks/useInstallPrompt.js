import { useEffect, useState } from 'react';

// Everything the "Add to Home Screen" feature needs to decide what to show.
//
// Install support is split by platform:
//  - Chrome/Edge (Android + desktop) fire `beforeinstallprompt`; we stash it and
//    can trigger the native install dialog with one tap.
//  - iOS Safari has NO programmatic install — Apple only allows the manual
//    Share → "Add to Home Screen" flow, so we show instructions instead.
//  - iOS non-Safari browsers can't install a PWA at all (only Safari can).
//  - Already-installed (standalone) → nothing to offer.

function isStandalone() {
  try {
    return (
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true // iOS Safari
    );
  } catch {
    return false;
  }
}

function detectPlatform() {
  const ua = navigator.userAgent || '';
  const isIOS = /iphone|ipad|ipod/i.test(ua) ||
    // iPadOS 13+ reports as a Mac; the touch check tells it apart.
    (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
  // On iOS every browser is really Safari's engine, but only actual Safari can
  // install. CriOS/FxiOS/EdgiOS are Chrome/Firefox/Edge skins that cannot.
  const isIOSSafari = isIOS && /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
  return { isIOS, isIOSSafari };
}

export default function useInstallPrompt() {
  const [deferred, setDeferred] = useState(null); // the beforeinstallprompt event
  const [installed, setInstalled] = useState(isStandalone());
  const { isIOS, isIOSSafari } = detectPlatform();

  useEffect(() => {
    const onPrompt = (e) => {
      e.preventDefault(); // stop Chrome's mini-infobar; we drive it ourselves
      setDeferred(e);
    };
    const onInstalled = () => {
      setInstalled(true);
      setDeferred(null);
    };
    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, []);

  // Fire the native install dialog (Chrome/Edge). Resolves true if accepted.
  async function promptInstall() {
    if (!deferred) return false;
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    setDeferred(null);
    return outcome === 'accepted';
  }

  return {
    installed, // already added to home screen → hide the feature
    canPrompt: !!deferred, // a one-tap native install is available
    isIOS,
    isIOSSafari, // show the manual Share instructions
    promptInstall,
  };
}
