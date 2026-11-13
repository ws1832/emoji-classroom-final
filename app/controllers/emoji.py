"""Emoji 记录写入、历史查询和统计控制器。"""

from datetime import datetime

from fastapi import HTTPException
from tortoise.functions import Count

from app.core.crud import CRUDBase
from app.models.admin import User
from app.models.classroom import ClassSession, EmojiRecord, ScheduleUser
from app.models.enums import EmojiSource, EmojiType
from app.schemas.emoji import EmojiCreate


class EmojiController(CRUDBase[EmojiRecord, EmojiCreate, EmojiCreate]):
    def __init__(self):
        super().__init__(model=EmojiRecord)

    async def _require_user(self, user_id: int) -> User:
        user = await User.filter(id=user_id, is_active=True).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    async def _require_session(self, session_id: int) -> ClassSession:
        session = await ClassSession.get_or_none(id=session_id).prefetch_related("course")
        if session is None:
            raise HTTPException(status_code=404, detail="Class session not found")
        return session

    async def create_record(self, obj_in: EmojiCreate, actor_id: int | None = None) -> EmojiRecord:
        """写入记录并校验来源约束与用户归属。

        用户登录身份不能写入 AI 来源，包括教师和管理员。设备服务身份由独立
        AI 入库服务处理；本控制器仍保留可信内部调用的来源字段校验。
        """

        if actor_id is not None and obj_in.source is EmojiSource.AI:
            raise HTTPException(status_code=403, detail="AI records require an independent device credential")

        values = obj_in.model_dump(exclude_unset=True)
        user_id = values.get("user_id", actor_id)
        session_id = values.get("session_id")
        if user_id is not None:
            values["user_id"] = user_id
        session = await self._require_session(session_id)
        if actor_id is not None:
            actor = await self._require_user(actor_id)
            if actor_id != user_id and not actor.is_superuser and actor_id != session.course.teacher_id:
                raise HTTPException(status_code=403, detail="Cannot write a record for another user")
            if actor_id == user_id and not actor.is_superuser and actor_id != session.course.teacher_id:
                is_scheduled = await ScheduleUser.filter(session_id=session_id, user_id=actor_id).exists()
                if not is_scheduled:
                    raise HTTPException(status_code=403, detail="User is not scheduled for this classroom")
        if user_id is not None:
            await self._require_user(user_id)
        if obj_in.source is EmojiSource.MANUAL and user_id is None:
            raise HTTPException(status_code=422, detail="Manual records must be associated with a user")
        if obj_in.source is EmojiSource.MANUAL and obj_in.confidence is not None:
            raise HTTPException(status_code=422, detail="Manual records must not contain confidence")
        if obj_in.source is EmojiSource.AI and obj_in.confidence is None:
            raise HTTPException(status_code=422, detail="AI records require confidence")
        return await self.model.create(**values)

    async def get_user_history(
        self,
        user_id: int,
        actor_id: int | None = None,
        session_id: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        await self._require_user(user_id)
        if actor_id is not None and actor_id != user_id:
            actor = await self._require_user(actor_id)
            if not actor.is_superuser:
                if session_id is None:
                    raise HTTPException(status_code=403, detail="Cannot view another user's history")
                session = await self._require_session(session_id)
                if session.course.teacher_id != actor_id:
                    raise HTTPException(status_code=403, detail="Cannot view this classroom history")
        if actor_id == user_id and session_id is not None:
            actor = await self._require_user(actor_id)
            session = await self._require_session(session_id)
            if actor_id != session.course.teacher_id and not actor.is_superuser:
                is_scheduled = await ScheduleUser.filter(session_id=session_id, user_id=user_id).exists()
                if not is_scheduled:
                    raise HTTPException(status_code=403, detail="User is not scheduled for this classroom")
        filters = {"user_id": user_id}
        if session_id is not None:
            filters["session_id"] = session_id
        if from_time is not None:
            filters["timestamp__gte"] = from_time
        if to_time is not None:
            filters["timestamp__lte"] = to_time
        query = self.model.filter(**filters).order_by("-timestamp", "-id")
        total = await query.count()
        records = await query.offset((page - 1) * page_size).limit(page_size)
        return total, records

    async def get_teacher_history(
        self,
        session_id: int,
        teacher_id: int,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        session = await self._require_session(session_id)
        if session.course.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="Class session does not belong to the teacher")
        filters = {"session_id": session_id}
        if from_time is not None:
            filters["timestamp__gte"] = from_time
        if to_time is not None:
            filters["timestamp__lte"] = to_time
        query = self.model.filter(**filters).order_by("-timestamp")
        total = await query.count()
        records = await query.offset((page - 1) * page_size).limit(page_size)
        return total, records

    async def statistics(
        self,
        session_id: int | None = None,
        user_id: int | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        source: EmojiSource | None = None,
    ) -> list[dict]:
        filters = {}
        if source is not None:
            filters["source"] = source
        if session_id is not None:
            filters["session_id"] = session_id
        if user_id is not None:
            filters["user_id"] = user_id
        if from_time is not None:
            filters["timestamp__gte"] = from_time
        if to_time is not None:
            filters["timestamp__lte"] = to_time
        rows = (
            await self.model.filter(**filters)
            .annotate(count=Count("id"))
            .group_by("emoji_type")
            .values("emoji_type", "count")
        )
        total = sum(row["count"] for row in rows)
        return [
            {
                "emoji_type": row["emoji_type"],
                "count": row["count"],
                "percentage": round(row["count"] * 100 / total, 2) if total else 0.0,
            }
            for row in rows
        ]

    # 兼容路由层常用的简短命名。
    create_emoji = create_record
    history = get_user_history

    async def list_records(
        self,
        actor_id: int,
        is_superuser: bool,
        session_id: int | None = None,
        user_id: int | None = None,
        user_no: str | None = None,
        emoji_type: EmojiType | None = None,
        source: EmojiSource | None = None,
        course_id: int | None = None,
        class_name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        """管理端分页查询 Emoji 记录：管理员看全部，教师看自己的课堂。"""

        query = self.model.all().select_related("session__course", "user")
        if not is_superuser:
            query = query.filter(session__course__teacher_id=actor_id)
        if session_id is not None:
            query = query.filter(session_id=session_id)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if user_no:
            query = query.filter(user__user_no=user_no)
        if emoji_type is not None:
            query = query.filter(emoji_type=emoji_type)
        if source is not None:
            query = query.filter(source=source)
        if course_id is not None:
            query = query.filter(session__course_id=course_id)
        if class_name:
            query = query.filter(session__class_name=class_name)
        if from_time is not None:
            query = query.filter(timestamp__gte=from_time)
        if to_time is not None:
            query = query.filter(timestamp__lte=to_time)
        total = await query.count()
        records = await query.order_by("-timestamp", "-id").offset((page - 1) * page_size).limit(page_size)
        return total, records

    def export_query(
        self,
        actor_id: int,
        is_superuser: bool,
        session_id: int | None = None,
        user_id: int | None = None,
        user_no: str | None = None,
        emoji_type: EmojiType | None = None,
        source: EmojiSource | None = None,
        course_id: int | None = None,
        class_name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ):
        """保留原过滤条件，返回惰性查询供有界 keyset 导出。"""

        query = self.model.all().select_related("session__course", "user")
        if not is_superuser:
            query = query.filter(session__course__teacher_id=actor_id)
        if session_id is not None:
            query = query.filter(session_id=session_id)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if user_no:
            query = query.filter(user__user_no=user_no)
        if emoji_type is not None:
            query = query.filter(emoji_type=emoji_type)
        if source is not None:
            query = query.filter(source=source)
        if course_id is not None:
            query = query.filter(session__course_id=course_id)
        if class_name:
            query = query.filter(session__class_name=class_name)
        if from_time is not None:
            query = query.filter(timestamp__gte=from_time)
        if to_time is not None:
            query = query.filter(timestamp__lte=to_time)
        return query

    async def export_records(self, *args, **kwargs):
        """兼容内部旧调用；HTTP 导出使用 stream_export_records。"""
        return await self.export_query(*args, **kwargs).order_by("-timestamp", "-id")

    async def stream_export_records(self, query, *, ceiling, batch_size=500):
        """固定开始时最大 ID；以(timestamp,id)游标保持旧倒序和同时间稳定性。"""
        from tortoise.expressions import Q

        cursor = None
        query = query.filter(id__lte=ceiling)
        while True:
            page = query
            if cursor:
                timestamp, identifier = cursor
                page = page.filter(Q(timestamp__lt=timestamp) | Q(timestamp=timestamp, id__lt=identifier))
            rows = await page.order_by("-timestamp", "-id").limit(batch_size)
            if not rows:
                break
            for record in rows:
                yield record
            cursor = (rows[-1].timestamp, rows[-1].id)


emoji_controller = EmojiController()
