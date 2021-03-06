import asyncio
from typing import List
from config.log4 import config_logger
from src.db.queries.queries import queries, LTUser


logging = config_logger("auto_intimacy")


NON_LIMIT_UID_LIST = (
    20932326,  # dd
    39748080,  # 录屏
    312186483,  # 桃子
    87301592,  # 酋长
)


async def send_gift(cookie, medal, user_name=""):
    from utils.biliapi import BiliApi

    r = await BiliApi.get_medal_info_list(cookie)
    if not r:
        logging.error(f"Cannot get medal of user: {user_name}")
        return

    uid = r[0]["uid"]
    target_model = [_ for _ in r if _["medal_name"] == medal and "roomid" in _]
    if not target_model:
        return
    target_model = target_model[0]
    logging.info(
        f"\n{'-'*80}\n"
        f"开始处理：{uid} {user_name} -> {target_model['medal_name']}"
    )

    live_room_id = await BiliApi.force_get_real_room_id(target_model["roomid"])
    ruid = target_model["anchorInfo"]["uid"]

    today_feed = target_model["todayFeed"]
    day_limit = target_model["dayLimit"]
    left_intimacy = day_limit - today_feed
    logging.info(f"今日剩余亲密度: {left_intimacy}")

    bag_list = await BiliApi.get_bag_list(cookie)
    available_bags = [bag for bag in bag_list if bag["gift_name"] == "辣条" and bag["expire_at"] > 0]
    available_bags.sort(key=lambda x: x["expire_at"])

    # 获取背包中的辣条
    send_list = []
    for bag in available_bags:
        gift_num = bag["gift_num"]
        intimacy_single = 1
        need_send_gift_num = min(left_intimacy // intimacy_single, gift_num)

        if need_send_gift_num > 0:
            send_list.append({
                "corner_mark": bag["corner_mark"],
                "coin_type": None,
                "gift_num": need_send_gift_num,
                "bag_id": bag["bag_id"],
                "gift_id": bag["gift_id"],
            })
            left_intimacy -= intimacy_single * need_send_gift_num

        if left_intimacy <= 0:
            break

    # 获取钱包 赠送银瓜子辣条
    if uid in NON_LIMIT_UID_LIST and left_intimacy > 0:
        wallet_info = await BiliApi.get_wallet(cookie)
        silver = wallet_info.get("silver", 0)
        supplement_lt_num = min(silver // 100, left_intimacy)
        if supplement_lt_num > 0:
            send_list.append({
                "corner_mark": "银瓜子",
                "coin_type": "silver",
                "gift_num": supplement_lt_num,
                "bag_id": 0,
                "gift_id": 1,
            })
            left_intimacy -= supplement_lt_num

    for gift in send_list:
        flag, data = await BiliApi.send_gift(
            gift["gift_id"], gift["gift_num"], gift["coin_type"], gift["bag_id"], ruid, live_room_id, cookie
        )
        if not flag:
            logging.info(f"Send failed, msg: {data.get('message', 'unknown')}")

    send_msg = "\n".join([f"{s['corner_mark']}辣条 * {s['gift_num']}" for s in send_list])
    logging.info(
        f"赠送礼物列表:\n\n"
        f"{send_msg}\n\n"
        f"{user_name} 剩余亲密度: {left_intimacy}\n"
        f"{'-'*80}"
    )


async def main():
    lt_users: List[LTUser] = await queries.get_lt_user_by(available=True)
    for lt_user in lt_users:
        for medal in lt_user.send_medals:
            await send_gift(cookie=lt_user.cookie, medal=medal, user_name=lt_user.name)

    lt_user: LTUser = await queries.get_lt_user_by_uid(user_id=312186483)
    if lt_user:
        await send_gift(cookie=lt_user.cookie, medal="發电姬", user_name="桃子")

    lt_user: LTUser = await queries.get_lt_user_by_uid(user_id=87301592)
    if lt_user:
        await send_gift(cookie=lt_user.cookie, medal="电磁泡", user_name="村长")

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
