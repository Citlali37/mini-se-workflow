import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from mini_se_workflow.llm import DeepSeekClient, LLMError, parse_json_object


class LLMTests(unittest.TestCase):
    def test_json_and_fenced_output(self):
        self.assertEqual(parse_json_object('```json\n{"ok": true}\n```'), {"ok": True})
        with self.assertRaises(LLMError):
            parse_json_object("[]")
        with self.assertRaises(LLMError):
            parse_json_object("invalid")
        for content in ('{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}'):
            with self.assertRaises(LLMError):
                parse_json_object(content)

    def test_empty_content_still_records_billable_usage(self):
        client = DeepSeekClient('https://api.deepseek.com', 'test-secret', 'test-model')
        response = io.BytesIO(json.dumps({'choices':[{'message':{'content':''},'finish_reason':'length'}],
            'usage':{'completion_tokens':8192}}).encode())
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(LLMError):
                client.complete_json(agent_name='requirements',system_prompt='s',user_prompt='u')
        self.assertEqual(client.usage_records[0]['usage']['completion_tokens'], 8192)
        self.assertEqual(client.usage_records[0]['finish_reason'], 'length')

    def test_http_retry_preserves_request_and_structured_output(self):
        client = DeepSeekClient("https://api.deepseek.com", "test-secret", "deepseek-chat", max_retries=2)
        error = urllib.error.HTTPError(client.url, 429, "rate limit", {}, io.BytesIO(b"temporary"))
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": '{"summary":"done"}'}}]}).encode())
        with patch("urllib.request.urlopen", side_effect=[error, response]) as call, patch("time.sleep"):
            result = client.complete_json(agent_name="coding", system_prompt="system", user_prompt="user")
        self.assertEqual(result["summary"], "done")
        self.assertEqual(call.call_count, 2)
        body = json.loads(call.call_args.args[0].data)
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_authentication_failure_is_not_retried(self):
        client = DeepSeekClient("https://api.deepseek.com", "test-secret", "deepseek-chat", max_retries=3)
        error = urllib.error.HTTPError(client.url, 401, "unauthorized", {}, io.BytesIO(b"invalid key"))
        with patch("urllib.request.urlopen", side_effect=error) as call:
            with self.assertRaises(LLMError):
                client.complete_json(agent_name="design", system_prompt="s", user_prompt="u")
        self.assertEqual(call.call_count, 1)

    def test_request_budget_and_usage_records(self):
        client = DeepSeekClient("https://api.deepseek.com", "test-secret", "test-model", max_tokens=8192, request_limit=1)
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens":10,"completion_tokens":20}}).encode())
        with patch("urllib.request.urlopen", return_value=response) as call:
            client.complete_json(agent_name="requirements", system_prompt="s", user_prompt="u")
            with self.assertRaises(LLMError):
                client.complete_json(agent_name="design", system_prompt="s", user_prompt="u")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(client.usage_records[0]['usage']['completion_tokens'], 20)
        self.assertEqual(json.loads(call.call_args.args[0].data)['max_tokens'], 8192)


if __name__ == "__main__":
    unittest.main()
