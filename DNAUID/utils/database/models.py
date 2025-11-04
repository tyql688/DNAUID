from typing import Any, Dict, List, Optional, Type, TypeVar

from sqlalchemy import delete, null, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_, or_
from sqlmodel import Field, col, select

from gsuid_core.utils.database.base_models import Bind, User, with_session
from gsuid_core.webconsole.mount_app import GsAdminModel, PageSchema, site

T_DNABind = TypeVar("T_DNABind", bound="DNABind")
T_DNAUser = TypeVar("T_DNAUser", bound="DNAUser")


class DNABind(Bind, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}
    uid: str = Field(default=None, title="二重螺旋uid")

    @classmethod
    @with_session
    async def get_group_all_uid(
        cls: Type[T_DNABind], session: AsyncSession, group_id: str
    ) -> List[T_DNABind]:
        result = await session.scalars(
            select(cls).where(col(cls.group_id).contains(group_id))
        )
        return list(result.all()) if result else []

    @classmethod
    async def insert_uid(
        cls: Type[T_DNABind],
        user_id: str,
        bot_id: str,
        uid: str,
        group_id: Optional[str] = None,
        lenth_limit: Optional[int] = None,
        is_digit: Optional[bool] = True,
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
            code = await cls.insert_data(
                user_id=user_id, bot_id=bot_id, **{"uid": uid, "group_id": group_id}
            )
            return code

        # 获取历史
        result: Optional[T_DNABind] = await cls.select_data(user_id, bot_id)
        if not result:
            return -1

        current_uids = list(dict.fromkeys(filter(None, result.uid.split("_"))))
        if uid in current_uids:
            return -2

        current_uids.append(uid)
        return await cls.update_data(user_id, bot_id, **{"uid": "_".join(current_uids)})


class DNAUser(User, table=True):
    __table_args__: Dict[str, Any] = {"extend_existing": True}
    cookie: str = Field(default="", title="Cookie")
    uid: str = Field(default=None, title="二重螺旋uid")
    dev_code: str = Field(default=None, title="设备ID")

    @classmethod
    @with_session
    async def mark_cookie_invalid(
        cls: Type[T_DNAUser], session: AsyncSession, uid: str, cookie: str, mark: str
    ):
        sql = (
            update(cls)
            .where(col(cls.uid) == uid)
            .where(col(cls.cookie) == cookie)
            .values(status=mark)
        )
        await session.execute(sql)
        return True

    @classmethod
    @with_session
    async def select_cookie(
        cls: Type[T_DNAUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> Optional[str]:
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
        cls: Type[T_DNAUser],
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ) -> Optional[T_DNAUser]:
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
    async def select_user_cookie_uids(
        cls: Type[T_DNAUser],
        session: AsyncSession,
        user_id: str,
    ) -> List[str]:
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
    async def select_data_by_cookie(
        cls: Type[T_DNAUser], session: AsyncSession, cookie: str
    ) -> Optional[T_DNAUser]:
        sql = select(cls).where(cls.cookie == cookie)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    @with_session
    async def select_data_by_cookie_and_uid(
        cls: Type[T_DNAUser], session: AsyncSession, cookie: str, uid: str
    ) -> Optional[T_DNAUser]:
        sql = select(cls).where(cls.cookie == cookie, cls.uid == uid)
        result = await session.execute(sql)
        data = result.scalars().all()
        return data[0] if data else None

    @classmethod
    async def get_user_by_attr(
        cls: Type[T_DNAUser],
        user_id: str,
        bot_id: str,
        attr_key: str,
        attr_value: str,
    ) -> Optional[Any]:
        user_list = await cls.select_data_list(user_id=user_id, bot_id=bot_id)
        if not user_list:
            return None
        for user in user_list:
            if getattr(user, attr_key) != attr_value:
                continue
            return user

    @classmethod
    @with_session
    async def get_waves_all_user(
        cls: Type[T_DNAUser], session: AsyncSession
    ) -> List[T_DNAUser]:
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
    async def delete_all_invalid_cookie(cls, session: AsyncSession):
        """删除所有无效缓存"""
        sql = delete(cls).where(
            or_(col(cls.status) == "无效", col(cls.cookie) == ""),
        )
        result = await session.execute(sql)
        return result.rowcount

    @classmethod
    @with_session
    async def delete_cookie(
        cls,
        session: AsyncSession,
        uid: str,
        user_id: str,
        bot_id: str,
    ):
        sql = delete(cls).where(
            and_(
                col(cls.user_id) == user_id,
                col(cls.uid) == uid,
                col(cls.bot_id) == bot_id,
            )
        )
        result = await session.execute(sql)
        return result.rowcount


@site.register_admin
class DNABindAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋绑定管理",
        icon="fa fa-group",
    )  # type: ignore

    # 配置管理模型
    model = DNABind


@site.register_admin
class DNAUserAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(
        label="二重螺旋用户管理",
        icon="fa fa-users",
    )  # type: ignore

    # 配置管理模型
    model = DNAUser
