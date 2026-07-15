import { useEffect, useState } from 'react';
import { Users, UserPlus, Copy, Trash2, LogOut, Check } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { inviteUrl } from '../api/members';
import { canDo, roleLabel } from '../utils/permissions';
import { formatDate } from '../utils/format';
import { Button, SelectField, Card, Spinner, ErrorMessage, Modal, ConfirmDialog } from './UI';

const INVITE_ROLES = [
  { value: 'editor', label: 'Редактор — може вести журнал' },
  { value: 'viewer', label: 'Спостерігач — лише перегляд' },
];

const MEMBER_ROLES = [
  { value: 'editor', label: 'Редактор' },
  { value: 'viewer', label: 'Спостерігач' },
];

function InviteModal({ open, onClose, onCreate }) {
  const [role, setRole] = useState('editor');
  const [invite, setInvite] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      setRole('editor');
      setInvite(null);
      setError('');
      setCopied(false);
    }
  }, [open]);

  const handleCreate = async () => {
    setError('');
    setBusy(true);
    try {
      setInvite(await onCreate(role));
    } catch (err) {
      setError(extractError(err, 'Не вдалося створити запрошення'));
    } finally {
      setBusy(false);
    }
  };

  const link = invite ? inviteUrl(invite.invite_path) : '';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setError('Не вдалося скопіювати. Скопіюйте посилання вручну.');
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Запросити до авто" size="sm">
      {error && <ErrorMessage className="mb-3">{error}</ErrorMessage>}

      {invite ? (
        <div className="space-y-3">
          <p className="text-xs text-mist">
            Надішліть це посилання. Воно одноразове й діє до {formatDate(invite.expires_at)}.
          </p>
          <div className="flex items-center gap-2 rounded-xl border border-edge-soft bg-garage px-3.5 py-2.5">
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-fg">{link}</code>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="Скопіювати посилання"
              className="flex-shrink-0 rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-xs text-mist/70">
            Посилання показується один раз — після закриття вікна відновити його не можна, лише
            створити нове.
          </p>
          <Button variant="secondary" onClick={onClose} className="w-full">
            Готово
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <SelectField
            label="Роль"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            options={INVITE_ROLES}
          />
          <Button onClick={handleCreate} disabled={busy} className="w-full">
            {busy ? 'Створення…' : 'Створити посилання'}
          </Button>
        </div>
      )}
    </Modal>
  );
}

function MemberRow({ member, canManage, onRemove, onRoleChange }) {
  const manageable = canManage && member.id != null && !member.is_you && member.role !== 'owner';

  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-medium text-fg">
          {member.label}
          {member.is_you && (
            <span className="flex-shrink-0 rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">
              ви
            </span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-mist">
          {roleLabel(member.role)} · з {formatDate(member.created_at)}
        </p>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1">
        {manageable ? (
          <>
            <SelectField
              label="Роль"
              value={member.role}
              onChange={(e) => onRoleChange(member, e.target.value)}
              options={MEMBER_ROLES}
              containerClassName="w-36"
            />
            <button
              type="button"
              onClick={() => onRemove(member)}
              aria-label={`Прибрати ${member.label}`}
              className="rounded-lg p-1.5 text-mist/70 transition-colors hover:bg-crit/10 hover:text-crit"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </>
        ) : (
          <span className="text-xs text-mist/70">{roleLabel(member.role)}</span>
        )}
      </div>
    </div>
  );
}

export default function SharingCard({ car, onToast }) {
  const members = useCarStore((s) => s.members);
  const membersCarId = useCarStore((s) => s.membersCarId);
  const membersLoading = useCarStore((s) => s.membersLoading);
  const membersError = useCarStore((s) => s.membersError);
  const fetchMembers = useCarStore((s) => s.fetchMembers);
  const inviteMember = useCarStore((s) => s.inviteMember);
  const removeMember = useCarStore((s) => s.removeMember);
  const changeMemberRole = useCarStore((s) => s.changeMemberRole);
  const leaveCar = useCarStore((s) => s.leaveCar);

  const [inviting, setInviting] = useState(false);
  const [removingMember, setRemovingMember] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState('');

  const isOwner = canDo(car?.your_role, 'members:manage');
  const fresh = String(membersCarId) === String(car?.id);
  const you = fresh ? members.find((m) => m.is_you) : null;

  useEffect(() => {
    if (car?.id) fetchMembers(car.id).catch(() => {});
  }, [car?.id, fetchMembers]);

  const handleInvite = (role) => inviteMember(role);

  const confirmRemove = async () => {
    const member = removingMember;
    setRemovingMember(null);
    if (!member) return;
    setError('');
    try {
      await removeMember(member.id);
      onToast(`${member.label} більше не має доступу`);
    } catch (err) {
      setError(extractError(err, 'Не вдалося прибрати учасника'));
    }
  };

  const handleRoleChange = async (member, role) => {
    setError('');
    try {
      await changeMemberRole(member.id, role);
      onToast(`${member.label} тепер ${roleLabel(role).toLowerCase()}`);
    } catch (err) {
      setError(extractError(err, 'Не вдалося змінити роль'));
    }
  };

  const confirmLeave = async () => {
    setLeaving(false);
    if (!you) return;
    setError('');
    try {
      await leaveCar(car.id, you.id);
      onToast('Ви вийшли з авто');
    } catch (err) {
      setError(extractError(err, 'Не вдалося вийти з авто'));
    }
  };

  if (!car) return null;

  if (!isOwner) {
    return (
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
              <Users className="h-4 w-4 text-signal" />
              Спільний доступ
            </h2>
            <p className="mt-1 text-xs text-mist">
              Ви маєте доступ як {roleLabel(car.your_role)}. Авто веде інший власник.
            </p>
          </div>
          {you?.id != null && (
            <Button
              variant="ghost"
              onClick={() => setLeaving(true)}
              className="flex-shrink-0 px-3 py-1.5 text-mist"
            >
              <LogOut className="h-4 w-4" />
              Вийти з авто
            </Button>
          )}
        </div>

        {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

        <ConfirmDialog
          open={leaving}
          title="Вийти з авто?"
          message={`Вийти з ${car.brand} ${car.model}? Авто зникне з вашого гаража. Повернутись можна лише за новим запрошенням.`}
          confirmLabel="Вийти"
          onConfirm={confirmLeave}
          onCancel={() => setLeaving(false)}
        />
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">
            <Users className="h-4 w-4 text-signal" />
            Спільний доступ
          </h2>
          <p className="mt-1 text-xs text-mist">
            Хто ще бачить {car.brand} {car.model}. Редактор веде журнал, спостерігач лише читає.
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => setInviting(true)}
          className="flex-shrink-0 px-2.5 py-1.5 text-amber"
        >
          <UserPlus className="h-4 w-4" />
          Запросити
        </Button>
      </div>

      {membersError && <ErrorMessage className="mb-2">{membersError}</ErrorMessage>}
      {error && <ErrorMessage className="mb-2">{error}</ErrorMessage>}

      {membersLoading && members.length === 0 ? (
        <Spinner className="py-4" />
      ) : fresh && members.length > 0 ? (
        <div className="divide-y divide-edge">
          {members.map((member) => (
            <MemberRow
              key={member.user_id}
              member={member}
              canManage
              onRemove={setRemovingMember}
              onRoleChange={handleRoleChange}
            />
          ))}
        </div>
      ) : (
        <p className="py-2 text-sm text-mist">
          Доступ лише у вас. Запросіть посиланням того, хто теж їздить цим авто.
        </p>
      )}

      <InviteModal open={inviting} onClose={() => setInviting(false)} onCreate={handleInvite} />

      <ConfirmDialog
        open={removingMember !== null}
        title="Прибрати учасника?"
        message={
          removingMember
            ? `Прибрати ${removingMember.label}? Доступ до авто зникне одразу, а записи в журналі лишаться.`
            : ''
        }
        confirmLabel="Прибрати"
        onConfirm={confirmRemove}
        onCancel={() => setRemovingMember(null)}
      />
    </Card>
  );
}
