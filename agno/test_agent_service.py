import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Dynamically add current directory to sys.path for running tests from anywhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add root folder as well to resolve any relative shared imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import json
from agent_service import app
from agno.models.message import Message as AgnoMessage

class TestAgentService(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('agent_service.Agent')
    def test_chat_success(self, mock_agent_class):
        # Setup mock Agent instance and its run return value
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Mock RunOutput
        mock_result = MagicMock()
        mock_result.content = "This is a mock assistant reply."
        mock_result.messages = [
            AgnoMessage(role="user", content="hello"),
            AgnoMessage(role="assistant", content="This is a mock assistant reply.")
        ]
        mock_agent_instance.run.return_value = mock_result

        # Post request with structured messages list
        payload = {
            "messages": [
                {"role": "user", "content": "hello"}
            ]
        }
        response = self.app.post('/chat',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["text"], "This is a mock assistant reply.")
        self.assertEqual(data["toolOutputs"], [])

        # Verify Agent.run was called with structured AgnoMessage list
        called_args, called_kwargs = mock_agent_instance.run.call_args
        self.assertIn("input", called_kwargs)
        agno_messages = called_kwargs["input"]
        self.assertEqual(len(agno_messages), 1)
        self.assertIsInstance(agno_messages[0], AgnoMessage)
        self.assertEqual(agno_messages[0].role, "user")
        self.assertEqual(agno_messages[0].content, "hello")

    @patch('agent_service.Agent')
    def test_chat_legacy_prompt(self, mock_agent_class):
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        mock_result = MagicMock()
        mock_result.content = "Reply to prompt"
        mock_result.messages = []
        mock_agent_instance.run.return_value = mock_result

        # Post request with legacy single prompt
        payload = {
            "prompt": "describe python"
        }
        response = self.app.post('/chat',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["text"], "Reply to prompt")

        # Verify it was converted to an AgnoMessage list with user role
        called_args, called_kwargs = mock_agent_instance.run.call_args
        agno_messages = called_kwargs["input"]
        self.assertEqual(len(agno_messages), 1)
        self.assertEqual(agno_messages[0].role, "user")
        self.assertEqual(agno_messages[0].content, "describe python")

    @patch('agent_service.Agent')
    def test_chat_filters_historical_tool_outputs(self, mock_agent_class):
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Prepare history input messages
        msg_history = [
            {"role": "user", "content": "run: ls"},
            {"role": "tool", "content": '{"stdout": "file1.txt", "stderr": ""}'},
            {"role": "assistant", "content": "List of files: file1.txt"},
            {"role": "user", "content": "run: who"}
        ]

        # Convert to AgnoMessage list
        agno_history = [AgnoMessage(role=m["role"], content=m["content"]) for m in msg_history]

        # Setup mock return messages that contains all history AND the new run's messages
        mock_result = MagicMock()
        mock_result.content = "Command 'who' not allowed"
        mock_result.messages = [
            # Pre-existing messages (history)
            agno_history[0],
            agno_history[1],
            agno_history[2],
            agno_history[3],
            # Newly generated messages in this turn
            AgnoMessage(role="tool", content='{"error": "Command \'who\' not allowed", "stdout": "", "stderr": ""}'),
            AgnoMessage(role="assistant", content="Command 'who' not allowed")
        ]
        mock_agent_instance.run.return_value = mock_result

        # Post request
        payload = {
            "messages": msg_history
        }
        response = self.app.post('/chat',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # The response must ONLY contain the new tool outputs, not the old ones
        self.assertEqual(len(data["toolOutputs"]), 1)
        self.assertEqual(data["toolOutputs"][0]["error"], "Command 'who' not allowed")

if __name__ == '__main__':
    unittest.main()
