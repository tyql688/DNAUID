import asyncio
import functools
from typing import Any, Literal, TypeVar, ClassVar

from sqlmodel import Field, col, select
from sqlalchemy import null, delete, update
from sqlalchemy.sql import or_, and_
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.startup import exec_list
from gsuid_core.utils.database.base_models import (
    Bind,
    User,
    BaseIDModel,
    with_session,
)

from ..utils import get_today_date

exec_list.extend(
    [
        "ALTER TABLE DNAUser ADD COLUMN d_num TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN refresh_token TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN web_token TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN web_dev_code TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN web_d_num TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN web_refresh_token TEXT DEFAULT ''",
        "ALTER TABLE DNAUser ADD COLUMN web_status TEXT DEFAULT ''",
        "ALTER TABLE dnaprivacy ADD COLUMN uid_hidden BOOLEAN DEFAULT 0",
        "ALTER TABLE dna_group_privacy ADD COLUMN force_uid_hidden BOOLEAN DEFAULT NULL",
    ]
)

T_DNABind = TypeVar("T_DNABind", bound="DNABind")
T_DNAUser = TypeVar("T_DNAUser", bound="DNAUser")
T_DNASign = TypeVar("T_DNASign", bound="DNASign")
T_DNAPrivacy = TypeVar("T_DNAPrivacy", bound="DNAPrivacy")
T_DNAGroupPrivacy = TypeVar("T_DNAGroupPrivacy", bound="DNAGroupPrivacy")


_DB_WRITE_LOCK = asyncio.Lock()


def with_lock(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        async with _DB_WRITE_LOCK:
            return await func(*args, **kwargs)

    return wrapper


class DNABind(Bind, table=True):
    __table_args__: dict[str, Any] = {"extend_existing": True}
    uid: str = Field(default=None, title="二重螺旋uid")

    @classmethod
    @with_session
    async def get_group_all_uid(cls: type[T_DNABind], session: AsyncSession, group_id: str) -> list[T_DNABind]:
        result = await session.scalars(select(cls).where(col(cls.group_id).contains(group_id)))
        return list(result.all()) if result else []

    @classmethod
    async def insert_uid(
        cls: type[T_DNABind],
        user_id: str,
        bot_id: str,
        uid: str,
        group_id: str | None = None,
        lenth_limit: int | None = None,
        is_digit: bool | None = True,
    ) -> int:
        """
        0: 成功
        -1: 长度不符
        -2: 已存在
        -3: 不是数字
        """
        if not uid:
            return -1

        if lenth_limit and len(uid) != lenth_limit:
            return -1

        if is_digit and not uid.isdigit():
            return -3

        # 第一次绑定
        if not await cls.bind_exists(user_id, bot_id):
            code = await cls.insert_data(user_id=user_id, bot_id=bot_id, **{"uid": uid, "group_id": group_id})
            return code

        # 获取历史
        result: T_DNABind | None = await cls.select_data(user_id, bot_id)
        if not result:
            return -1

        current_uids = list(dict.fromkeys(filter(None, result.uid.split("_"))))
        if uid in current_uids:
            return -2

        current_uids.append(uid)
        return await cls.update_data(user_id, bot_id, **{"uid": "_".join(current_uids)})

    @classmethod
    @with_session
    async def delete_uid(
        cls: type[T_DNABind],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> int:
        result = await cls.get_uid_list_by_game(user_id, bot_id)
        if result is None or uid not in result:
            return -1

        result.remove(uid)
        result = [i for i in result if i] if result else []

        if not result:
            # 没有剩余uid，使用 SQL DELETE 删除记录
            sql = delete(cls).where(and_(col(cls.user_id) == user_id, col(cls.bot_id) == bot_id))
            await session.execute(sql)
            return 0
        else:
            # 还有剩余uid，更新记录
            return await cls.update_data(user_id, bot_id, **{"uid": "_".join(result)})

    @classmethod
    @with_session
    async def delete_all_uid(cls: type[T_DNABind], session: AsyncSession, user_id: str, bot_id: str) -> int:
        sql = delete(cls).where(and_(col(cls.user_id) == user_id, col(cls.bot_id) == bot_id))
        await session.execute(sql)
        return 0


class DNAUser(User, table=True):
    __table_args__: dict[str, Any] = {"extend_existing": True}
    cookie: str = Field(default="", title="Cookie")
    uid: str = Field(default=None, title="二重螺旋uid")
    dev_code: str = Field(default=None, title="设备ID")
    d_num: str = Field(default="", title="d_num")
    refresh_token: str = Field(default="", title="refresh_token")
    web_token: str = Field(default="", title="Web token")
    web_dev_code: str = Field(default="", title="Web 设备ID")
    web_d_num: str = Field(default="", title="Web d_num")
    web_refresh_token: str = Field(default="", title="Web refresh_token")
    web_status: str = Field(default="", title="Web token 状态")

    @classmethod
    @with_session
    async def mark_cookie_invalid(cls: type[T_DNAUser], session: AsyncSession, uid: str, cookie: str, mark: str):
        sql = update(cls).where(col(cls.uid) == uid).where(col(cls.cookie) == cookie).values(status=mark)
        await session.execute(sql)
        return True

    @classmethod
    @with_session
    async def select_cookie(
        cls: type[T_DNAUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> str | None:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0].cookie if data else None

    @classmethod
    @with_session
    async def select_dna_user(
        cls: type[T_DNAUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> T_DNAUser | None:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def select_dna_users(
        cls: type[T_DNAUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> list[T_DNAUser]:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return list(data) if data else []

    @classmethod
    @with_session
    async def select_web_user(
        cls: type[T_DNAUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> T_DNAUser | None:
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.uid == uid,
            cls.bot_id == bot_id,
            col(cls.web_token) != null(),
            col(cls.web_token) != "",
            or_(col(cls.web_status) == null(), col(cls.web_status) == ""),
        )
        result = await session.execute(sql)
        return result.scalars().first()

    @classmethod
    @with_session
    async def select_user_cookie_uids(
        cls: type[T_DNAUser],
        session: AsyncSession,
        user_id: str,
    ) -> list[str]:
        sql = select(cls).where(
            and_(
                col(cls.user_id) == user_id,
                col(cls.cookie) != null(),
                col(cls.cookie) != "",
                or_(col(cls.status) == null(), col(cls.status) == ""),
            )
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return [i.uid for i in data] if data else []

    @classmethod
    @with_session
    async def select_data_by_cookie(cls: type[T_DNAUser], session: AsyncSession, cookie: str) -> T_DNAUser | None:
        sql = select(cls).where(cls.cookie == cookie)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def select_data_by_cookie_and_uid(
        cls: type[T_DNAUser], session: AsyncSession, cookie: str, uid: str
    ) -> T_DNAUser | None:
        sql = select(cls).where(cls.cookie == cookie, cls.uid == uid)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    async def get_user_by_attr(
        cls: type[T_DNAUser],
        user_id: str,
        bot_id: str,
        attr_key: str,
        attr_value: str,
    ) -> Any | None:
        user_list = await cls.select_data_list(user_id=user_id, bot_id=bot_id)
        if not user_list:
            return None
        for user in user_list:
            if getattr(user, attr_key) != attr_value:
                continue
            return user

    @classmethod
    @with_session
    async def get_dna_all_user(cls: type[T_DNAUser], session: AsyncSession) -> list[T_DNAUser]:
        """获取所有有效用户"""
        sql = select(cls).where(
            and_(
                or_(col(cls.status) == null(), col(cls.status) == ""),
                col(cls.cookie) != null(),
                col(cls.cookie) != "",
            )
        )

        result = await session.execute(sql)
        data = result.scalars().all()
        return list(data)

    @classmethod
    @with_session
    async def get_all_card_users(
        cls: type[T_DNAUser],
        session: AsyncSession,
    ) -> list[T_DNAUser]:
        app_available = and_(
            col(cls.cookie) != null(),
            col(cls.cookie) != "",
            or_(col(cls.status) == null(), col(cls.status) == ""),
        )
        web_available = and_(
            col(cls.web_token) != null(),
            col(cls.web_token) != "",
            or_(col(cls.web_status) == null(), col(cls.web_status) == ""),
        )
        result = await session.execute(select(cls).where(or_(app_available, web_available)))
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_all_invalid_cookie(cls, session: AsyncSession) -> int:
        """删除所有无效缓存"""
        app_unavailable = or_(
            col(cls.status) == "无效",
            col(cls.cookie) == null(),
            col(cls.cookie) == "",
        )
        web_unavailable = or_(
            col(cls.web_status) == "无效",
            col(cls.web_token) == null(),
            col(cls.web_token) == "",
        )
        sql = delete(cls).where(
            and_(app_unavailable, web_unavailable),
        )
        result = await session.execute(sql)
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def delete_cookie(
        cls,
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        uid: str,
    ) -> int:
        sql = delete(cls).where(
            and_(
                col(cls.user_id) == user_id,
                col(cls.uid) == uid,
                col(cls.bot_id) == bot_id,
            )
        )
        result = await session.execute(sql)
        return result.rowcount if isinstance(result, CursorResult) else 0


class DNASign(BaseIDModel, table=True):
    __table_args__: dict[str, Any] = {"extend_existing": True}
    uid: str = Field(title="二重螺旋UID")
    game_sign: int = Field(default=0, title="游戏签到")
    bbs_sign: int = Field(default=0, title="社区签到")
    bbs_detail: int = Field(default=0, title="社区浏览")
    bbs_like: int = Field(default=0, title="社区点赞")
    bbs_share: int = Field(default=0, title="社区分享")
    bbs_reply: int = Field(default=0, title="社区回复")
    date: str = Field(default=get_today_date(), title="签到日期")

    @classmethod
    def build(cls, uid: str):
        date = get_today_date()
        return cls(uid=uid, date=date)

    @classmethod
    async def _find_sign_record(
        cls: type[T_DNASign],
        session: AsyncSession,
        uid: str,
        date: str,
    ) -> T_DNASign | None:
        """查找指定UID和日期的签到记录（内部方法）"""
        query = select(cls).where(cls.uid == uid).where(cls.date == date)
        result = await session.execute(query)
        return result.scalars().first()

    @classmethod
    @with_lock
    @with_session
    async def upsert_dna_sign(
        cls: type[T_DNASign],
        session: AsyncSession,
        dna_sign_data: T_DNASign,
    ) -> T_DNASign | None:
        """
        插入或更新签到数据
        返回更新后的记录或新插入的记录
        """
        if not dna_sign_data.uid:
            return None

        # 确保日期有值
        dna_sign_data.date = dna_sign_data.date or get_today_date()

        # 查询是否存在记录
        record = await cls._find_sign_record(session, dna_sign_data.uid, dna_sign_data.date)

        if record:
            # 更新已有记录
            for field in [
                "game_sign",
                "bbs_sign",
                "bbs_detail",
                "bbs_like",
                "bbs_share",
                "bbs_reply",
            ]:
                value = getattr(dna_sign_data, field)
                if value:
                    setattr(record, field, value)
            result = record
        else:
            # 添加新记录 - 直接从Pydantic模型创建SQLModel实例
            result = cls(**dna_sign_data.model_dump())
            session.add(result)

        return result

    @classmethod
    @with_session
    async def get_sign_data(
        cls: type[T_DNASign],
        session: AsyncSession,
        uid: str,
        date: str | None = None,
    ) -> T_DNASign | None:
        """根据UID和日期查询签到数据"""
        date = date or get_today_date()
        return await cls._find_sign_record(session, uid, date)

    @classmethod
    @with_session
    async def get_all_sign_data_by_date(
        cls: type[T_DNASign],
        session: AsyncSession,
        date: str | None = None,
    ) -> list[T_DNASign]:
        """根据日期查询所有签到数据"""
        actual_date = date or get_today_date()
        sql = select(cls).where(cls.date == actual_date)
        result = await session.execute(sql)
        return list(result.scalars().all())

    @classmethod
    @with_lock
    @with_session
    async def clear_sign_record(
        cls: type[T_DNASign],
        session: AsyncSession,
        date: str,
    ):
        """清除签到记录"""
        sql = delete(cls).where(col(cls.date) <= date)
        await session.execute(sql)


class DNAPrivacy(BaseIDModel, table=True):
    """隐私设置表：存储用户的窥屏权限设置"""

    __table_args__: dict[str, Any] = {"extend_existing": True}
    user_id: str = Field(default=None, title="用户ID")
    bot_id: str = Field(default=None, title="Bot ID")
    group_id: str | None = Field(default=None, title="群组ID")
    allow_peek: bool = Field(default=True, title="允许被窥屏")
    uid_hidden: bool = Field(default=False, title="隐藏UID")

    @classmethod
    @with_session
    async def get_privacy_setting(
        cls: type[T_DNAPrivacy],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> T_DNAPrivacy | None:
        """获取用户的隐私设置"""
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_lock
    @with_session
    async def set_privacy_setting(
        cls: type[T_DNAPrivacy],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        allow_peek: bool | None = None,
        uid_hidden: bool | None = None,
    ) -> T_DNAPrivacy:
        """设置用户的隐私设置

        Args:
            user_id: 用户ID
            bot_id: Bot ID
            allow_peek: 是否允许被窥屏，None 表示不修改
            uid_hidden: 是否隐藏UID，None 表示不修改
        """
        sql = select(cls).where(
            cls.user_id == user_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()

        if data:
            # 更新现有记录
            record = data[0]
            if allow_peek is not None:
                record.allow_peek = allow_peek
            if uid_hidden is not None:
                record.uid_hidden = uid_hidden
            return record
        else:
            # 创建新记录
            new_record = cls(
                user_id=user_id,
                bot_id=bot_id,
                allow_peek=allow_peek if allow_peek is not None else True,
                uid_hidden=uid_hidden if uid_hidden is not None else False,
            )
            session.add(new_record)
            return new_record

    @classmethod
    @with_session
    async def is_uid_hidden(
        cls: type[T_DNAPrivacy],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> bool:
        """检查用户是否设置了隐藏UID

        查询全局配置（group_id is None），确保结果确定性。

        返回值:
        - True: 用户设置了隐藏UID
        - False: 用户未设置隐藏UID（默认）
        """
        sql = (
            select(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.group_id).is_(None),
            )
            .order_by(col(cls.id).desc())
            .limit(1)
        )
        result = await session.execute(sql)
        record = result.scalar_one_or_none()
        if record is not None:
            return record.uid_hidden
        return False


class DNAGroupPrivacy(BaseIDModel, table=True):
    """群组隐私设置表：存储群的全体隐私设置"""

    __tablename__: ClassVar[str] = "dna_group_privacy"
    __table_args__: dict[str, Any] = {"extend_existing": True}
    group_id: str = Field(default=None, title="群组ID", unique=True)
    bot_id: str = Field(default=None, title="Bot ID")
    force_allow_peek: bool | None = Field(default=None, title="强制全体允许窥屏")
    force_uid_hidden: bool | None = Field(default=None, title="强制全体隐藏UID")

    @classmethod
    @with_session
    async def get_group_privacy(
        cls: type[T_DNAGroupPrivacy],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
    ) -> T_DNAGroupPrivacy | None:
        """获取群的隐私设置"""
        sql = select(cls).where(
            cls.group_id == group_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_lock
    @with_session
    async def set_group_force_privacy(
        cls: type[T_DNAGroupPrivacy],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
        field: Literal["force_allow_peek", "force_uid_hidden"],
        value: bool | None,
    ) -> T_DNAGroupPrivacy:
        """设置群的一项强制隐私设置，value=None 表示清除该项"""
        sql = select(cls).where(col(cls.group_id) == group_id, col(cls.bot_id) == bot_id)
        record = (await session.execute(sql)).scalars().first()
        if record is None:
            record = cls(group_id=group_id, bot_id=bot_id)
            session.add(record)
        if field == "force_allow_peek":
            record.force_allow_peek = value
        else:
            record.force_uid_hidden = value
        return record

    @classmethod
    @with_session
    async def check_group_force_privacy(
        cls: type[T_DNAGroupPrivacy],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
    ) -> bool | None:
        """检查群是否有强制隐私设置

        返回值:
        - True: 强制全体开偷窥
        - False: 强制全体防偷窥
        - None: 没有强制设置
        """
        sql = select(cls).where(
            cls.group_id == group_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        if data:
            return data[0].force_allow_peek
        return None

    @classmethod
    @with_session
    async def check_uid_hidden(
        cls: type[T_DNAGroupPrivacy],
        session: AsyncSession,
        group_id: str | None,
        bot_id: str,
    ) -> bool | None:
        """检查群是否有强制UID隐藏设置

        返回值:
        - True: 强制全体隐藏UID
        - False: 强制全体显示UID
        - None: 没有强制设置
        """
        if not group_id:
            return None
        sql = select(cls).where(
            cls.group_id == group_id,
            cls.bot_id == bot_id,
        )
        result = await session.execute(sql)
        data = result.scalars().all()
        if data:
            return data[0].force_uid_hidden
        return None


@site.register_admin
class DNABindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋绑定管理",
        icon="fa fa-group",
    )

    # 配置管理模型
    model = DNABind


@site.register_admin
class DNAUserAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋用户管理",
        icon="fa fa-users",
    )

    # 配置管理模型
    model = DNAUser


@site.register_admin
class DNASignAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋签到管理",
        icon="fa fa-check",
    )

    # 配置管理模型
    model = DNASign


@site.register_admin
class DNAPrivacyAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋隐私管理",
        icon="fa fa-eye-slash",
    )

    # 配置管理模型
    model = DNAPrivacy


@site.register_admin
class DNAGroupPrivacyAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋群隐私管理",
        icon="fa fa-users-slash",
    )

    # 配置管理模型
    model = DNAGroupPrivacy
