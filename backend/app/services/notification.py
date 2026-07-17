import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notification_bus import publish
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
    await db.flush()  # applique les défauts (id, created_at) avant sérialisation

    # Publication via le bus PostgreSQL (LISTEN/NOTIFY) dans la MÊME transaction :
    # le push temps réel fonctionne depuis n'importe quel processus (API ou worker),
    # et n'est délivré qu'au commit — jamais pour une transaction annulée.
    await publish(
        db,
        recipient_id,
        {
            "kind": "notification",
            "data": NotificationResponse.model_validate(notification).model_dump(mode="json"),
        },
    )
    await db.commit()
    await db.refresh(notification)
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


async def notify_emails_prets(
    db: AsyncSession, commercial_id: uuid.UUID, nb_emails: int
) -> None:
    """Notifie le commercial que ses emails sont prêts à valider."""
    await create_notification(
        db,
        recipient_id=commercial_id,
        type=NotificationType.EMAILS_PRETS,
        title="Emails prêts à valider",
        message=f"{nb_emails} email{'s' if nb_emails > 1 else ''} généré{'s' if nb_emails > 1 else ''} — en attente de votre validation.",
    )


async def notify_retour_crm(
    db: AsyncSession, commercial_id: uuid.UUID, company_name: str, event: str
) -> None:
    """Notifie le commercial d'un retour CRM Odoo (webhook) sur un de ses leads."""
    if event == "lead.lost":
        await create_notification(
            db,
            recipient_id=commercial_id,
            type=NotificationType.LEAD_SANS_REPONSE,
            title="Prospect perdu dans Odoo",
            message=f"{company_name} : opportunité marquée perdue — statut passé à SANS_REPONSE.",
        )
    elif event == "lead.won":
        await create_notification(
            db,
            recipient_id=commercial_id,
            type=NotificationType.LEAD_REPONDU,
            title="Prospect converti dans Odoo",
            message=f"{company_name} : opportunité gagnée — statut passé à REPONDU.",
        )
    else:  # message.received
        await create_notification(
            db,
            recipient_id=commercial_id,
            type=NotificationType.LEAD_REPONDU,
            title="Réponse reçue",
            message=f"{company_name} a répondu à votre email — statut passé à REPONDU.",
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
