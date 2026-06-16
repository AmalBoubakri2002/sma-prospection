import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import manager
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.schemas.notification import NotificationResponse


async def create_notification(
    db: AsyncSession,
    recipient_id: uuid.UUID,
    type: str,
    title: str,
    message: str,
    related_user_id: uuid.UUID | None = None,
) -> Notification:
    notification = Notification(
        recipient_id=recipient_id,
        type=type,
        title=title,
        message=message,
        related_user_id=related_user_id,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    await manager.send_to_user(
        recipient_id,
        NotificationResponse.model_validate(notification).model_dump(mode="json"),
    )
    return notification


async def notify_admins_new_registration(db: AsyncSession, commercial: User) -> None:
    result = await db.execute(select(User).where(User.role == "admin"))
    admins = result.scalars().all()
    for admin in admins:
        await create_notification(
            db,
            recipient_id=admin.id,
            type=NotificationType.REGISTRATION_REQUEST,
            title="Nouvelle demande d'inscription",
            message=f"{commercial.full_name or commercial.email} souhaite créer un compte commercial.",
            related_user_id=commercial.id,
        )


async def notify_account_approved(db: AsyncSession, commercial: User) -> None:
    await create_notification(
        db,
        recipient_id=commercial.id,
        type=NotificationType.ACCOUNT_APPROVED,
        title="Compte approuvé",
        message="Votre compte a été validé par un administrateur. Vous pouvez maintenant vous connecter.",
    )


async def notify_account_rejected(db: AsyncSession, commercial: User) -> None:
    await create_notification(
        db,
        recipient_id=commercial.id,
        type=NotificationType.ACCOUNT_REJECTED,
        title="Demande refusée",
        message="Votre demande d'inscription a été refusée par un administrateur.",
    )


async def list_notifications(db: AsyncSession, recipient_id: uuid.UUID) -> list[Notification]:
    result = await db.execute(
        select(Notification)
        .where(Notification.recipient_id == recipient_id)
        .order_by(Notification.created_at.desc())
    )
    return list(result.scalars().all())


async def get_notification_by_id(db: AsyncSession, notification_id: uuid.UUID) -> Notification | None:
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    return result.scalar_one_or_none()


async def mark_notification_read(db: AsyncSession, notification: Notification) -> Notification:
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification
