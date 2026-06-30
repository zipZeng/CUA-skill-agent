import os
import sys
from typing import List, Dict
from types import SimpleNamespace
from .utils import Misc, SessionLogger, LogMessage, Status
from .action import BaseAction, BaseComposeAction
import time
from .mixture_grounding import MixtureGrounding
import warnings
from .planner import RAGPlanner
from .skill_matcher import match_instruction
import re
import pyautogui

warnings.filterwarnings("ignore")


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config_rag.json")


class CUARAGAgent:
    def __init__(self, config=CONFIG_PATH, logger=None):
        self.project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config = Misc.file_to_namespace(config)
        self.name = self.config.name
        
        self.mixture_grounding = MixtureGrounding(
            config=self.config.mixture_grounding
        )
        self.planner = RAGPlanner(self.config)
        self.logger = logger

    def set_logger_dir(self, explicit_log_dir):
        self.logger = SessionLogger(
            config=self.config.logger,
            remote_logger=None,
            explicit_log_dir=explicit_log_dir,
        )
        self.mixture_grounding.force_reset_logger(self.logger)
        self.planner.force_reset_logger(self.logger)

    def _ground_click_action(self, action, step_description=""):
        """Run UIA grounding for click-type actions. Uses the action's own
        thought as grounding target — composed actions encode meaningful
        descriptions (e.g. 'Click the Windows Start button')."""
        if hasattr(action, "call_grounding_model"):
            action_type = getattr(action, "type", "")
            if action_type in ("click", "double_click", "right_click",
                               "triple_click", "move_abs", "drag"):
                observation = self.env.get_observation()
                grounding_desc = step_description or getattr(action, "thought", "")
                if hasattr(grounding_desc, "value"):
                    grounding_desc = grounding_desc.value
                action.call_grounding_model(
                    grounding_expertise=self.mixture_grounding,
                    observation=observation,
                    action_description=str(grounding_desc),
                )

    def _execute_skill(self, skill_class, params: dict, cancel_event=None):
        """Execute a composed action (skill) — no LLM. Each click step
        gets UIA grounding for coordinates."""
        attempt_start_time = time.time()
        task_status = Status.IN_PROGRESS

        try:
            operation = skill_class(**{k: v for k, v in params.items()
                                      if hasattr(skill_class, k)})
        except Exception as e:
            self.logger.info(LogMessage(
                type="skill_instantiate_error",
                message=f"Failed to instantiate {skill_class.__name__}: {e}",
            ))
            return Status.FAILURE

        if hasattr(operation, "configure_from_env"):
            operation.configure_from_env(env=self.env)

        self.logger.info(LogMessage(
            type="skill_start",
            message=f"Executing skill: {skill_class.__name__} params={params}",
        ))

        step_count = 0
        max_substeps = getattr(self.config, "max_steps", 30)
        while True:
            if self.termination(task_status, cancel_event, attempt_start_time):
                return task_status
            step_count += 1
            if step_count > max_substeps:
                return Status.TIMEOUT

            action = operation.step(edge_name_pref="hotkey")
            if action is None:
                break

            self._ground_click_action(action)

            result = self.execute(actions=[action])
            time.sleep(self.config.step_interval_time)

            if result in (Status.SUCCESS, Status.FAILURE):
                return result

        return Status.SUCCESS

    def _execute_direct_fallback(self, instruction: str):
        """Fallback: run_direct.py-style patterns when no skill matches."""
        task = instruction
        self.logger.info(LogMessage(
            type="direct_fallback",
            message=f"No skill matched. Using direct patterns for: {task}",
        ))
        patterns = [
            (r"^open\s+(.+)", self._direct_open_app),
            (r"^打开\s*(.+)", self._direct_open_app),
            (r"^launch\s+(.+)", self._direct_open_app),
            (r"^search\s+(.+)", self._direct_search),
            (r"^搜索\s*(.+)", self._direct_search),
            (r"^notepad\s*(.*)", self._direct_notepad),
            (r"^记事本\s*(.*)", self._direct_notepad),
            (r"^calc\s*(.*)", self._direct_calc),
            (r"^计算器\s*(.*)", self._direct_calc),
        ]
        for pattern, handler in patterns:
            m = re.match(pattern, task, re.IGNORECASE)
            if m:
                return handler(m)
        self.logger.info(LogMessage(
            type="no_match",
            message=f"No direct pattern matched for: {task}",
        ))
        return Status.FAILURE

    def _direct_open_app(self, match):
        app = match.group(1).strip()
        self.logger.info(LogMessage(type="direct", message=f"Opening app: {app}"))
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write(app, interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        return Status.SUCCESS

    def _direct_search(self, match):
        query = match.group(1).strip()
        self.logger.info(LogMessage(type="direct", message=f"Searching: {query}"))
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write(query, interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        return Status.SUCCESS

    def _direct_notepad(self, match):
        text = match.group(1).strip()
        self.logger.info(LogMessage(type="direct", message="Opening Notepad"))
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write("notepad", interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1.0)
        if text:
            pyautogui.write(text, interval=0.05)
        return Status.SUCCESS

    def _direct_calc(self, match):
        expr = match.group(1).strip()
        self.logger.info(LogMessage(type="direct", message="Opening Calculator"))
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write("calculator", interval=0.05)
        time.sleep(0.5)
        pyautogui.press("enter")
        if expr:
            time.sleep(1.0)
            pyautogui.write(expr, interval=0.05)
            pyautogui.press("enter")
        return Status.SUCCESS

    def proceed(self, instruction, example, explicit_log_dir, env=None, cancel_event=None, **kwargs):
        # Set up the environment

        self.set_logger_dir(explicit_log_dir)
        
        if env is None:
            from .desktop_env import DesktopEnv

            self.env = DesktopEnv(
                name=self.config.env.name,
                platform=self.config.env.platform,
                url=self.config.env.url,
                screen_height=self.config.env.screen_height,
                screen_width=self.config.env.screen_width,
                observation_type=self.config.env.observation_type,
                observe_screenshot_in_bytes=self.config.env.observe_screenshot_in_bytes,
                logger=self.logger,
            )
        else:
            self.env = env

        self.reset()
        self.planner.set_instruction(instruction)
        self.logger.info(
            LogMessage(
                type="agent_start",
                message=f"Starting Agent: {self.name}",
                metadata={
                    "instruction": instruction,
                    "log_source_dir": str(self.logger.session_dir),
                },
            )
        )
        time.sleep(3)
        self.logger.info(
            LogMessage(
                type="wait for environment ready",
                message="Wait 3s for environment ready...",
            )
        )
        observation = self.env.get_observation()
        self.logger.info(
            LogMessage(
                    type="initial_screen",
                    message=f"",
                    metadata={
                        "initial_screen": observation,
                    },
                )
            )
        # screenshot = observation["screenshot"]
        # file_path = example["config"][0]["parameters"]["files"][0]["path"]
        # exec_action = self.planner.get_code_solution(screenshot, file_path)
        # # self.env.reset()
        # self.env.step(exec_action)
        # time.sleep(60)
        # return 



        # ---- Primary path: match instruction to a composed action (skill) ----
        self.logger.info(LogMessage(
            type="skill_matching",
            message=f"Matching instruction: '{instruction}'",
        ))
        match_result = match_instruction(instruction)

        if match_result is not None:
            skill_class, params = match_result
            self.logger.info(LogMessage(
                type="skill_matched",
                message=f"Matched: {skill_class.__name__} params={params}",
            ))
            result = self._execute_skill(skill_class, params, cancel_event)
            self.logger.info(LogMessage(
                type="skill_result",
                message=f"Skill execution result: {result}",
            ))
            return

        # ---- Fallback: direct patterns (no skill match) ----
        self.logger.info(LogMessage(
            type="fallback",
            message="No skill matched, trying direct patterns.",
        ))
        self._execute_direct_fallback(instruction)


    def termination(
        self, task_status: Status, cancel_event, attempt_start_time
    ) -> bool:
        if cancel_event is not None and cancel_event.is_set():
            task_status = Status.CANCELED
        if time.time() - attempt_start_time > self.config.max_wall_time:
            task_status = Status.TIMEOUT

        if task_status in [
            Status.SUCCESS,
            Status.FAILURE,
            Status.CANCELED,
            Status.TIMEOUT,
            Status.CALL_USER,
        ]:
            self.logger.info(
                LogMessage(type="agent_termination", message=f"Status: {task_status}")
            )
            return True
        return False

    def execute(self, actions: List[BaseAction] = None) -> Status:
        task_status = Status.IN_PROGRESS
        for action in actions:
            if action is None:
                continue
            if action.type == "dummy":
                continue

            if action.type == "finish":
                self.logger.info(
                    LogMessage(
                        type="task_end_status",
                        message=f"{self.name} [green]finish[/green] the task.",
                    )
                )
                task_status = Status.SUCCESS
                return task_status
            elif action.type == "fail":
                self.logger.info(
                    LogMessage(
                        type="task_end_status",
                        message=f"{self.name} [red]fail[/red] the task.",
                    )
                )
                task_status = Status.FAILURE
                return task_status
            elif action.type == "call_user":
                self.logger.info(
                    LogMessage(
                        type="task_end_status",
                        message=f"{self.name} [blue]call_user[/blue] the task.",
                    )
                )
                task_status = Status.CALL_USER
                return task_status
            elif action.type == "error_env":
                self.logger.info(
                    LogMessage(
                        type="task_end_status",
                        message=f"{self.name} [red]error_env[/red] during the task.",
                    )
                )
                task_status = Status.ENV_ERROR
                return task_status

            before_observation = self.env.get_observation()

            executable_action_code = action.get_gui_code()

            # optional - getting debug image
            # warpped_text = Misc.wrap_text_lines(executable_action, 40)
            # debug_before_image = Misc.get_commands_debug_image(before_observation["screenshot"], commands_debug_info=[], text=warpped_text)

            # actual action execution
            self.env.step(executable_action_code)

            after_observation = self.env.get_observation()

            self.logger.info(
                LogMessage(
                    type=str(action.type),
                    message=f"Before/After action observation and {action} executed",
                    metadata={
                        "before_observation": before_observation,
                        # "before_observation_debug": debug_before_image,
                        "after_observation": after_observation,
                        "action": str(action),
                        "executable_action": executable_action_code,
                    },
                )
            )
        return task_status

    def reset(self, wait_time: int = 1):
        if self.logger:
            self.logger.info(
            LogMessage(
                type="agent_reset",
                message=f"Performing Agent Reset",
            )
        )
        else:
            print("Performing Agent Reset")
        time.sleep(wait_time)
