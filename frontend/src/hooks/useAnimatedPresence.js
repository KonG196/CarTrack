import { useCallback, useEffect, useRef, useState } from 'react';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export default function useAnimatedPresence(open, onClose, duration = 200) {
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);
  const timer = useRef(null);
  const selfClosing = useRef(false);

  const clearTimer = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };

  useEffect(() => {
    if (open) {
      clearTimer();
      selfClosing.current = false;
      setMounted(true);
      setClosing(false);
    }
  }, [open]);

  useEffect(() => {
    if (open || !mounted) return;

    if (selfClosing.current) {
      clearTimer();
      setMounted(false);
      setClosing(false);
      selfClosing.current = false;
      return;
    }

    if (prefersReducedMotion()) {
      setMounted(false);
      return;
    }

    setClosing(true);
    clearTimer();
    timer.current = window.setTimeout(() => {
      setMounted(false);
      setClosing(false);
    }, duration);
  }, [open, mounted, duration]);

  useEffect(() => clearTimer, []);

  const requestClose = useCallback(() => {
    if (selfClosing.current) return;
    selfClosing.current = true;

    if (prefersReducedMotion()) {
      onClose?.();
      return;
    }

    setClosing(true);
    clearTimer();
    timer.current = window.setTimeout(() => onClose?.(), duration);
  }, [onClose, duration]);

  return { mounted, closing, requestClose };
}
