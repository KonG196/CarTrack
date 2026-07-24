import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, ChevronRight } from 'lucide-react';
import { Card, Button, Modal } from './UI';
import useInstallPrompt from '../hooks/useInstallPrompt';

// The "Add to Home Screen" entry in Settings. Adapts to the platform:
//  - installable (Chrome/Edge) → one tap fires the native install dialog;
//  - iOS Safari → opens step-by-step manual instructions (Apple allows no
//    programmatic install);
//  - iOS non-Safari → tells the user to open it in Safari first;
//  - already installed → renders nothing.
export default function InstallAppCard() {
  const { t } = useTranslation();
  const { installed, canPrompt, isIOS, isIOSSafari, promptInstall } = useInstallPrompt();
  const [showHow, setShowHow] = useState(false);

  if (installed) return null; // already on the home screen — nothing to offer

  // The row's action depends on what the platform supports.
  const onClick = () => {
    if (canPrompt) {
      promptInstall();
    } else {
      setShowHow(true); // iOS (or a browser that hasn't fired the prompt yet)
    }
  };

  const subtitle = canPrompt
    ? t('installApp.subtitleInstall')
    : t('installApp.subtitleHow');

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        className="block w-full text-left transition active:scale-[0.99] motion-reduce:active:scale-100"
      >
        <Card className="flex items-center gap-3 transition-colors hover:border-edge-soft">
          <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber/15">
            <Download className="h-5 w-5 text-amber" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">{t('installApp.title')}</p>
            <p className="truncate text-xs text-mist">{subtitle}</p>
          </div>
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-mist" />
        </Card>
      </button>

      <Modal open={showHow} onClose={() => setShowHow(false)} title={t('installApp.title')} size="sm">
        {isIOS && !isIOSSafari ? (
          // iOS but not Safari — only Safari can install a PWA on iOS.
          <p className="text-sm text-mist">{t('installApp.iosOpenInSafari')}</p>
        ) : isIOS ? (
          <IosSteps t={t} />
        ) : (
          // A desktop/Android browser that didn't expose an install prompt
          // (e.g. Firefox) — point at the menu.
          <p className="text-sm text-mist">{t('installApp.genericHint')}</p>
        )}
        <Button
          onClick={() => setShowHow(false)}
          variant="secondary"
          className="mt-4 w-full"
        >
          {t('common.gotIt')}
        </Button>
      </Modal>
    </>
  );
}

// The manual iOS Safari flow: numbered steps, the first two shown with real
// Safari screenshots so the buttons are unmistakable.
function IosSteps({ t }) {
  const steps = [
    { text: t('installApp.iosStep1'), img: '/install-ios-step1.png' },
    { text: t('installApp.iosStep2'), img: '/install-ios-step2.png' },
    { text: t('installApp.iosStep3'), img: null },
  ];
  return (
    <ol className="space-y-4">
      {steps.map((step, i) => (
        <li key={i} className="space-y-2">
          <div className="flex items-start gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-amber/15 font-mono text-xs font-semibold text-amber">
              {i + 1}
            </span>
            <span className="pt-0.5 text-sm text-fg">{step.text}</span>
          </div>
          {step.img ? (
            <img
              src={step.img}
              alt=""
              loading="lazy"
              className="mx-auto w-40 rounded-xl border border-edge"
            />
          ) : null}
        </li>
      ))}
    </ol>
  );
}
