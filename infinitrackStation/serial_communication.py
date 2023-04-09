import json

INPUT_START_SCAN = "ble_start_scan"
INPUT_STOP_SCAN = "ble_stop_scan"
INPUT_BLE_CONNECT = "ble_connect"

INPUT_GET_READY = "get_ready"

TYPE_STATUS = "status"
TYPE_BLE_SCAN_RESULT = "ble_scan_result"
TYPE_LORA_RECV = "lora_msg"

STATUS_READY_GLOBAL = "ready_global"
STATUS_ERROR_OCCURRED = "unknown_error"
STATUS_BLE_SCAN_STARTED = "ble_scan_started"
STATUS_BLE_SCAN_STOPPED = "ble_scan_stopped"

STATUS_BLE_DATA_SEND = "ble_data_send"


def send_message_str(msg_type: str, msg: str):
    message_data = _prepare_message(msg_type)
    message_data['msg'] = msg
    print(json.dumps(message_data))


def send_message_json(msg_type: str, msg: dict):
    message_data = _prepare_message(msg_type)
    message_data['msg'] = msg
    print(json.dumps(message_data))


def _prepare_message(msg_type: str):
    message_data = dict()
    message_data['type'] = msg_type
    return message_data
