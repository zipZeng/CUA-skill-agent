"""
Skill Matcher — maps natural language instructions to composed actions.
No LLM: domain detection → verb-keyword match → fallback to direct execution.
"""
import re
from typing import Dict, List, Tuple, Optional, Type

from .action.base_action import BaseAction, _OP_REGISTRY
from .action.compose_action import BaseComposeAction
from .action.argument import Argument


# --- Domain hints → class prefix ---
DOMAIN_MAP = {
    'notepad': 'Notepad', '记事本': 'Notepad',
    'word': 'Word',
    'excel': 'Excel',
    'powerpoint': 'PowerPoint', 'ppt': 'PowerPoint',
    'calculator': 'Calculator', '计算器': 'Calculator',
    'edge': 'MicrosoftEdge',
    'chrome': 'Chrome',
    'vlc': 'VLC',
    'file explorer': 'FileExplorer', '资源管理器': 'FileExplorer',
    'settings': 'WindowsSettings', '设置': 'WindowsSettings',
    'bing': 'BingSearch',
    'youtube': 'Youtube',
    'vs code': 'VSCode', 'vscode': 'VSCode',
    'clock': 'Clock', '时钟': 'Clock',
    'amazon': 'Amazon',
    'paint': 'Paint',
}

# Verb synonyms: instruction verb → description word boost
VERB_SYNONYMS = {
    'open': ['launch', 'start', 'run', 'open', '打开'],
    '打开': ['launch', 'start', 'run', 'open', '打开'],
    'launch': ['launch', 'start', 'run', 'open'],
    'close': ['close', 'exit', 'quit', '关闭'],
    '关闭': ['close', 'exit', 'quit', '关闭'],
    'type': ['type', 'write', 'enter', '输入'],
    '输入': ['type', 'write', 'enter', '输入'],
    'search': ['search', 'query', '查找', '搜索'],
    '搜索': ['search', 'query', '查找', '搜索'],
    'find': ['find', 'search', '查找'],
    '查找': ['find', 'search', '查找'],
    'replace': ['replace', '替换'],
    '替换': ['replace', '替换'],
    'save': ['save', 'store', '保存'],
    '保存': ['save', 'store', '保存'],
    'print': ['print', '打印'],
    '打印': ['print', '打印'],
    'create': ['create', 'new', '新建', '创建'],
    '创建': ['create', 'new', '新建', '创建'],
    'new': ['new', 'create', '新建', '创建'],
    '新建': ['new', 'create', '新建', '创建'],
    'zoom': ['zoom'],
    'copy': ['copy', '复制'],
    '复制': ['copy', '复制'],
    'delete': ['delete', 'remove', '删除'],
    '删除': ['delete', 'remove', '删除'],
}


def _detect_domain(instruction: str) -> Optional[str]:
    instr_lower = instruction.lower()
    for dkw, prefix in sorted(DOMAIN_MAP.items(), key=lambda x: -len(x[0])):
        if dkw in instr_lower:
            return prefix
    return None


class SkillMatcher:
    def __init__(self):
        self.skill_registry: Dict[str, dict] = {}
        self._collect_skills()

    def _collect_skills(self):
        for name, cls in _OP_REGISTRY.items():
            if not issubclass(cls, BaseComposeAction):
                continue
            if not hasattr(cls, 'descriptions') or not cls.descriptions:
                continue
            params = {}
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name)
                if isinstance(attr, Argument):
                    params[attr_name] = {
                        'default': attr.value,
                        'frozen': getattr(attr, '_frozen', False),
                    }
            self.skill_registry[name] = {
                'class': cls,
                'descriptions': cls.descriptions,
                'params': params,
                'type': getattr(cls, 'type', name),
            }

    def get_skill_names(self) -> List[str]:
        return list(self.skill_registry.keys())

    def _fast_match(self, instr_lower: str) -> Optional[Tuple]:
        """Hardcoded rules for the most common instruction patterns."""
        domain = _detect_domain(instr_lower)

        # "open X" / "打开 X" / "launch X" → XLaunch
        m = re.match(r'(?:open|launch|启动|运行)\s+(.+)', instr_lower, re.I)
        if not m:
            m = re.match(r'(打开)\s*(.+)', instr_lower)  # Chinese: optional space
        if m:
            app = m.group(1).strip().split()[0]  # first word after verb
            for prefix, name in [
                ('word', 'WordLaunch'), ('notepad', 'NotepadLaunch'),
                ('记事本', 'NotepadLaunch'), ('calculator', 'CalculatorLaunch'),
                ('计算器', 'CalculatorLaunch'), ('edge', 'MicrosoftEdgeLaunch'),
                ('chrome', 'ChromeLaunch'), ('excel', 'ExcelLaunch'),
                ('powerpoint', 'PowerPointLaunch'), ('ppt', 'PowerPointLaunch'),
                ('vlc', 'VLCOpenMediaFile'), ('clock', 'ClockOpenApp'),
            ]:
                if app.lower() == prefix.lower() and name in self.skill_registry:
                    info = self.skill_registry[name]
                    return info['class'], self._extract_params(
                        instr_lower, info['params'], info['descriptions'])
            # Generic: find any Launch skill matching the app name
            for name, info in self.skill_registry.items():
                if name.endswith('Launch') and app.lower() in name.lower():
                    return info['class'], self._extract_params(
                        instr_lower, info['params'], info['descriptions'])

        # "type X in Y" / "输入 X in Y" → YTypeText / YInsertText
        m = re.match(r'(?:type|write)\s+(.+)', instr_lower, re.I)
        if not m:
            m = re.match(r'(输入)\s*(.+)', instr_lower)  # Chinese: optional space
        if m and domain:
            rest = m.group(1).strip()
            # Extract text up to "in" keyword
            text = rest.split(' in ')[0].split(' 在 ')[0].strip() if ' in ' in rest or ' 在 ' in rest else rest
            for name in [f'{domain}TypeText', f'{domain}InsertText']:
                if name in self.skill_registry:
                    info = self.skill_registry[name]
                    params = self._extract_params(instr_lower, info['params'],
                                                  info['descriptions'])
                    params['text'] = text
                    return info['class'], params

        # "close X" / "关闭 X" → XExitApp
        m = re.match(r'(?:close|exit|quit)\s+(.+)', instr_lower, re.I)
        if not m:
            m = re.match(r'(关闭)\s*(.+)', instr_lower)  # Chinese: optional space
        if m and domain:
            for name in [f'{domain}ExitApp', f'{domain}CloseWindow']:
                if name in self.skill_registry:
                    info = self.skill_registry[name]
                    return info['class'], self._extract_params(
                        instr_lower, info['params'], info['descriptions'])

        # "save X" → XSaveFile (no "as")
        if re.match(r'(?:save|保存)\s+', instr_lower, re.I):
            if ' as ' not in instr_lower and '保存为' not in instr_lower:
                if domain:
                    for name in [f'{domain}SaveFile', f'{domain}Save']:
                        if name in self.skill_registry:
                            info = self.skill_registry[name]
                            return info['class'], self._extract_params(
                                instr_lower, info['params'], info['descriptions'])

        # "save as X" → XSaveAsFile
        if ' as ' in instr_lower or '保存为' in instr_lower:
            if domain:
                for name in [f'{domain}SaveAsFile', f'{domain}SaveAs']:
                    if name in self.skill_registry:
                        info = self.skill_registry[name]
                        return info['class'], self._extract_params(
                            instr_lower, info['params'], info['descriptions'])

        # "zoom in" / "zoom out" → XZoomIn / XZoomOut
        m = re.match(r'(?:zoom|放大|缩小)\s+(in|out)', instr_lower, re.I)
        if m and domain:
            direction = m.group(1).lower()
            zoom_name = f'{domain}Zoom{direction.capitalize()}'
            if zoom_name in self.skill_registry:
                info = self.skill_registry[zoom_name]
                params = self._extract_params(instr_lower, info['params'],
                                              info['descriptions'])
                if direction == 'in':
                    params['times'] = 1
                return info['class'], params

        return None

    @staticmethod
    def _strip_prefix(instr: str) -> str:
        """Strip Chinese polite prefixes like 帮我/请/麻烦/能不能/可以/给我."""
        prefixes = [
            '请帮我', '可以帮我', '能帮我', '麻烦你',
            '帮我', '请', '麻烦', '能不能', '可以', '可否', '能否', '给我',
            'please', 'can you', 'could you', 'would you',
        ]
        for p in sorted(prefixes, key=len, reverse=True):
            if instr.startswith(p):
                return instr[len(p):].lstrip()
        return instr

    def match(self, instruction: str) -> Optional[Tuple[Type[BaseComposeAction], Dict[str, str]]]:
        instr_lower = instruction.lower()
        instr_cleaned = self._strip_prefix(instr_lower)

        # ---- Fast path: hardcoded patterns for common instructions ----
        fast = self._fast_match(instr_cleaned)
        if fast:
            return fast

        domain = _detect_domain(instruction)

        # ---- Step 1: only search within detected domain ----
        if domain:
            candidates = {n: i for n, i in self.skill_registry.items()
                          if n.startswith(domain)}
        else:
            # No domain hint: search all skills
            candidates = self.skill_registry

        # ---- Step 2: extract action and target from instruction ----
        actions, targets = self._parse_instruction(instr_cleaned)
        # Expand actions with synonyms
        all_actions = set(actions)
        for a in actions:
            if a in VERB_SYNONYMS:
                all_actions.update(VERB_SYNONYMS[a])

        # ---- Step 3: match action to skill descriptions within candidates ----
        best_score = 0.0
        best_name = None

        for name, info in candidates.items():
            score = 0.0
            has_launch = 'Launch' in name
            has_open_menu = 'OpenMenu' in name

            for desc in info['descriptions']:
                desc_clean = re.sub(r'\$\{\{\w+\}\}', '', desc.lower()).strip()
                # Synonym-expanded action matching
                for a in all_actions:
                    if re.search(r'\b' + re.escape(a) + r'\b', desc_clean):
                        score += 3.0
                # Target word match
                for t in targets:
                    if re.search(r'\b' + re.escape(t) + r'\b', desc_clean):
                        score += 1.5
                # Exact skeleton match
                if desc_clean and desc_clean in instr_cleaned:
                    score += 2.0

            # Context adjustment: "open X" with no file mention → prefer Launch
            if any(a in {'open', '打开', 'launch', 'launch', 'run'}
                   for a in actions) and not any(
                       t in {'file', 'document', 'folder', '文件', '文档'}
                       for t in targets):
                if has_launch:
                    score += 3.0  # boost Launch actions
                if has_open_menu:
                    score -= 3.0  # demote OpenMenu actions

            # "zoom in" → prefer ZoomIn over ZoomReset
            if 'in' in targets and 'Zoom' in name and 'In' in name:
                score += 3.0
            if 'out' in targets and 'Zoom' in name and 'Out' in name:
                score += 3.0

            # "save X" without "as" → prefer SaveFile over SaveAsFile
            if any(a in {'save', '保存'} for a in actions):
                if 'as' not in instr_cleaned and 'SaveAs' in name:
                    score -= 3.0
                if 'as' in instr_cleaned and 'SaveAs' in name:
                    score += 3.0

            # "search X" without settings/history keywords → prefer SearchWeb
            if any(a in {'search', '搜索'} for a in actions):
                if not any(t in {'setting', 'settings', 'history', '历史', '设置'}
                           for t in targets):
                    if 'SearchWeb' in name:
                        score += 3.0
                    if 'SearchSettings' in name or 'SearchHistory' in name:
                        score -= 3.0

            if score > best_score:
                best_score = score
                best_name = name

        if best_score < 2.0:
            return None

        # When no domain hint, require at least one target word to actually
        # appear in the winning skill's descriptions — prevents "打开typora"
        # from randomly matching PowerPointLaunch.
        skill_info = candidates[best_name]
        if not domain and targets:
            target_hit = False
            for desc in skill_info['descriptions']:
                desc_lower = desc.lower()
                for t in targets:
                    if re.search(r'\b' + re.escape(t) + r'\b', desc_lower):
                        target_hit = True
                        break
                if target_hit:
                    break
            if not target_hit:
                return None

        params = self._extract_params(instr_cleaned, skill_info['params'],
                                      skill_info['descriptions'])
        return skill_info['class'], params

    def _parse_instruction(self, instr_lower: str) -> Tuple[List[str], List[str]]:
        """Split instruction into action words and target words."""
        # Known action verbs (ordered by priority)
        action_verbs = [
            'replace', 'find', 'search', 'type', 'write',
            'close', 'exit', 'quit',
            'save', 'print', 'zoom',
            'create', 'new', 'add', 'insert',
            'copy', 'cut', 'paste', 'delete', 'rename',
            'move', 'select', 'open', 'launch', 'start', 'run',
            '打开', '搜索', '关闭', '保存', '打印', '替换',
            '查找', '创建', '新建', '复制', '粘贴', '删除',
            '输入',
        ]

        action = []
        target_words = []
        remaining = instr_lower

        for verb in action_verbs:
            if verb in remaining:
                action.append(verb)

        # Target = non-action, non-stop words
        stop = {'on', 'with', 'to', 'at', 'for', 'from', 'the',
                'a', 'an', 'of', 'by', 'me', 'my', 'please', 'now',
                '帮', '我', '的', '一下', '一个', '然后', '使用'}
        all_words = re.findall(r'\w+|[一-鿿]+', instr_lower)
        for w in all_words:
            if w not in stop and w not in action:
                # Also exclude domain hint words
                if w not in DOMAIN_MAP:
                    target_words.append(w)

        return action, target_words

    def _extract_params(self, instr_lower: str, params: dict,
                        descriptions: List[str]) -> Dict[str, str]:
        extracted = {}
        for param_name, param_info in params.items():
            default = param_info['default']
            # frozen params are set in the class definition — skip to avoid
            # MRO conflicts when multiple parent classes define the same param
            if param_info.get('frozen'):
                continue
            val = self._find_param(instr_lower, param_name)
            if val and val != param_name:
                extracted[param_name] = val
            else:
                extracted[param_name] = default
        return extracted

    def _find_param(self, instr_lower: str, param_name: str) -> Optional[str]:
        # Get text after first action verb
        action_verbs = ['open', '打开', 'launch', '启动', 'type', 'write',
                        '输入', 'search', '搜索', 'find', '查找', 'replace',
                        '替换', 'save', '保存', 'close', '关闭', 'print',
                        '打印', 'create', '创建', 'new', '新建', 'zoom', 'copy',
                        '复制', 'delete', '删除', 'move', '移动', 'run', '运行']

        tail = instr_lower
        for verb in action_verbs:
            if verb in instr_lower:
                tail = instr_lower.split(verb, 1)[-1].strip()
                break

        # --- application_name ---
        if param_name == 'application_name':
            words = []
            for w in tail.split():
                if w in ('in', 'on', 'with', 'to', 'at', 'for', 'using', '在', '使用'):
                    break
                words.append(w)
                if len(words) >= 2:
                    break
            return ' '.join(words) if words else None

        # --- text ---
        if param_name == 'text':
            # text up to "in", "to", "on"
            words = []
            for w in tail.split():
                if w in ('in', 'on', 'to', 'with', 'into', 'at', 'for', 'from',
                         'using', '在', '到', '用', '给', '使用'):
                    break
                words.append(w)
            return ' '.join(words) if words else None

        # --- query ---
        if param_name == 'query':
            tail = tail.lstrip('for ').lstrip('查询 ').strip()
            return tail or None

        # --- file_name / filename ---
        if param_name in ('file_name', 'filename'):
            for sep in [' as ', ' to ']:
                if sep in instr_lower:
                    return instr_lower.split(sep, 1)[-1].strip().split()[0]
            return None

        # --- find_what ---
        if param_name == 'find_what':
            for sep in ['find ', '查找 ']:
                if sep in instr_lower:
                    after = instr_lower.split(sep, 1)[-1]
                    for end in [' with ', ' to ', ' in ', ' replace ', '替换为',
                                '替换 ', ' 在', ' 替换']:
                        if end in after:
                            return after.split(end)[0].strip()
                    return after.strip()
            return None

        # --- replace_with ---
        if param_name == 'replace_with':
            for sep in [' with ', '替换为', '替换成', ' to ']:
                if sep in instr_lower:
                    after = instr_lower.split(sep, 1)[-1]
                    for end in [' in ', ' 在']:
                        if end in after:
                            return after.split(end)[0].strip()
                    return after.strip().split()[0]
            return None

        # --- path ---
        if param_name == 'path':
            m = re.search(r'([a-zA-Z]:[\\/][^\s]+)', instr_lower)
            if m:
                return m.group(1)
            for folder_kw in ['desktop', 'documents', 'downloads', '桌面', '文档', '下载']:
                if folder_kw in instr_lower:
                    return f'C:\\Users\\Default\\{folder_kw.capitalize()}'
            return None

        return None


_skill_matcher = None


def get_skill_matcher() -> SkillMatcher:
    global _skill_matcher
    if _skill_matcher is None:
        _skill_matcher = SkillMatcher()
    return _skill_matcher


def match_instruction(instruction: str) -> Optional[Tuple]:
    return get_skill_matcher().match(instruction)
