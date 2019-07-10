import asyncio
from utils.highlevel_api import DBCookieOperator
from config.log4 import crontab_task_logger as logging


async def post_heartbeat(cookie):
    logging.info(f"Post heartbeat for {cookie.split(';')[0]}.")

    from utils.biliapi import BiliApi
    r, data = await BiliApi.post_heartbeat_5m(cookie)
    if not r:
        logging.error(f"Post heartbeat failed! msg: {data}")
        return

    r, data = await BiliApi.post_heartbeat_last_timest(cookie)
    if not r:
        logging.error(f"Cannot post last time st! msg: {data}")
        return
    logging.info(f"Post heartbeat success!")


async def main():
    objs = await DBCookieOperator.get_objs(available=True, is_vip=True)
    for obj in objs:
        await post_heartbeat(obj.cookie)
        await asyncio.sleep(5)
    logging.info("Post heart beat task done.\n\n")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
