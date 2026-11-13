"""课程控制器和教师归属校验。"""

from fastapi import HTTPException
from tortoise.expressions import Q

from app.core.crud import CRUDBase
from app.models.admin import User
from app.models.classroom import Course
from app.schemas.classroom import CourseCreate, CourseUpdate
from app.services.ai_jobs import is_admin


class CourseController(CRUDBase[Course, CourseCreate, CourseUpdate]):
    def __init__(self):
        super().__init__(model=Course)

    async def _require_user(self, user_id: int) -> User:
        user = await User.filter(id=user_id, is_active=True).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    async def get_for_teacher(self, course_id: int, teacher_id: int) -> Course:
        course = await self.model.get_or_none(id=course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if course.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="Course does not belong to the teacher")
        return course

    async def get_for_actor(self, course_id: int, actor_id: int) -> Course:
        course = await self.model.get_or_none(id=course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        actor = await self._require_user(actor_id)
        if not await is_admin(actor) and course.teacher_id != actor_id:
            raise HTTPException(status_code=403, detail="Course does not belong to the teacher")
        return course

    async def list_for_teacher(self, teacher_id: int, page: int = 1, page_size: int = 20, keyword: str = ""):
        await self._require_user(teacher_id)
        search = Q(teacher_id=teacher_id)
        if keyword:
            search &= Q(name__icontains=keyword)
        return await self.list(page=page, page_size=page_size, search=search, order=["-created_at"])

    async def create_course(self, obj_in: CourseCreate, actor_id: int | None = None) -> Course:
        if actor_id is not None:
            actor = await self._require_user(actor_id)
            if (
                not await is_admin(actor)
                and await actor.roles.filter(name="STUDENT").exists()
                and not await actor.roles.filter(name="TEACHER").exists()
            ):
                raise HTTPException(status_code=403, detail="Students cannot create courses")
        teacher_id = obj_in.teacher_id if actor_id is None else actor_id
        await self._require_user(teacher_id)
        if actor_id is not None and obj_in.teacher_id != actor_id:
            actor = await self._require_user(actor_id)
            if not await is_admin(actor):
                raise HTTPException(status_code=403, detail="Only the course teacher can create this course")
            await self._require_user(obj_in.teacher_id)
        if await self.model.filter(name=obj_in.name, teacher_id=obj_in.teacher_id).exists():
            raise HTTPException(status_code=409, detail="Course already exists for this teacher")
        return await self.create(obj_in)

    async def update_course(self, obj_in: CourseUpdate, actor_id: int) -> Course:
        from app.services.ai_jobs import classroom_mutation

        async with classroom_mutation(course_id=obj_in.id):
            return await self._update_course(obj_in, actor_id)

    async def _update_course(self, obj_in: CourseUpdate, actor_id: int) -> Course:
        course = await self.get_for_actor(obj_in.id, actor_id)
        if obj_in.teacher_id is not None and obj_in.teacher_id != course.teacher_id:
            from app.services.ai_jobs import guard_session_mutation
            from app.models import ClassSession

            await guard_session_mutation(await ClassSession.filter(course_id=course.id).values_list("id", flat=True))
            actor = await self._require_user(actor_id)
            if not await is_admin(actor):
                raise HTTPException(status_code=403, detail="Only an administrator can transfer a course")
            await self._require_user(obj_in.teacher_id)
        values = obj_in.model_dump(exclude_unset=True, exclude={"id"})
        if (
            values.get("name")
            and await self.model.filter(name=values["name"], teacher_id=values.get("teacher_id", course.teacher_id))
            .exclude(id=course.id)
            .exists()
        ):
            raise HTTPException(status_code=409, detail="Course already exists for this teacher")
        return await self.update(obj_in.id, values)

    async def delete_course(self, course_id: int, actor_id: int) -> None:
        from app.services.ai_jobs import classroom_mutation

        async with classroom_mutation(course_id=course_id):
            await self._delete_course(course_id, actor_id)

    async def _delete_course(self, course_id: int, actor_id: int) -> None:
        actor = await self._require_user(actor_id)
        if not await is_admin(actor):
            raise HTTPException(status_code=403, detail="Only administrators can delete courses")
        await self.get_for_actor(course_id, actor_id)
        from app.services.ai_jobs import guard_session_mutation
        from app.models import ClassSession

        await guard_session_mutation(await ClassSession.filter(course_id=course_id).values_list("id", flat=True))
        await self.remove(course_id)


course_controller = CourseController()
