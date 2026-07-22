import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Users, UserPlus, Copy, Trash2, LogOut, Check } from 'lucide-react';
import { useCarStore } from '../store/carStore';
import { extractError } from '../api/client';
import { inviteUrl } from '../api/members';
import { canDo, roleLabel } from '../utils/permissions';
import { formatDate } from '../utils/format';
import { Button, SelectField, Card, Spinner, ErrorMessage, Modal, ConfirmDialog } from './UI';

function InviteModal({ open, onClose, onCreate }) {
  const { t } = useTranslation();
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
      setError(extractError(err, t('sharing.inviteCreateError')));
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
      setError(t('sharing.copyError'));
    }
  };

  const inviteRoles = [
    { value: 'editor', label: t('sharing.inviteRoleEditor') },
    { value: 'viewer', label: t('sharing.inviteRoleViewer') },
  ];

  return (
    <Modal open={open} onClose={onClose} title={t('sharing.inviteTitle')} size="sm">
      {error && <ErrorMessage className="mb-3">{error}</ErrorMessage>}

      {invite ? (
        <div className="space-y-3">
          <p className="text-xs text-mist">
            {t('sharing.inviteLinkInfo', { date: formatDate(invite.expires_at) })}
          </p>
          <div className="flex items-center gap-2 rounded-xl border border-edge-soft bg-garage px-3.5 py-2.5">
            <code className="min-w-0 flex-1 break-all font-mono text-xs text-fg">{link}</code>
            <button
              type="button"
              onClick={handleCopy}
              aria-label={t('sharing.copyLinkAria')}
              className="flex-shrink-0 rounded-lg p-1.5 text-mist transition-colors hover:bg-raised hover:text-fg"
            >
              {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
            </button>
          </div>
          <p className="text-xs text-mist/70">
            {t('sharing.inviteOnceInfo')}
          </p>
          <Button variant="secondary" onClick={onClose} className="w-full">
            {t('common.done')}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <SelectField
            label={t('sharing.roleLabel')}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            options={inviteRoles}
          />
          <Button onClick={handleCreate} disabled={busy} className="w-full">
            {busy ? t('sharing.creating') : t('sharing.createLink')}
          </Button>
        </div>
      )}
    </Modal>
  );
}

function MemberRow({ member, canManage, onRemove, onRoleChange }) {
  const { t } = useTranslation();
  const manageable = canManage && member.id != null && !member.is_you && member.role !== 'owner';

  const memberRoles = [
    { value: 'editor', label: roleLabel('editor') },
    { value: 'viewer', label: roleLabel('viewer') },
  ];

  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-medium text-fg">
          {member.label}
          {member.is_you && (
            <span className="flex-shrink-0 rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">
              {t('sharing.you')}
            </span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-mist">
          {t('sharing.memberMeta', {
            role: roleLabel(member.role),
            date: formatDate(member.created_at),
          })}
        </p>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1">
        {manageable ? (
          <>
            <SelectField
              label={t('sharing.roleLabel')}
              value={member.role}
              onChange={(e) => onRoleChange(member, e.target.value)}
              options={memberRoles}
              containerClassName="w-36"
            />
            <button
              type="button"
              onClick={() => onRemove(member)}
              aria-label={t('sharing.removeMemberAria', { name: member.label })}
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
  const { t } = useTranslation();
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
      onToast(t('sharing.memberRemovedToast', { name: member.label }));
    } catch (err) {
      setError(extractError(err, t('sharing.removeMemberError')));
    }
  };

  const handleRoleChange = async (member, role) => {
    setError('');
    try {
      await changeMemberRole(member.id, role);
      onToast(t('sharing.roleChangedToast', { name: member.label, role: roleLabel(role).toLowerCase() }));
    } catch (err) {
      setError(extractError(err, t('sharing.roleChangeError')));
    }
  };

  const confirmLeave = async () => {
    setLeaving(false);
    if (!you) return;
    setError('');
    try {
      await leaveCar(car.id, you.id);
      onToast(t('sharing.leftCarToast'));
    } catch (err) {
      setError(extractError(err, t('sharing.leaveError')));
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
              {t('sharing.sharedAccess')}
            </h2>
            <p className="mt-1 text-xs text-mist">
              {t('sharing.viewerAccessInfo', { role: roleLabel(car.your_role) })}
            </p>
          </div>
          {you?.id != null && (
            <Button
              variant="ghost"
              onClick={() => setLeaving(true)}
              className="flex-shrink-0 px-3 py-1.5 text-mist"
            >
              <LogOut className="h-4 w-4" />
              {t('sharing.leaveCar')}
            </Button>
          )}
        </div>

        {error && <ErrorMessage className="mt-3">{error}</ErrorMessage>}

        <ConfirmDialog
          open={leaving}
          title={t('sharing.leaveCarConfirmTitle')}
          message={t('sharing.leaveCarConfirmMessage', { car: `${car.brand} ${car.model}` })}
          confirmLabel={t('sharing.leave')}
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
            {t('sharing.sharedAccess')}
          </h2>
          <p className="mt-1 text-xs text-mist">
            {t('sharing.ownerInfo', { car: `${car.brand} ${car.model}` })}
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => setInviting(true)}
          className="flex-shrink-0 px-2.5 py-1.5 text-amber"
        >
          <UserPlus className="h-4 w-4" />
          {t('sharing.invite')}
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
          {t('sharing.emptyState')}
        </p>
      )}

      <InviteModal open={inviting} onClose={() => setInviting(false)} onCreate={handleInvite} />

      <ConfirmDialog
        open={removingMember !== null}
        title={t('sharing.removeMemberConfirmTitle')}
        message={
          removingMember
            ? t('sharing.removeMemberConfirmMessage', { name: removingMember.label })
            : ''
        }
        confirmLabel={t('common.remove')}
        onConfirm={confirmRemove}
        onCancel={() => setRemovingMember(null)}
      />
    </Card>
  );
}
