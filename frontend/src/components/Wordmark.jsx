// Розміри знака й тексту йдуть у парі, щоб знак завжди був трохи вищим за
// великі літери — так локап читається як єдине ціле.
const SIZES = {
  sm: { text: 'text-sm', mark: 'h-7' },
  lg: { text: 'text-2xl', mark: 'h-11' },
};

/**
 * Логотип: знак (біла машина + бурштинова стрілка) + «KAPOT» (бурштин) із тихим
 * дескриптором «TRACKER». Єдиний варіант для всіх місць — хедер, логін, лендінг,
 * листи. (Бурштиновий суцільний знак лишається тільки для іконки застосунку.)
 */
export default function Wordmark({ size = 'sm', className = '' }) {
  const s = SIZES[size] || SIZES.sm;
  return (
    <span className={`inline-flex items-center gap-2 whitespace-nowrap ${className}`}>
      <img src="/logo-mark-white.png" alt="" aria-hidden="true" className={`${s.mark} w-auto`} />
      {/* «KAPOT» — герой (бурштин); «TRACKER» — тихий дескриптор: менший,
          приглушений, з розрядкою. inline-flex + items-center вирівнює менше
          слово по центру більшого, щоб не сідало нижче за базовою лінією. */}
      <span
        className={`inline-flex translate-y-[0.08em] items-center font-display font-semibold tracking-[0.02em] ${s.text}`}
      >
        <span className="text-amber">KAPOT</span>
        <span className="ml-[0.35em] text-[0.62em] tracking-[0.13em] text-mist">TRACKER</span>
      </span>
    </span>
  );
}
