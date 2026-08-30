from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import TagAlreadyExistsError, TagNotFoundError
from app.models.tag import Tag


class TagService:
    """当前用户的 Tag CRUD 业务。"""

    @staticmethod
    def list_tags(session: Session, user_id: int) -> list[Tag]:
        """按名称和主键稳定排序返回当前用户的标签。"""

        return list(
            session.scalars(
                select(Tag)
                .where(Tag.user_id == user_id)
                .order_by(Tag.name.asc(), Tag.id.asc())
            ).all()
        )

    @classmethod
    def create_tag(cls, session: Session, user_id: int, name: str) -> Tag:
        existing_id = cls._find_tag_id_by_name(session, user_id, name)
        if existing_id is not None:
            raise TagAlreadyExistsError(existing_id)

        tag = Tag(user_id=user_id, name=name)
        session.add(tag)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = cls._find_tag_id_by_name(session, user_id, name)
            if existing_id is not None:
                raise TagAlreadyExistsError(existing_id) from None
            raise
        except SQLAlchemyError:
            session.rollback()
            raise

        session.refresh(tag)
        return tag

    @classmethod
    def update_tag(
        cls,
        session: Session,
        tag_id: int,
        user_id: int,
        name: str,
    ) -> Tag:
        tag = cls.get_tag(session, tag_id, user_id)
        existing_id = cls._find_tag_id_by_name(session, user_id, name)
        if existing_id is not None and existing_id != tag.id:
            raise TagAlreadyExistsError(existing_id)

        tag.name = name
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            existing_id = cls._find_tag_id_by_name(session, user_id, name)
            if existing_id is not None and existing_id != tag_id:
                raise TagAlreadyExistsError(existing_id) from None
            raise
        except SQLAlchemyError:
            session.rollback()
            raise

        session.refresh(tag)
        return tag

    @classmethod
    def delete_tag(cls, session: Session, tag_id: int, user_id: int) -> int:
        tag = cls.get_tag(session, tag_id, user_id)
        session.delete(tag)
        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        return tag_id

    @staticmethod
    def get_tag(session: Session, tag_id: int, user_id: int) -> Tag:
        tag = session.scalar(
            select(Tag).where(
                Tag.id == tag_id,
                Tag.user_id == user_id,
            )
        )
        if tag is None:
            raise TagNotFoundError()
        return tag

    @staticmethod
    def _find_tag_id_by_name(
        session: Session,
        user_id: int,
        name: str,
    ) -> int | None:
        return session.scalar(
            select(Tag.id).where(
                Tag.user_id == user_id,
                Tag.name == name,
            )
        )
