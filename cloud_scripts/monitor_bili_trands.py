import sys
import json
import logging
import requests
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)

HOST_UID = [
    6851677,
]


def find(uid):
    url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
    params = {
        "visitor_uid": 0,
        "host_uid": uid,
        "offset_dynamic_id": 0,
    }
    r = requests.get(url=url, params=params)
    if r.status_code != 200:
        raise Exception("未能获取到动态！")

    response = json.loads(r.content, encoding="utf-8")
    cards = response["data"]["cards"]
    dynamic_id_list = [c["desc"]["dynamic_id"] for c in cards]
    return dynamic_id_list


def main_handler(event, context):
    logger.info("开始扫描动态...")
    post_data = {}
    for uid in HOST_UID:
        try:
            dynamic_id_list = find(uid)
        except Exception as e:
            logging.error("E in find: %s" % e)
            continue
        post_data[uid] = dynamic_id_list

    url = "https://www.madliar.com/lt/trends_qq_notice"
    r = requests.get(url=url, params={"token": "BXzgeJTWxGtd6b5F", "post_data": json.dumps(post_data)})
    logging.info("Post data: %s, result: %s" % (post_data, r.content))

    return {"headers": {"Content-Type": "text"}, "statusCode": 200, "body": "OK"}
