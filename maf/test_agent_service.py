import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import asyncio

# Set up path so we can import from maf/agent_service and shared/config_loader
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import agent_service
from agent_framework import Message
from agent_framework._types import Content, AgentResponse

class TestAgentService(unittest.TestCase):

    def setUp(self):
        # Reset caches before each test
        agent_service._agent_cache = None
        agent_service._last_config = None
        agent_service._session_cache = {}

    def test_get_session_id(self):
        """Test that get_session_id returns deterministic SHA-256 hashes."""
        messages = [{"role": "user", "content": "Hello world"}]
        session_id1 = agent_service.get_session_id(messages)
        session_id2 = agent_service.get_session_id(messages)
        self.assertEqual(session_id1, session_id2)
        self.assertIsInstance(session_id1, str)
        self.assertEqual(len(session_id1), 64) # SHA-256 has 64 hex characters

    @patch("agent_service.load_config")
    def test_get_agent_and_sessions(self, mock_load_config):
        """Test persistent agent and session retrieval."""
        mock_load_config.return_value = {
            "baseURL": "http://mock-url/v1",
            "apiKey": "mock-key",
            "model": "gpt-4o",
            "allowList": ["ls"],
            "allowAll": False
        }

        # Retrieve agent first time
        agent1 = agent_service.get_agent()
        self.assertIsNotNone(agent1)

        # Retrieve agent second time (should be cached)
        agent2 = agent_service.get_agent()
        self.assertIs(agent1, agent2)

        # Retrieve session
        session_id = "test_session"
        session1 = agent_service.get_session(agent1, session_id)
        self.assertIsNotNone(session1)
        self.assertEqual(session1.session_id, session_id)

        session2 = agent_service.get_session(agent1, session_id)
        self.assertIs(session1, session2)

    @patch("agent_service.load_config")
    @patch("agent_framework.openai.OpenAIChatClient")
    def test_run_agent_integration(self, mock_client_class, mock_load_config):
        """Test full native run_agent execution with mocked run loop and tool result extraction."""
        mock_load_config.return_value = {
            "baseURL": "http://mock-url/v1",
            "apiKey": "mock-key",
            "model": "gpt-4o",
            "allowList": ["ls"],
            "allowAll": False
        }

        # Mock Agent.run to return a mock AgentResponse
        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Hello! Here is the list of files."

        # Create mock message with tool output content
        ci = Content.from_function_result(call_id='call_123', result='{"stdout": "file1.txt\\nfile2.txt", "stderr": "", "error": null}')
        msg = Message(role='tool', contents=[ci])
        mock_response.to_dict.return_value = {
            "type": "agent_response",
            "messages": [msg.to_dict()],
            "response_id": "run_123"
        }

        async def dummy_run(*args, **kwargs):
            return mock_response

        # Get agent and patch its run method
        agent = agent_service.get_agent()
        agent.run = AsyncMock(side_effect=dummy_run)

        # Execute run_agent asynchronously
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
            {"role": "user", "content": "List files"}
        ]

        result = asyncio.run(agent_service.run_agent(messages))

        # Check that result has extracted the tool outputs correctly using public properties and dicts
        self.assertIn("toolOutputs", result)
        self.assertEqual(len(result["toolOutputs"]), 1)
        self.assertEqual(result["toolOutputs"][0]["stdout"], "file1.txt\nfile2.txt")
        self.assertEqual(result["text"], "")  # Suppressed because tool output is present

if __name__ == "__main__":
    unittest.main()
