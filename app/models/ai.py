"""匿名 AI 控制、租约和回执；不修改 EmojiRecord 的公开字段。"""

from tortoise import fields

from .base import BaseModel, TimestampMixin


class AIDevice(BaseModel, TimestampMixin):
    name = fields.CharField(max_length=80)
    source_alias = fields.CharField(max_length=64)
    enabled = fields.BooleanField(default=True)
    last_seen = fields.DatetimeField(null=True)
    incarnation = fields.UUIDField(null=True)
    health = fields.CharField(max_length=32, default="offline")
    capabilities = fields.JSONField(default=list)

    class Meta:
        table = "ai_device"


class AIDeviceGrant(BaseModel):
    device = fields.ForeignKeyField("models.AIDevice", related_name="grants", on_delete=fields.CASCADE)
    teacher = fields.ForeignKeyField("models.User", related_name="ai_grants", on_delete=fields.CASCADE)

    class Meta:
        table = "ai_device_grant"
        unique_together = (("device", "teacher"),)


class AICredential(BaseModel):
    key_id = fields.CharField(max_length=32, unique=True)
    secret_hash = fields.CharField(max_length=64)
    device = fields.ForeignKeyField("models.AIDevice", related_name="credentials", on_delete=fields.CASCADE)
    expires_at = fields.DatetimeField()
    revoked = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_credential"


class AIJob(BaseModel, TimestampMixin):
    session = fields.ForeignKeyField("models.ClassSession", related_name="ai_jobs", on_delete=fields.CASCADE)
    device = fields.ForeignKeyField("models.AIDevice", related_name="jobs", on_delete=fields.CASCADE)
    creator = fields.ForeignKeyField("models.User", related_name="ai_jobs", on_delete=fields.SET_NULL, null=True)
    request_id = fields.UUIDField(unique=True)
    profile = fields.CharField(max_length=16)
    input_kind = fields.CharField(max_length=16, default="legacy")
    model_version = fields.CharField(max_length=64)
    mapping_version = fields.CharField(max_length=32, default="five-emotions-v1")
    threshold = fields.FloatField()
    detection_threshold = fields.FloatField()
    sample_interval = fields.FloatField()
    max_faces = fields.IntField(default=10)
    config_revision = fields.IntField(default=1)
    generation = fields.IntField(default=1)
    desired = fields.CharField(max_length=16, default="ready")
    observed = fields.CharField(max_length=16, default="prechecking")
    health = fields.CharField(max_length=32, default="waiting")
    metrics = fields.JSONField(default=dict)
    # 一个设备代表一个 source；非终止任务占位。NULL 允许多个历史任务。
    active_slot = fields.CharField(max_length=32, null=True, unique=True)
    last_ack = fields.DatetimeField(null=True)
    started_at = fields.DatetimeField(null=True)
    stopped_at = fields.DatetimeField(null=True)

    class Meta:
        table = "ai_job"
        indexes = (("session_id", "created_at"),)


class AILease(BaseModel):
    lease_id = fields.UUIDField(unique=True)
    job = fields.ForeignKeyField("models.AIJob", related_name="leases", on_delete=fields.CASCADE)
    credential = fields.ForeignKeyField("models.AICredential", related_name="leases", on_delete=fields.CASCADE)
    incarnation = fields.UUIDField()
    generation = fields.IntField()
    acquired_at = fields.DatetimeField()
    expires_at = fields.DatetimeField()
    capture_end = fields.DatetimeField(null=True)
    revoked = fields.BooleanField(default=False)

    class Meta:
        table = "ai_lease"
        unique_together = (("job", "generation"),)


class AIReceipt(BaseModel):
    event_id = fields.UUIDField(unique=True)
    job = fields.ForeignKeyField("models.AIJob", related_name="receipts", on_delete=fields.CASCADE)
    payload_hash = fields.CharField(max_length=64)
    decision = fields.CharField(max_length=16)
    reason = fields.CharField(max_length=48)
    record = fields.ForeignKeyField(
        "models.EmojiRecord", related_name="ai_receipts", null=True, on_delete=fields.SET_NULL
    )
    received_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ai_receipt"
        indexes = (("job_id", "received_at"),)


class AIRecordMetadata(BaseModel):
    record = fields.OneToOneField("models.EmojiRecord", related_name="ai_metadata", on_delete=fields.CASCADE)
    job = fields.ForeignKeyField("models.AIJob", related_name="record_metadata", on_delete=fields.CASCADE)
    lease = fields.ForeignKeyField("models.AILease", related_name="record_metadata", on_delete=fields.CASCADE)
    model_version = fields.CharField(max_length=64)
    mapping_version = fields.CharField(max_length=32)
    config_revision = fields.IntField()
    quality = fields.JSONField(default=dict)

    class Meta:
        table = "ai_record_metadata"


class BrowserBudget(BaseModel):
    """课堂结束后清理的不可公开配额键；不关联结果或用户外键。"""

    key = fields.CharField(max_length=64, unique=True)
    expires_at = fields.DatetimeField()
    sample_interval = fields.IntField(default=10)
    last_slot = fields.BigIntField(default=-1)
    last_claim_at = fields.DatetimeField(null=True)
    phase_ms = fields.IntField()

    class Meta:
        table = "ai_browser_budget"


class BrowserCapture(BaseModel):
    """短期授权/防重复控制信息；不在结果接口中暴露，不是学生结果归属。"""

    capture_id = fields.UUIDField(unique=True)
    job = fields.ForeignKeyField("models.AIJob", related_name="browser_captures", on_delete=fields.CASCADE)
    owner = fields.ForeignKeyField("models.User", null=True, on_delete=fields.SET_NULL)
    active_key = fields.CharField(max_length=64, null=True, unique=True)
    token_hash = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
    stopped_at = fields.DatetimeField(null=True)
    last_slot = fields.BigIntField(default=-1)
    phase_ms = fields.IntField(default=0)

    class Meta:
        table = "ai_browser_capture"


class BrowserFrame(BaseModel):
    """仅短期元数据票据，不保存图片；防同一时间槽/请求重复推理和入库。"""

    event_id = fields.UUIDField(unique=True)
    capture = fields.ForeignKeyField("models.BrowserCapture", null=True, on_delete=fields.SET_NULL)
    job = fields.ForeignKeyField("models.AIJob", on_delete=fields.CASCADE)
    lease = fields.ForeignKeyField("models.AILease", on_delete=fields.CASCADE)
    generation = fields.IntField()
    slot = fields.BigIntField()
    payload_hash = fields.CharField(max_length=64)
    captured_at = fields.DatetimeField()
    state = fields.CharField(max_length=16, default="claimed")
    reason = fields.CharField(max_length=32, default="waiting")
    counted = fields.BooleanField(default=False)
    inference_ms = fields.FloatField(default=0)

    class Meta:
        table = "ai_browser_frame"
        unique_together = (("capture", "slot"),)
