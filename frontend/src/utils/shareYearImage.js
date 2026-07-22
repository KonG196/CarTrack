import { formatMoney, formatKm } from './format';
import i18n from '../i18n';

// Draw «Ваш рік з Kapot» to a portrait canvas and share it (Web Share API with
// a file) or download it as a fallback. Returns 'shared' | 'downloaded' |
// 'cancelled'. Canvas uses generic families so it needs no font loading.
const C = {
  bg: '#0B1119',
  panel: '#121A26',
  edge: '#1D2A3E',
  amber: '#FFB454',
  amberInk: '#231708',
  fg: '#E9EEF6',
  mist: '#93A1B8',
};

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function renderYearCanvas(review, carName) {
  const W = 1080;
  const H = 1350;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  const pad = 84;

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, W, H);

  // wordmark
  ctx.textBaseline = 'alphabetic';
  ctx.font = '800 44px sans-serif';
  ctx.fillStyle = C.amber;
  ctx.fillText('KAPOT', pad, 130);
  const kapotW = ctx.measureText('KAPOT').width;
  ctx.font = '700 30px sans-serif';
  ctx.fillStyle = C.mist;
  ctx.fillText('TRACKER', pad + kapotW + 16, 130);

  // title
  ctx.font = '800 108px sans-serif';
  ctx.fillStyle = C.fg;
  ctx.fillText(i18n.t('shareYear.title', { year: review.year }), pad, 300);
  ctx.font = '500 40px sans-serif';
  ctx.fillStyle = C.mist;
  ctx.fillText(carName, pad, 360);

  // total spent hero
  ctx.font = '600 34px sans-serif';
  ctx.fillStyle = C.mist;
  ctx.fillText(i18n.t('shareYear.spentLabel'), pad, 500);
  ctx.font = '800 128px monospace';
  ctx.fillStyle = C.amber;
  ctx.fillText(formatMoney(review.total_spent), pad, 630);

  // stat rows
  const rows = [
    [i18n.t('shareYear.distance'), formatKm(review.km_driven)],
    [
      i18n.t('shareYear.fueled'),
      review.liters != null ? i18n.t('shareYear.litersValue', { liters: review.liters }) : '—',
    ],
    [
      i18n.t('shareYear.consumption'),
      review.avg_consumption_l_100km != null
        ? i18n.t('shareYear.consumptionValue', { value: review.avg_consumption_l_100km.toFixed(1) })
        : '—',
    ],
    [
      i18n.t('shareYear.costPerKm'),
      review.cost_per_km != null
        ? i18n.t('shareYear.costPerKmValue', { amount: formatMoney(review.cost_per_km * 100) })
        : '—',
    ],
  ];
  if (review.cheapest_station) {
    rows.push([i18n.t('shareYear.cheapestStation'), review.cheapest_station.name]);
  }
  if (review.biggest_expense) {
    // Amount only — the truncation loop trims from the right, which would eat
    // the ₴ figure if the title were appended here.
    rows.push([i18n.t('shareYear.biggestExpense'), formatMoney(review.biggest_expense.amount)]);
  }

  let y = 760;
  const rowH = 96;
  for (const [label, value] of rows) {
    ctx.fillStyle = C.panel;
    roundRect(ctx, pad, y, W - pad * 2, rowH - 16, 20);
    ctx.fill();
    ctx.font = '500 34px sans-serif';
    ctx.fillStyle = C.mist;
    ctx.textAlign = 'left';
    ctx.fillText(label, pad + 32, y + 52);
    ctx.font = '700 38px sans-serif';
    ctx.fillStyle = C.fg;
    ctx.textAlign = 'right';
    // truncate very long values so they never overrun
    let text = String(value);
    const maxW = W - pad * 2 - 340;
    while (ctx.measureText(text).width > maxW && text.length > 4) {
      text = text.slice(0, -2);
    }
    if (text !== String(value)) text = text.replace(/…?$/, '…');
    ctx.fillText(text, W - pad - 32, y + 52);
    ctx.textAlign = 'left';
    y += rowH;
  }

  // footer
  ctx.font = '500 30px sans-serif';
  ctx.fillStyle = C.mist;
  ctx.fillText(i18n.t('shareYear.footer'), pad, H - 70);

  return canvas;
}

export async function shareYearImage(review, carName) {
  const canvas = renderYearCanvas(review, carName);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) return 'error';
  const file = new File([blob], `kapot-rik-${review.year}.png`, { type: 'image/png' });

  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: i18n.t('shareYear.shareTitle', { year: review.year }) });
      return 'shared';
    } catch {
      return 'cancelled';
    }
  }

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.name;
  link.click();
  URL.revokeObjectURL(url);
  return 'downloaded';
}
