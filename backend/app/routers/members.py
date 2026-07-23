"""Sharing a car: invite links, the members list, roles and leaving.

Every route here answers to app.access, so the rules are the same ones the
rest of the API enforces: a car that is not yours in any way is 404, a car
you can see but not administer is 403.

The exception is the two token routes. They take no car id — the token is
the only thing identifying the car, and until it is verified the caller has
no relationship to that car at all. So they answer 404 for every bad token
alike: unknown, expired, or already spent.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.access import (
    ASSIGNABLE_ROLES,
    ROLE_OWNER,
    ROLE_VIEWER,
    get_accessible_car,
    member_label,
)
from app.auth import get_current_user
from app.database import get_db
from app.models import Car, CarInvite, CarMember, User
from app.schemas import (
    InviteAcceptOut,
    InviteCarOut,
    InviteCreate,
    InviteCreatedOut,
    InvitePreviewOut,
    MemberOut,
    MemberUpdate,
)
from app.i18n import t
from app.services.invites import (
    INVITE_PATH_PREFIX,
    as_utc,
    create_invite,
    find_live_invite,
)

router = APIRouter(tags=["members"])

INVITE_NOT_FOUND = "Invite not found"
MEMBER_NOT_FOUND = "Member not found"


def _assignable_role_or_400(role: str, current_user: User) -> str:
    """Hold a role to what may actually be granted, or refuse it.

    400 rather than 422 even for nonsense: the client asked for a role that
    exists in the app but is not on offer ('owner'), or one that does not
    exist at all — both are «no», for the same reason, in the same words.
    """
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.roleMustBe", current_user.language),
        )
    return role


def _serialize_member(member: CarMember, car: Car, current_user: User) -> MemberOut:
    """Build the API representation of one membership row.

    The owner's role is read off the car, not off the row: ``cars.user_id``
    is what app.access enforces, so a stale or wrong role on the owner's own
    membership row must never be what the list reports.
    """
    role = ROLE_OWNER if member.user_id == car.user_id else member.role
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        label=member_label(member.user),
        role=role,
        is_you=member.user_id == current_user.id,
        created_at=member.created_at,
    )


def _get_member_or_404(db: Session, member_id: int) -> CarMember:
    member = db.get(CarMember, member_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=MEMBER_NOT_FOUND
        )
    return member


# Invites


@router.post(
    "/cars/{car_id}/invites",
    response_model=InviteCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_car_invite(
    car_id: int,
    payload: InviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteCreatedOut:
    """Mint a share link for a car (owner only). The token is shown once."""
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_OWNER)
    role = _assignable_role_or_400(payload.role, current_user)
    invite, token = create_invite(db, car, current_user, role)
    return InviteCreatedOut(
        token=token,
        invite_path=f"{INVITE_PATH_PREFIX}{token}",
        expires_at=as_utc(invite.expires_at),
    )


@router.get("/invites/{token}", response_model=InvitePreviewOut)
def preview_invite(
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvitePreviewOut:
    invite = find_live_invite(db, token)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVITE_NOT_FOUND
        )
    car = db.get(Car, invite.car_id)
    inviter = db.get(User, invite.created_by)
    if car is None or inviter is None:  # pragma: no cover - FK cascades cover this
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVITE_NOT_FOUND
        )
    return InvitePreviewOut(
        car=InviteCarOut.model_validate(car),
        role=invite.role,
        inviter_label=member_label(inviter),
    )


@router.post(
    "/invites/{token}/accept",
    response_model=InviteAcceptOut,
    status_code=status.HTTP_201_CREATED,
)
def accept_invite(
    token: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteAcceptOut:
    """Join a car with a share link.

    Whoever holds the link may use it — the invite is not addressed to an
    email, which is the design: the owner decides who to send it to. It is
    spent by the first person who joins with it, and only by them.
    """
    invite = find_live_invite(db, token)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVITE_NOT_FOUND
        )
    car = db.get(Car, invite.car_id)
    if car is None:  # pragma: no cover - deleting a car cascades its invites
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=INVITE_NOT_FOUND
        )
    if car.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.ownCarFullAccess", current_user.language),
        )

    existing = db.execute(
        select(CarMember).where(
            CarMember.car_id == car.id, CarMember.user_id == current_user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Nothing was granted, so nothing is spent: the link stays live for
        # whoever it was actually meant for. A standing role is never
        # lowered by a link — that is what PATCH /api/members/{id} is for.
        response.status_code = status.HTTP_200_OK
        return InviteAcceptOut(car_id=car.id, role=existing.role, already_member=True)

    role = invite.role  # read before the commit expires the row
    # Spend the invite atomically: the UPDATE only lands if it is still unused,
    # so two people racing the same single-use link cannot both be onboarded —
    # exactly one wins the guarded write, the loser gets the same 404.
    spent = db.execute(
        update(CarInvite)
        .where(CarInvite.id == invite.id, CarInvite.used_at.is_(None))
        .values(used_by=current_user.id, used_at=dt.datetime.now(dt.timezone.utc))
    )
    if spent.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=INVITE_NOT_FOUND)
    db.add(CarMember(car_id=car.id, user_id=current_user.id, role=role))
    db.commit()
    return InviteAcceptOut(car_id=car.id, role=role, already_member=False)


# Members


@router.get("/cars/{car_id}/members", response_model=list[MemberOut])
def list_members(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemberOut]:
    """Everyone on a car, oldest first — so the owner heads the list."""
    car = get_accessible_car(db, current_user, car_id, min_role=ROLE_VIEWER)
    members = (
        db.execute(
            select(CarMember)
            .where(CarMember.car_id == car.id)
            # One query for every label instead of one per row.
            .options(selectinload(CarMember.user))
            .order_by(CarMember.id)
        )
        .scalars()
        .all()
    )
    return [_serialize_member(member, car, current_user) for member in members]


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemberOut:
    """Change someone's role on a car (owner only)."""
    member = _get_member_or_404(db, member_id)
    car = get_accessible_car(
        db,
        current_user,
        member.car_id,
        min_role=ROLE_OWNER,
        not_found_detail=MEMBER_NOT_FOUND,
    )
    role = _assignable_role_or_400(payload.role, current_user)
    if member.user_id == car.user_id:
        # Ownership lives in cars.user_id; this row only mirrors it, and
        # editing the mirror would say something that is not true.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.ownerRoleImmutable", current_user.language),
        )
    member.role = role
    db.commit()
    db.refresh(member)
    return _serialize_member(member, car, current_user)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove someone from a car, or leave it yourself.

    The owner may remove anyone; anyone may remove themselves. Nobody may
    remove the owner — a car without an owner has no one who can share it,
    and deleting the car is the way to be rid of it.
    """
    member = _get_member_or_404(db, member_id)
    # Viewer is enough to be told the member exists — the real rule is below.
    car = get_accessible_car(
        db,
        current_user,
        member.car_id,
        min_role=ROLE_VIEWER,
        not_found_detail=MEMBER_NOT_FOUND,
    )
    if member.user_id == car.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("err.ownerCantBeRemoved", current_user.language),
        )
    is_self = member.user_id == current_user.id
    is_owner = car.user_id == current_user.id
    if not (is_self or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this car",
        )
    # The logs they wrote stay: author_id is SET NULL / kept, never cascaded.
    db.delete(member)
    db.commit()
    return None
