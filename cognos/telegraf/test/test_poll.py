import json
import cognos.telegraf.poll as poll
from requests.models import Response


def test_esc():
    dummy_string = 'string with "" quotes'
    poll.esc(dummy_string)


def test_esc_str():
    dummy_string = 'string with "" quotes'
    poll.esc_str(dummy_string)


def test_get_cognos_events(mocker):
    dummy_detach_response = {
        "errorIdOrStringIfAny": "", "errorCode": 0, "apiVersion": "0.1",
        "response": (
            "[{\"event_header\":{\"cluster_name\":\"CL_ID_1\","
            "\"node_name\":\"node_1\"},\"event_payload\":"
            "{\"category\":\"thermal\",\"domain\":\"cxl_device\","
            "\"feature_name\":\"cxl\",\""
            "observations\":{\"fpga_temp_in_F\":530,"
            "\"fpga_threshold_in_F\":100},\"severity\":\"critical\","
            "\"source\":33235991846400,\"source_type\":\"device\","
            "\"timestamp\":7335626863}}]"
        )
    }

    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_detach_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_cognos_events()
