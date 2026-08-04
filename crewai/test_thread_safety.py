import unittest
from unittest.mock import patch, MagicMock
import json
import threading
import time
import sys
import os

# Add parent and current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_service import app, _captured_tool_outputs, BashTool

class TestCrewAIThreadSafety(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('agent_service.Crew')
    @patch('agent_service.load_chatlets_config')
    def test_concurrent_requests_thread_isolation(self, mock_load_config, mock_crew_class):
        # Configure load_config mock
        mock_load_config.return_value = {
            "allowList": ["ls", "pwd"],
            "allowAll": False,
            "model": "gpt-4",
            "baseURL": "http://localhost:8080/v1",
            "apiKey": "example"
        }

        # Shared list to store outputs from different threads
        thread_results = {}
        barrier = threading.Barrier(2)

        def mock_kickoff_1():
            # Thread 1: Wait for both threads to reach here, then execute tool
            barrier.wait()
            # Execute "ls"
            BashTool()._run("ls")
            # Simulate some processing delay to let Thread 2 execute
            time.sleep(0.1)
            # Create a mock result object
            res = MagicMock()
            res.output = "thread 1 result"
            return res

        def mock_kickoff_2():
            # Thread 2: Wait for both threads to reach here, then execute tool
            barrier.wait()
            # Execute "pwd"
            BashTool()._run("pwd")
            # Create a mock result object
            res = MagicMock()
            res.output = "thread 2 result"
            return res

        # We will use side_effect to return different responses based on the thread
        def kickoff_side_effect(*args, **kwargs):
            thread_name = threading.current_thread().name
            if "thread_1" in thread_name:
                return mock_kickoff_1()
            else:
                return mock_kickoff_2()

        # Configure mock Crew instance kickoff method
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.side_effect = kickoff_side_effect
        mock_crew_class.return_value = mock_crew_instance

        def client_request(thread_id, command):
            threading.current_thread().name = f"thread_{thread_id}"
            response = self.app.post('/chat', json={
                "messages": [{"role": "user", "content": f"run {command}"}]
            })
            data = json.loads(response.data)
            thread_results[thread_id] = data

        # Spawn concurrent requests
        t1 = threading.Thread(target=client_request, args=(1, "ls"))
        t2 = threading.Thread(target=client_request, args=(2, "pwd"))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Verify thread 1 results
        self.assertIn(1, thread_results)
        self.assertIn("toolOutputs", thread_results[1])
        tool_outputs_1 = thread_results[1]["toolOutputs"]

        # Thread 1 should only have the result of "ls" command
        self.assertEqual(len(tool_outputs_1), 1)
        self.assertIsNone(tool_outputs_1[0].get("error"))
        # Since ls was executed, we can see if it has stdout (non-empty)
        self.assertIn("stdout", tool_outputs_1[0])

        # Verify thread 2 results
        self.assertIn(2, thread_results)
        self.assertIn("toolOutputs", thread_results[2])
        tool_outputs_2 = thread_results[2]["toolOutputs"]

        # Thread 2 should only have the result of "pwd" command
        self.assertEqual(len(tool_outputs_2), 1)
        self.assertIsNone(tool_outputs_2[0].get("error"))
        self.assertIn("stdout", tool_outputs_2[0])

        # Verify that thread 1's stdout contains the current directory files,
        # while thread 2's stdout contains the current working directory path.
        # This confirms that they ran different commands and kept their results isolated!
        cwd_output = tool_outputs_2[0]["stdout"]
        ls_output = tool_outputs_1[0]["stdout"]
        self.assertNotEqual(cwd_output, ls_output)

        print("Thread safety test passed successfully!")

if __name__ == '__main__':
    unittest.main()
