import re
import os
import sys
import time
import json
import logging
import asyncio
import datetime
import requests
from cqhttp import CQHttp
from random import choice, random

from utils.biliapi import WsApi, BiliApi
from utils.ws import ReConnectingWsClient


if "linux" in sys.platform:
    from config import config
    LOG_PATH = config["LOG_PATH"]

    access_token = config["cq_access_token"]
    secret = config["cq_secret"]

    bot = CQHttp(api_root='http://49.234.17.23:5700/', access_token=access_token, secret=access_token)
else:
    LOG_PATH = "./log"
    access_token = ""
    bot = CQHttp(api_root='http://127.0.0.1:5700/')


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
file_handler = logging.FileHandler(os.path.join(LOG_PATH, "hansy.log"), encoding="utf-8")
file_handler.setFormatter(log_format)
logger = logging.getLogger("hansy")
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
logger.addHandler(file_handler)
logging = logger


class DanmakuSetting(object):
    MONITOR_ROOM_ID = 2516117
    MONITOR_UID = 65568410

    MSG_INTERVAL = 120
    MSG_LIST = [
        "📢 想要观看直播回放的小伙伴，记得关注录屏组哦~",
        "📢 喜欢泡泡的小伙伴，加粉丝群436496941来玩耍呀~",
        "📢 更多好听的原创歌和翻唱作品，网易云音乐搜索「管珩心」~",
        "📢 你的关注和弹幕是直播的动力，小伙伴们多粗来聊天掰头哇~",
        "📢 赠送1个B坷垃，就可以领取珩心专属「电磁泡」粉丝勋章啦~",
        "📢 有能力的伙伴上船支持一下主播鸭~还能获赠纪念礼品OvO",
    ]
    MSG_INDEX = 0

    LAST_ACTIVE_TIME = time.time() - 3600
    THRESHOLD = 79000

    THANK_GIFT = True
    THANK_FOLLOWER = False

    @classmethod
    def get_if_master_is_active(cls):
        message_peroid = len(cls.MSG_LIST) * cls.MSG_INTERVAL
        result = time.time() - cls.LAST_ACTIVE_TIME < message_peroid
        return result

    @classmethod
    def flush_last_active_time(cls):
        cls.LAST_ACTIVE_TIME = time.time()

    # notice
    TEST_GROUP_ID_LIST = [159855203, ]
    NOTICE_GROUP_ID_LIST = [
        159855203,  # test
        883237694,  # guard
        436496941,
        591691708,
    ]
    LAST_LIVE_TIME = time.time() - 3600
    LAST_LIVE_STATUS_UPDATE_TIME = ""


class TempData:
    user_name_to_uid_map = {}
    silver_gift_list = []
    fans_id_set = None


def send_qq_notice_message(test=False):
    url = "https://api.live.bilibili.com/AppRoom/index?platform=android&room_id=2516117"
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,image/apng,*/*;q=0.8"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/70.0.3538.110 Safari/537.36"
        ),
    }
    try:
        r = requests.get(url=url, headers=headers)
        if r.status_code != 200:
            raise Exception("Error status code!")
        result = json.loads(r.content.decode("utf-8"))
        title = result.get("data", {}).get("title")
        image = result.get("data", {}).get("cover")
    except Exception as e:
        logging.exception("Error when get live room info: %s" % e, exc_info=True)
        title = "珩心小姐姐开播啦！快来围观"
        image = "https://i1.hdslb.com/bfs/archive/a6a3d6f3d3582fd5172f6f829c0fe5522705e399.jpg"

    content = "这里是一只易燃易咆哮的小狮子，宝物是糖果锤！嗷呜(っ*´□`)っ~不关注我的通通都要被一！口！吃！掉！"

    groups = DanmakuSetting.TEST_GROUP_ID_LIST if test else DanmakuSetting.NOTICE_GROUP_ID_LIST
    for group_id in groups:
        message = "[CQ:share,url=https://live.bilibili.com/2516117,title=%s,content=%s,image=%s]" % (
            title, content, image
        )
        bot.send(context={"message_type": "group", "group_id": group_id}, message=message)

        message = "[CQ:at,qq=all] \n直播啦！！快来听泡泡唱歌咯，本次直播主题：\n%s" % title
        bot.send(context={"message_type": "group", "group_id": group_id}, message=message)


async def send_hansy_danmaku(msg, user=""):
    try:
        if user == "DD":
            from data import COOKIE_DD as COOKIE
        else:
            from data import COOKIE_LP as COOKIE
    except Exception as e:
        logging.error(f"Cannot load cookie, e: {e}.", exc_info=True)
        return

    flag, msg = await BiliApi.send_danmaku(
        message=msg,
        room_id=DanmakuSetting.MONITOR_ROOM_ID,
        cookie=COOKIE
    )
    if not flag:
        logging.error(f"Danmaku [{msg}] send failed, msg: {msg}, user: {user}.")


async def save_gift(uid, name, face, gift_name, count):
    logging.info(f"Saving new gift, user: {uid}-{name} -> {gift_name}*{count}.")
    if not face:
        face = await BiliApi.get_user_face(uid)

    faces = map(lambda x: x.split(".")[0], os.listdir("/home/wwwroot/statics/static/face"))
    if str(uid) not in faces:
        try:
            r = requests.get(face, timeout=20)
            if r.status_code != 200:
                raise Exception("Request error when get face!")
            with open(f"/home/wwwroot/statics/static/face/{uid}", "wb") as f:
                f.write(r.content)
        except Exception as e:
            logging.error(f"Cannot save face, e: {e}, {uid} -> {face}")
        else:
            logging.info(f"User face saved, {uid} -> {face}")

    data = {
        "created_time": str(datetime.datetime.now()),
        "uid": uid,
        "sender": name,
        "gift_name": gift_name,
        "count": count,
    }
    with open("/home/wwwroot/async.madliar/temp_data/gift_list.txt", "a+") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
    logging.info(f"New gift saved, user: {uid}-{name} -> {gift_name}*{count}.")


async def proc_message(message):
    cmd = message.get("cmd")
    if cmd.startswith("DANMU_MSG"):
        info = message.get("info", {})
        msg = str(info[1])
        uid = info[2][0]
        user_name = info[2][1]
        is_admin = info[2][2]
        ul = info[4][0]
        d = info[3]
        dl = d[0] if d else "-"
        deco = d[1] if d else "undefined"
        logging.info(f"{'[管] ' if is_admin else ''}[{deco} {dl}] [{uid}][{user_name}][{ul}]-> {msg}")

        if msg.startswith("📢") or msg.startswith("🤖"):
            return

        DanmakuSetting.flush_last_active_time()

        if is_admin or uid == 39748080:
            if msg == "开启答谢":
                DanmakuSetting.THANK_GIFT = True
                await send_hansy_danmaku("🤖 弹幕答谢已开启。房管发送「关闭答谢」即可关闭。")

            elif msg == "关闭答谢":
                DanmakuSetting.THANK_GIFT = False
                await send_hansy_danmaku("🤖 弹幕答谢已关闭。房管发送「开启答谢」即可再次打开。")

            elif msg == "开启答谢关注":
                DanmakuSetting.THANK_FOLLOWER = True
                await send_hansy_danmaku("🤖 答谢关注已开启。房管发送「关闭答谢关注」即可关闭。")

            elif msg == "关闭答谢关注":
                DanmakuSetting.THANK_FOLLOWER = False
                TempData.fans_id_set = None
                await send_hansy_danmaku("🤖 答谢关注已关闭。房管发送「开启答谢关注」即可再次打开。")

            elif msg == "清空缓存":
                TempData.fans_id_set = None
                await send_hansy_danmaku("🤖 完成。")

            elif msg == "状态":
                await send_hansy_danmaku(
                    f"礼物{'开' if DanmakuSetting.THANK_GIFT else '关'}-"
                    f"关注{'开' if DanmakuSetting.THANK_FOLLOWER else '关'}-"
                )

        if "好听" in msg and random() > 0.7:
            await send_hansy_danmaku(choice([
                "🤖 φ(≧ω≦*)♪好听好听！ 打call ᕕ( ᐛ )ᕗ",
                "🤖 好听！给跪了! ○|￣|_ (这么好听还不摁个关注？！",
                "🤖 好听! 我的大仙泡最美最萌最好听 ´･∀･)乂(･∀･｀",
                "🤖 觉得好听的话，就按个关注别走好吗…(๑˘ ˘๑) ♥",
            ]))

        elif "点歌" in msg and "吗" in msg:
            await send_hansy_danmaku("🤖 可以点歌哦，等这首唱完直接发歌名就行啦╰(*°▽°*)╯")

        elif msg[:4] == "#粉丝数":
            query = "".join(msg[4:].split())
            if not query:
                return await send_hansy_danmaku(f"🤖 指令错误。示例： #粉丝数 2516117。")

            if query.isdigit():
                live_room_id = query
                user_id = await BiliApi.get_uid_by_live_room_id(live_room_id)
                if user_id <= 0:
                    return await send_hansy_danmaku(f"🤖 查询失败，错误的直播间号{live_room_id}")
                fans_count = await BiliApi.get_fans_count_by_uid(user_id)
                await send_hansy_danmaku(f"🤖 {live_room_id}直播间有{fans_count}个粉丝。")
            else:
                user_name = query
                flag, user_id = await BiliApi.get_user_id_by_search_way(user_name)
                if not flag or not user_id or user_id <= 0:
                    return await send_hansy_danmaku(f"🤖 查询失败，错误的up主名字{user_name}")
                fans_count = await BiliApi.get_fans_count_by_uid(user_id)
                await send_hansy_danmaku(f"🤖 {user_name}有{fans_count}个粉丝。")

        if uid == 20932326 and msg == "测试通知":
            send_qq_notice_message(test=True)

            time_interval = time.time() - DanmakuSetting.LAST_LIVE_TIME
            message = (
                f"通知间隔太短：上次开播{time_interval / 60}分钟前，"
                f"刷新时间{DanmakuSetting.LAST_LIVE_STATUS_UPDATE_TIME}."
            )
            bot.send_private_msg(user_id=80873436, message=message)

    elif cmd == "SEND_GIFT":
        data = message.get("data")
        uid = data.get("uid", "--")
        face = data.get("face", "")
        uname = data.get("uname", "")
        gift_name = data.get("giftName", "")
        coin_type = data.get("coin_type", "")
        total_coin = data.get("total_coin", 0)
        num = data.get("num", "")
        if coin_type != "gold":
            if DanmakuSetting.THANK_GIFT:
                TempData.silver_gift_list.append(f"{uname}${gift_name}${num}")
            logging.info(f"SEND_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (total_coin: {total_coin})")

        elif coin_type == "gold" and uname not in TempData.user_name_to_uid_map:
            TempData.user_name_to_uid_map[uname] = {"uid": uid, "face": face}
            logging.info(f"USER_NAME_TO_ID_MAP Length: {len(TempData.user_name_to_uid_map)}")
            if len(TempData.user_name_to_uid_map) > 10000:
                TempData.user_name_to_uid_map = {}

    elif cmd == "COMBO_END":
        data = message.get("data")
        uname = data.get("uname", "")
        gift_name = data.get("gift_name", "")
        price = data.get("price")
        count = data.get("combo_num", 0)
        logging.info(f"GOLD_GIFT: [ ----- ] [{uname}] -> {gift_name}*{count} (price: {price})")

        cached_user = TempData.user_name_to_uid_map.get(uname, {})
        uid = cached_user.get("uid")
        face = cached_user.get("face")
        if DanmakuSetting.THANK_GIFT:
            await send_hansy_danmaku(f"感谢{uname}赠送的{count}个{gift_name}! 大气大气~")
        if uid and price * count > DanmakuSetting.THRESHOLD:
            await save_gift(uid, uname, face, gift_name, count)

    elif cmd == "GUARD_BUY":
        data = message.get("data")
        uid = data.get("uid")
        uname = data.get("username", "")
        gift_name = data.get("gift_name", "GUARD")
        price = data.get("price")
        num = data.get("num", 0)
        logging.info(f"GUARD_GIFT: [{uid}] [{uname}] -> {gift_name}*{num} (price: {price})")
        if DanmakuSetting.THANK_GIFT:
            await send_hansy_danmaku(f"感谢{uname}开通了{num}个月的{gift_name}! 大气大气~")

        face = TempData.user_name_to_uid_map.get(uname, {}).get("face")
        await save_gift(uid, uname, face, gift_name, num)

    elif cmd == "LIVE":
        DanmakuSetting.THANK_GIFT = False
        DanmakuSetting.THANK_FOLLOWER = True
        await send_hansy_danmaku("状态")

        time_interval = time.time() - DanmakuSetting.LAST_LIVE_TIME
        if time_interval > 60 * 40:
            DanmakuSetting.LAST_LIVE_TIME = time.time()
            send_qq_notice_message()

    elif cmd == "PREPARING":
        DanmakuSetting.THANK_GIFT = True
        DanmakuSetting.THANK_FOLLOWER = False
        await send_hansy_danmaku("状态")

        bot.send_private_msg(user_id=291020256, message="小仙女记得把歌单发我昂~\n [CQ:image,file=1.gif]")


async def send_carousel_msg():
    if not DanmakuSetting.get_if_master_is_active():
        return

    msg = DanmakuSetting.MSG_LIST[DanmakuSetting.MSG_INDEX]
    await send_hansy_danmaku(msg, user="DD")

    DanmakuSetting.MSG_INDEX = (DanmakuSetting.MSG_INDEX + 1) % len(DanmakuSetting.MSG_LIST)


async def send_recorder_group_danmaku():
    try:
        from data import COOKIE_LP
    except Exception as e:
        logging.error(f"Cannot load COOKIE_LP cookie, e: {e}.", exc_info=True)
        return

    await BiliApi.enter_room(DanmakuSetting.MONITOR_ROOM_ID, COOKIE_LP)


async def thank_gift():
    gift_list = {}
    while TempData.silver_gift_list:
        gift = TempData.silver_gift_list.pop()
        uname, gift_name, num = gift.split("$")
        key = f"{uname}${gift_name}"
        if key in gift_list:
            gift_list[key] += int(num)
        else:
            gift_list[key] = int(num)

    for key, num in gift_list.items():
        uname, gift_name = key.split("$")
        await send_hansy_danmaku(f"感谢{uname}赠送的{num}个{gift_name}! 大气大气~")


async def get_fans_list():
    if not DanmakuSetting.MONITOR_UID:
        DanmakuSetting.MONITOR_UID = await BiliApi.get_uid_by_live_room_id(DanmakuSetting.MONITOR_ROOM_ID)
    result = await BiliApi.get_fans_list(DanmakuSetting.MONITOR_UID)
    return result[::-1]


async def thank_follower():

    if not isinstance(TempData.fans_id_set, set):
        fl = await get_fans_list()
        if fl:
            TempData.fans_id_set = {x["mid"] for x in fl}
        return

    new_fans_list = await get_fans_list()
    if not new_fans_list:
        return

    new_fans_uid_set = {_["mid"] for _ in new_fans_list}
    thank_uid_list = list(new_fans_uid_set - TempData.fans_id_set)
    if len(thank_uid_list) <= 5:
        while thank_uid_list:
            thank_uid = thank_uid_list.pop(0)
            try:
                uname = [_["uname"] for _ in new_fans_list if _["mid"] == thank_uid][0]
            except Exception as e:
                logging.error(f"Cannot get uname in thank_follower: {e}, thank_uid: {thank_uid}.", exc_info=True)
            else:
                await asyncio.sleep(0.3)
                await send_hansy_danmaku(choice([
                    f"谢谢{uname}的关注~相遇是缘，愿常相伴╭❤",
                    f"感谢{uname}的关注~♪（＾∀＾●）",
                    f"感谢{uname}的关注，爱了就别走好吗ノ♥",
                    f"谢谢{uname}的关注，mua~(˙ε˙)",
                ]), user="DD")

    if len(TempData.fans_id_set) < 5000:
        TempData.fans_id_set |= new_fans_uid_set
    else:
        TempData.fans_list = new_fans_uid_set


async def update_hansy_guard_list():
    guard_list = await BiliApi.get_guard_list(uid=65568410)
    if not guard_list:
        return
    text = "\n".join([
        "".join([" ❤ " + _["name"] for _ in guard_list if _["level"] < 3]),
        "".join([" ❤ " + _["name"] for _ in guard_list if _["level"] == 3])
    ])
    with open("/home/wwwroot/async.madliar/temp_data/guard_list.txt", "wb") as f:
        f.write(text.encode("utf-8"))


async def update_hansy_live_status():
    if time.time() - DanmakuSetting.LAST_LIVE_TIME > 60*60:
        return

    flag, r = await BiliApi.get_live_status(room_id=DanmakuSetting.MONITOR_ROOM_ID)
    DanmakuSetting.LAST_LIVE_STATUS_UPDATE_TIME = f"{datetime.datetime.now()}"
    if flag and r:
        DanmakuSetting.LAST_LIVE_TIME = time.time()


async def main():
    async def on_connect(ws):
        logging.info("connected.")
        await ws.send(WsApi.gen_join_room_pkg(DanmakuSetting.MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        for m in WsApi.parse_msg(message):
            try:
                await proc_message(m)
            except Exception as e:
                logging.error(f"Error happened when proc_message: {e}", exc_info=True)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Hansy ws stated.")

    counter = -1
    while True:
        await asyncio.sleep(1)
        counter = (counter + 1) % 10000000000

        if counter % 15 == 0 and DanmakuSetting.THANK_FOLLOWER:
            await thank_follower()

        if counter % 13 == 0 and DanmakuSetting.THANK_GIFT:
            await thank_gift()

        if counter % DanmakuSetting.MSG_INTERVAL == 0:
            await send_carousel_msg()

        if counter % (60*5) == 0:
            await send_recorder_group_danmaku()

        if counter % (60*6) == 0:
            await update_hansy_live_status()

        if counter % (3600*12) == 0:
            await update_hansy_guard_list()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
