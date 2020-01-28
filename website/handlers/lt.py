import time
import json
import traceback
from aiohttp import web
from random import randint
from jinja2 import Template
from utils.cq import bot_zy
from config import CDN_URL, g
from utils.biliapi import BiliApi
from utils.highlevel_api import DBCookieOperator
from config.log4 import website_logger as logging
from utils.dao import redis_cache, LTUserSettings
from utils.dao import LtUserLoginPeriodOfValidity


def request_frequency_control(time_interval=4):
    user_requests_records = []  # [(uniq, time), ... ]

    def deco(f):
        async def wrapped(request):
            host = request.headers.get("Host", "governors")
            ua = request.headers.get("User-Agent", "NON_UA")
            remote = request.remote
            unique_identification = hash((host, ua, remote))

            last_req_time = 0
            for _ in user_requests_records:
                if _[0] == unique_identification:
                    last_req_time = _[1]
                    break

            if time.time() - last_req_time < time_interval:
                return web.Response(text=f"你的请求过于频繁。请{time_interval}秒钟后再试。", content_type="text/html")

            result = await f(request)

            user_requests_records.insert(0, (unique_identification, time.time()))

            while len(user_requests_records) > 2000:
                user_requests_records.pop()

            return result
        return wrapped
    return deco


def render_to_response(template, context=None):
    try:
        with open(template, encoding="utf-8") as f:
            template_context = f.read()
    except IOError:
        template_context = "<center><h3>Template Does Not Existed!</h3></center>"

    template = Template(template_context)
    return web.Response(text=template.render(context or {}), content_type="text/html")


def json_response(data):
    return web.Response(text=json.dumps(data), content_type="application/json")


async def check_login(request):
    try:
        bili_uid = request.cookies["DedeUserID"]
        mad_token = request.cookies["mad_token"]
        bili_uid = int(bili_uid)

        key = f"LT_USER_MAD_TOKEN_{bili_uid}"
        mad_token_cache = await redis_cache.get(key)
        if mad_token != mad_token_cache:
            raise ValueError("Bad mad_token.")

    except (KeyError, ValueError, TypeError):
        return

    return bili_uid


async def lt(request):
    token = request.match_info['token']
    if not token:
        return web.HTTPForbidden()

    ua = request.headers.get("User-Agent", "NON_UA")
    remote_ip = request.remote  # request.headers.get("X-Real-IP", "")
    logging.info(f"LT_ACCESS_TOKEN_RECEIVED: {token}, ip: {remote_ip}. UA: {ua}")

    key = F"LT_ACCESS_TOKEN_{token}"
    r = await redis_cache.get(key=key)
    if not r:
        return web.HTTPNotFound()

    r = await redis_cache.incr(key)
    if r < 4:
        return web.Response(text="<h3>请刷新此页面，直到能够正常显示。</h3>", content_type="text/html")

    await redis_cache.delete(key)
    context = {"CDN_URL": CDN_URL}
    return render_to_response("website/templates/website_homepage.html", context=context)


async def login(request):
    data = await request.post()
    account = data['account']
    password = data['password']
    email = data["email"]
    if not account or not password:
        return json_response({"code": 403, "err_msg": "输入错误！检查你的输入!"})

    try:
        flag, obj = await DBCookieOperator.add_user_by_account(
            account=account, password=password, notice_email=email)
    except Exception as e:
        return json_response({"code": 500, "err_msg": f"服务器内部发生错误! {e}\n{traceback.format_exc()}"})

    if not flag:
        return json_response({"code": 403, "err_msg": f"操作失败！原因：{obj}"})

    await LtUserLoginPeriodOfValidity.update(obj.DedeUserID)

    key = f"LT_USER_MAD_TOKEN_{obj.DedeUserID}"
    mad_token = f"{int(time.time() * 1000):0x}{randint(0x1000, 0xffff):0x}"
    await redis_cache.set(key=key, value=mad_token, timeout=3600*24*30)

    response = json_response({"code": 0, "location": "/lt/settings"})
    response.set_cookie(name="mad_token", value=mad_token, httponly=True)
    response.set_cookie(name="DedeUserID", value=obj.DedeUserID, httponly=True)
    return response


async def settings(request):
    context = {"CDN_URL": CDN_URL}
    bili_uid = await check_login(request)
    if not bili_uid:
        context["err_msg"] = "你无权访问此页面。请返回宝藏站点首页，正确填写你的信息，然后点击「我要挂辣条」按钮。"
        return render_to_response("website/templates/settings.html", context=context)

    obj = await DBCookieOperator.get_by_uid(user_id=bili_uid)
    context["user_name"] = obj.name
    context["user_id"] = obj.uid
    context["settings"] = await LTUserSettings.get(uid=bili_uid)
    return render_to_response("website/templates/settings.html", context=context)


async def post_settings(request):
    bili_uid = await check_login(request)
    if not bili_uid:
        return json_response({"code": 403, "err_msg": "你无权访问。"})

    data = await request.post()
    try:
        tv_percent = int(data["tv_percent"])
        guard_percent = int(data["guard_percent"])
        pk_percent = int(data["pk_percent"])
        storm_percent = int(data["storm_percent"])
        anchor_percent = int(data["anchor_percent"])
        medals = [m.strip() for m in data["medals"].split("\r\n")]
        medals = [m for m in medals if m]
    except (KeyError, TypeError, ValueError) as e:
        return json_response({"code": 403, "err_msg": f"你提交了不正确的参数 ！{e}\n{traceback.format_exc()}"})

    if (
        not 0 <= tv_percent <= 100
        or not 0 <= guard_percent <= 100
        or not 0 <= pk_percent <= 100
        or not 0 <= storm_percent <= 100
        or not 0 <= anchor_percent <= 100
    ):
        return json_response({"code": 403, "err_msg": "范围错误！请设置0~100 ！"})

    for m in medals:
        if not isinstance(m, str) or not 0 < len(m) <= 6:
            return json_response({"code": 403, "err_msg": f"错误的勋章：{m}"})

    await LTUserSettings.set(
        uid=bili_uid,
        tv_percent=tv_percent,
        guard_percent=guard_percent,
        pk_percent=pk_percent,
        storm_percent=storm_percent,
        anchor_percent=anchor_percent,
        medals=medals,
    )
    return json_response({"code": 0})


async def trends_qq_notice(request):
    token = request.query.get("token")
    if token == "BXzgeJTWxGtd6b5F":
        post_data = request.query.get("post_data")
        uid_to_dynamic = json.loads(post_data, encoding="utf-8")
        for uid, dynamic_id_list in uid_to_dynamic.items():
            uid = int(uid)
            dynamic_id_set = set(dynamic_id_list)

            key = f"MONITOR_BILI_UID_V2_{uid}"
            existed_dynamic_id_set = await redis_cache.get(key=key)
            if not isinstance(existed_dynamic_id_set, set):
                await redis_cache.set(key=key, value=dynamic_id_set)

                bili_user_name = await BiliApi.get_user_name(uid=uid)
                message = f"{bili_user_name}(uid: {uid})的动态监测已经添加！"
                bot_zy.send_private_msg(user_id=g.QQ_NUMBER_雨声雷鸣, message=message)
                bot_zy.send_private_msg(user_id=g.QQ_NUMBER_DD, message=message)
                return web.Response(status=206)

            new_dynamics = dynamic_id_set - existed_dynamic_id_set
            if new_dynamics:
                refreshed_data = dynamic_id_set | existed_dynamic_id_set
                await redis_cache.set(key=key, value=refreshed_data)

                try:
                    flag, dynamics = await BiliApi.get_user_dynamics(uid=uid)
                    if not flag:
                        raise Exception(f"Cannot get user dynamics!")

                    latest_dynamic = dynamics[0]
                    bili_user_name = latest_dynamic["desc"]["user_profile"]["info"]["uname"]
                    content, pictures = await BiliApi.get_user_dynamic_content_and_pictures(latest_dynamic)

                    content = "\n".join(content)
                    message = f"{bili_user_name}(uid: {uid})新动态：\n\n{content}"

                    if uid == 337052615:
                        latest_dynamic_id = latest_dynamic["desc"]["dynamic_id"]
                        from website.handlers.cq_zy import BotUtils
                        await BotUtils().proc_dynamic(
                            user_id=250666570,
                            msg=f"#动态{latest_dynamic_id}",
                            group_id=895699676
                        )

                    if not pictures:
                        image = "https://i0.hdslb.com/bfs/space/cb1c3ef50e22b6096fde67febe863494caefebad.png"
                    else:
                        image = pictures[0]

                    message_share = (
                        f"\n\n[CQ:share,"
                        f"url=https://t.bilibili.com/{dynamic_id_list[0]},"
                        f"title={content[:30].replace(',', '，')},content=Bilibili动态,image={image}]"
                    )
                    bot_zy.send_private_msg(user_id=171660901, message=message_share)

                except Exception as e:
                    error_msg = f"Error happened when fetching user dynamic: {e}\n\n{traceback.format_exc()}"
                    logging.error(error_msg)

                    bili_user_name = await BiliApi.get_user_name(uid=uid)
                    message = f"{bili_user_name}(uid: {uid})有新动态啦! 动态id：{dynamic_id_list[0]}！"

                bot_zy.send_private_msg(user_id=171660901, message=message)

        return web.Response(status=206)
    return web.Response(status=403)
