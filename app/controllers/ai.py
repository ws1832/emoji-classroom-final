"""控制面 controller 委托业务服务；路由只负责身份/契约/响应。"""

from app.services import ai_jobs


class AIController:
    create_device = staticmethod(ai_jobs.create_device)
    update_device = staticmethod(ai_jobs.update_device)
    list_devices = staticmethod(ai_jobs.list_devices)
    create_job = staticmethod(ai_jobs.create_job)
    list_jobs = staticmethod(ai_jobs.list_jobs)
    control_job = staticmethod(ai_jobs.control_job)


ai_controller = AIController()
