import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function Spinner({ className = '' }) {
  const { t } = useTranslation();
  return (
    <div className={`flex justify-center py-10 ${className}`}>
      <Loader2 className="h-7 w-7 animate-spin text-amber" aria-label={t('common.loading')} />
    </div>
  );
}
