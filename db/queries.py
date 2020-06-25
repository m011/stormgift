import datetime
from typing import Union, List
from db.tables import LTUser
from utils.dao import redis_cache


class LTUserQueryMixin:
    key = LTUser.__key__

    async def _save_lt_user(self, lt_user: LTUser) -> None:
        await redis_cache.hash_map_set(self.key, {lt_user.DedeUserID: lt_user.dict()})

    async def upsert_lt_user(
            self,
            DedeUserID: int,
            SESSDATA: str,
            bili_jct: str,
            sid: str,
            DedeUserID__ckMd5: str,
            access_token: str,
            refresh_token: str,
            account: str = None,
            password: str = None,
            notice_email: str = None,
            available: bool = True,
    ) -> LTUser:

        update_params = dict(
            DedeUserID=DedeUserID,
            SESSDATA=SESSDATA,
            bili_jct=bili_jct,
            sid=sid,
            DedeUserID__ckMd5=DedeUserID__ckMd5,
            access_token=access_token,
            refresh_token=refresh_token,
            available=available,
        )

        existed_lt_user = await self.get_lt_user_by_uid(user_id=DedeUserID)
        if not existed_lt_user:
            lt_user = LTUser(**update_params)
        else:
            create_params = existed_lt_user.dict()
            create_params.update(update_params)
            lt_user = LTUser(**create_params)

        if account is not None:
            lt_user.account = account
        if password is not None:
            lt_user.password = password
        if notice_email is not None:
            lt_user.notice_email = notice_email

        await self._save_lt_user(lt_user)
        return lt_user

    async def set_lt_user_invalid(self, user_id: int) -> Union[LTUser, None]:
        # TODO： re-login or notice

        lt_user = await self.get_lt_user_by_uid(user_id=user_id)
        if not lt_user or lt_user.available:
            return lt_user

        lt_user.available = False
        await self._save_lt_user(lt_user)

        if lt_user.bind_qq:
            from utils.cq import async_zy
            await async_zy.send_private_msg(
                user_id=lt_user.bind_qq,
                message=f"你挂的辣条机已经掉线，请重新登录。{lt_user}"
            )
        return lt_user

    async def set_lt_user_if_is_vip(self, user_id: int, is_vip: bool) -> Union[LTUser, None]:
        lt_user = await self.get_lt_user_by_uid(user_id=user_id)
        if not lt_user:
            return
        lt_user.is_vip = is_vip
        await self._save_lt_user(lt_user)
        return lt_user

    async def set_lt_user_blocked(self, user_id: int) -> Union[LTUser, None]:
        lt_user = await self.get_lt_user_by_uid(user_id=user_id)
        if not lt_user:
            return
        lt_user.blocked_time = datetime.datetime.now()
        await self._save_lt_user(lt_user)
        return lt_user

    async def get_lt_user_by_uid(self, user_id: Union[str, int]) -> Union[LTUser, None]:
        user_id = LTUser.__UID_STR_TO_INT_MAP__.get(user_id, user_id)
        if not isinstance(user_id, int):
            return None

        result = await redis_cache.hash_map_get(self.key, user_id)
        if not result:
            return
        return LTUser(**result)

    async def get_all_lt_user(self) -> List[LTUser]:
        cached = await redis_cache.hash_map_get_all(self.key)
        result = []
        for e in cached.values():
            result.append(LTUser(**e))
        return result

    async def get_lt_user_by(
            self,
            available: bool = None,
            is_vip: bool = None,
            is_blocked: bool = None,
    ) -> List[LTUser]:

        all_users = await self.get_all_lt_user()
        result = []
        for u in all_users:
            if available is not None and u.available != available:
                continue
            if is_vip is not None and u.is_vip != is_vip:
                continue
            if is_blocked is not None and u.is_blocked != is_blocked:
                continue
            result.append(u)

        return result

    async def get_an_available_lt_user(self) -> Union[LTUser, None]:
        all_users = await self.get_all_lt_user()
        for u in all_users:
            if u.available:
                return u


class Queries(LTUserQueryMixin):
    ...


queries = Queries()