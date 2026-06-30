from dotenv import load_dotenv
from PIL import Image
from io import BytesIO
import requests
from .utils import pil_to_base64, LogMessage
from typing import List
from types import SimpleNamespace
import os
import json
import re

class MixtureGrounding:
    def __init__(self, 
        config: SimpleNamespace = None,
        logger = None
        ):
        self.config = config
        self.logger = logger

    def force_reset_logger(self, logger):
        self.logger = logger


    def phi_v_grounding(self,
        action_description: str = None,
        screenshot = None,
        azure_endpoint: bool = True,
        azure_url: str = None
        ) -> List:
        refined_coordinates = None

        messages = [('action_description', ('action_description.txt', action_description, 'text/plain'))]
        screenshot = Image.open(BytesIO(screenshot)).convert("RGB")
        curr_screenshot_base64 = pil_to_base64(screenshot)
        messages.append(('screenshot', ('screenshot.png', curr_screenshot_base64, 'image/png')))

        if azure_endpoint:
            headers = {}
            # Load environment variables from .env file
            load_dotenv()
            if os.getenv("PHI_V_GROUNDING_BEARER_KEY") is not None:
                key = os.getenv("PHI_V_GROUNDING_BEARER_KEY")
                headers = {"Authorization": f"Bearer {key}"}

            self.logger.info(LogMessage(
                message=f"Sending request to Phi-V-Grounding Azure endpoint: {azure_url}"
            ))
            response = requests.post(azure_url, files=messages, headers=headers)

            refined_coordinates = response.json()["coordinates"][0]
            self.logger.info(LogMessage(
                message=f"Refined coordinate: {refined_coordinates}"
            ))
        return refined_coordinates

    def uitars_v1_grounding(self,
        action_description: str = None,
        screenshot = None,
        azure_endpoint: bool = True,
        endpoint_url: str = None,
        bearer_key_env_var: str = None
        ) -> List:
        refined_coordinates = None
        user_prompt = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. \n\n## Output Format\n\nAction: ...\n\n\n## Action Space\nclick(start_box='<|box_start|>(x1,y1)<|box_end|>')\n\n## User Instruction\n{instruction}"""
        user_prompt = user_prompt.format(instruction=action_description)
        screenshot = Image.open(BytesIO(screenshot)).convert("RGB")
        curr_screenshot_base64 = pil_to_base64(screenshot)

        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_prompt}]
            },
            {
                "role": "user",
                "content": [{"type": "image", "image": curr_screenshot_base64}]
            }
        ]


        self.logger.info(LogMessage(
            type="mixture_grounding_prompt",
            message=f"User prompt for UITARS-V1-Grounding: {user_prompt}"
        ))

        if azure_endpoint:
            headers = {}
            # Load environment variables from .env file
            load_dotenv()
            key = None
            if os.getenv(bearer_key_env_var) is not None:
                key = os.getenv(bearer_key_env_var)
            headers = {"Authorization": f"Bearer {key}"}
            if key is None:
                raise ValueError(f"Bearer key not found in environment variable '{bearer_key_env_var}'. Need to set it before running the test.")
            self.logger.info(LogMessage(
                type="mixture_grounding_sending_request",
                message=f"Sending request to UITARS-V1-Grounding Azure endpoint: {endpoint_url}"
            ))
            response = requests.post(
                endpoint_url, 
                json=messages, 
                headers=headers
            )
        else:
            self.logger.info(LogMessage(
                type="mixture_grounding_sending_request",
                message=f"Sending request to UITARS-V1-Grounding local endpoint: {endpoint_url}"
            ))
            response = requests.post(
                endpoint_url, 
                json=messages, 
            )

        refined_action_str = response.json()["response"][0]
        match = re.search(r"start_box='\((\d+),(\d+)\)'", refined_action_str)

        refined_coordinates = [0, 0]
        if match:
            x, y = int(match.group(1)), int(match.group(2))

            refined_coordinates[0] = int(x) / 1000 * screenshot.width
            refined_coordinates[1] = int(y) / 1000 * screenshot.height

        self.logger.info(LogMessage(
            type="mixture_grounding_refined_coordinate",
            message=f"Refined coordinate: {refined_coordinates}"
        ))

        return refined_coordinates

    def _get_uia_elements(self):
        """Collect UIA control summaries from active window and taskbar.
        Returns (elements_text, controls_list) or (None, None) on failure.
        """
        try:
            from .utils._uia import DesktopHandler
            d = DesktopHandler()
            all_controls = []

            taskbar = d.get_taskbar()
            if taskbar:
                _, tb_controls = taskbar.get_control_summary2(max_text_length=80)
                all_controls.extend(tb_controls)

            active_window = d.get_active_window()
            if active_window:
                _, aw_controls = active_window.get_control_summary2(max_text_length=80)
                all_controls.extend(aw_controls)

            if not all_controls:
                return None, None

            lines = []
            for i, ctrl in enumerate(all_controls):
                text = ctrl.get("text", "").strip()
                cls = ctrl.get("class_name", "").strip()
                auto_id = ctrl.get("automation_id", "")
                desc = f"{text} - {cls}"
                if auto_id:
                    desc += f" [{auto_id}]"
                lines.append(f"{i}. {desc}")

            return "\n".join(lines), all_controls
        except Exception:
            return None, None

    def _keyword_match(self, action_description, controls):
        """Fast keyword match: find UIA control whose text best matches the action."""
        import difflib

        # Handle Argument objects from action.thought
        if hasattr(action_description, 'value'):
            action_description = action_description.value
        if not isinstance(action_description, str):
            action_description = str(action_description)

        targets = []
        # Priority 1: quoted strings
        for m in re.finditer(r"['\"]([^'\"]+)['\"]", action_description):
            targets.append((m.group(1).lower(), 2))

        # Priority 2: proper nouns / capitalized phrases (app names)
        for m in re.finditer(r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\b', action_description):
            phrase = m.group(1).strip().lower()
            stop = {'click', 'the', 'on', 'for', 'icon', 'button', 'windows', 'start',
                    'search', 'bar', 'type', 'open', 'launch', 'it', 'to', 'if', 'is',
                    'this', 'that', 'with', 'from', 'left', 'right', 'center', 'bottom',
                    'top', 'menu', 'and', 'or', 'in', 'at', 'by', 'of', 'do', 'not',
                    'are', 'you', 'can', 'will', 'be', 'has', 'have', 'was', 'a', 'an'}
            if phrase and phrase not in stop and len(phrase) > 1:
                targets.append((phrase, 1))

        # Priority 3: special UI elements not always in UIA
        if re.search(r'start\s*(menu|button)', action_description, re.I):
            targets.append(('start', 1))
        if re.search(r'search\s*(bar|box|field)', action_description, re.I):
            targets.append(('search', 1))

        if not targets:
            return None

        best_score = 0
        best_idx = None
        for i, ctrl in enumerate(controls):
            ctrl_text = (ctrl.get("text", "") + " " +
                         ctrl.get("class_name", "") + " " +
                         ctrl.get("automation_id", "")).lower()
            for target, weight in targets:
                if target in ctrl_text:
                    # Direct substring: higher score for shorter ctrl_text (more specific match)
                    ratio = len(target) / max(len(ctrl_text), 1)
                    score = weight * ratio + 0.5
                else:
                    score = difflib.SequenceMatcher(None, target, ctrl_text).ratio() * weight * 0.3
                if score > best_score:
                    best_score = score
                    best_idx = i

        if best_score >= 0.5 and best_idx is not None:
            rect = controls[best_idx]["rectangle"]
            x = rect["x"] + rect["width"] // 2
            y = rect["y"] + rect["height"] // 2
            return [int(x), int(y)]
        return None

    def uia_desktop_grounding(self,
        action_description: str = None,
        endpoint_url: str = None,
        model_name: str = "qwen2.5vl-vision",
        ) -> List:
        """UIA-based grounding: enumerate UI elements via Windows accessibility API,
        match the action description to the best element, return exact coordinates.

        Strategy: keyword match (instant, no LLM). Returns None if no match —
        caller should try visual grounding as fallback.
        """
        # Handle Argument objects from action.thought
        if hasattr(action_description, 'value'):
            action_description = action_description.value
        if not isinstance(action_description, str):
            action_description = str(action_description)

        elements_text, controls = self._get_uia_elements()
        if elements_text is None or not controls:
            return None

        coord = self._keyword_match(action_description, controls)
        return coord  # None signals caller to fall back to visual grounding

    def predict(self,
        action_description: str = None,
        observation = None
        ) -> List:
        refined_coordinates = None
        # Handle Argument objects from action.thought
        if hasattr(action_description, 'value'):
            action_description = action_description.value
        if not isinstance(action_description, str):
            action_description = str(action_description)

        for expert in self.config.expertises:
            if expert.model == "uia_desktop_grounding" and expert.weight > 0:
                refined_coordinates = self.uia_desktop_grounding(
                    action_description=action_description,
                    endpoint_url=getattr(expert, "endpoint_url", None),
                    model_name=getattr(expert, "model_name", "qwen2.5vl-vision"),
                )
                if refined_coordinates is not None:
                    if self.logger:
                        self.logger.info(LogMessage(
                            message=f"Refined coordinates from UIA-Desktop-Grounding: {refined_coordinates}"
                        ))
                    return refined_coordinates
            if expert.model == "uitars_v1_grounding" and expert.weight > 0:
                refined_coordinates = self.uitars_v1_grounding(
                    action_description=action_description,
                    screenshot=observation["screenshot"],
                    azure_endpoint=expert.azure_endpoint,
                    endpoint_url=expert.endpoint_url,
                    bearer_key_env_var=expert.bearer_key_env_var
                )
                if self.logger:
                    self.logger.info(LogMessage(
                        message=f"Refined coordinates from UITARS-V1-Grounding: {refined_coordinates}"
                    ))
            if expert.model == "ollama_grounding" and expert.weight > 0:
                refined_coordinates = self.ollama_grounding(
                    action_description=action_description,
                    screenshot=observation["screenshot"],
                    endpoint_url=getattr(expert, "endpoint_url", None),
                    model_name=getattr(expert, "model_name", "qwen2.5vl:7b"),
                )
                if self.logger:
                    self.logger.info(LogMessage(
                        message=f"Refined coordinates from Ollama-Grounding: {refined_coordinates}"
                    ))
        return refined_coordinates

    def ollama_grounding(self,
        action_description: str = None,
        screenshot = None,
        endpoint_url: str = None,
        model_name: str = "qwen2.5vl:7b",
        ) -> List:
        import base64 as b64_mod

        # Handle Argument objects from action.thought
        if hasattr(action_description, 'value'):
            action_description = action_description.value
        if not isinstance(action_description, str):
            action_description = str(action_description)

        prompt = (
            "You are a GUI grounding assistant. Look at the screenshot and find the "
            "pixel coordinates of the UI element described below.\n\n"
            f"Element to locate: {action_description}\n\n"
            "Return ONLY a JSON object with x and y pixel coordinates:\n"
            '{"x": <number>, "y": <number>}\n'
            "If the element is not visible, return your best estimate."
        )

        screenshot_img = Image.open(BytesIO(screenshot)).convert("RGB")
        buf = BytesIO()
        screenshot_img.save(buf, format="PNG")
        img_b64 = b64_mod.b64encode(buf.getvalue()).decode("utf-8")

        base_url = (endpoint_url or "http://localhost:11434").rstrip("/")

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        resp = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=300, proxies={"http": None, "https": None})
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from response — handle markdown code fences
        text = text.strip()
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
            if text.endswith("```"):
                text = text[:-3]
        text = text.strip()

        coord = json.loads(text)
        x = coord["x"]
        y = coord["y"]
        # Handle nested lists: if LLM returns [148, 50] instead of 148
        if isinstance(x, list):
            x = x[0]
        if isinstance(y, list):
            y = y[0]
        return [int(x), int(y)]


