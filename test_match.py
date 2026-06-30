"""
Test skill_matcher in isolation — no desktop interaction, no LLM.
Usage: python test_match.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.skill_matcher import match_instruction

cases = [
    # (instruction, expected_class_name)
    ("open Word", "WordLaunch"),
    ("open notepad", "NotepadLaunch"),
    ("open excel", "ExcelLaunch"),
    ("open powerpoint", "PowerPointLaunch"),
    ("open edge", "MicrosoftEdgeLaunch"),
    ("open chrome", "ChromeLaunch"),
    ("open calculator", "CalculatorLaunch"),
    ("open vlc", "VLCOpenMediaFile"),
    ("打开 notepad", "NotepadLaunch"),
    ("打开记事本", "NotepadLaunch"),
    ("打开计算器", "CalculatorLaunch"),
    # close: WordExitApp doesn't exist, only NotepadExitApp does
    ("close notepad", "NotepadExitApp"),
    ("关闭记事本", "NotepadExitApp"),
    # type/input: TypeText only for Notepad; Word uses InsertText
    ("type hello in notepad", "NotepadTypeText"),
    ("输入 test in word", "WordInsertText"),
    # save: SaveFile only for Notepad; others use Save
    ("save file in notepad", "NotepadSaveFile"),
    ("save document in word", "WordSave"),
    # save as: no domain has SaveAsFile, only SaveAs
    ("save as document in word", "WordSaveAs"),
    ("保存为 report in excel", "ExcelSaveAs"),
    # zoom: only Notepad/Chrome/Edge have ZoomIn/ZoomOut
    ("zoom in notepad", "NotepadZoomIn"),
    ("zoom out chrome", "ChromeZoomOut"),
    # search
    ("search python in chrome", "ChromeSearchWeb"),
    # find and replace
    ("find hello and replace with world in notepad", "NotepadFindReplaceAll"),
    # copy: FileExplorer only
    ("copy item in file explorer", "FileExplorerCopyItem"),
    # prefixed: "帮我"/"请" should be stripped
    ("帮我打开word", "WordLaunch"),
    ("请打开notepad", "NotepadLaunch"),
    ("麻烦打开计算器", "CalculatorLaunch"),
    # unknown app: should return NO MATCH → fallback handles it
    ("打开typora", "NO MATCH"),
    ("帮我打开typora", "NO MATCH"),
]

print("=" * 70)
print(f"{'Instruction':40s} {'Expected':25s} {'Got':25s} {'OK'}")
print("=" * 70)

passed = 0
failed = 0
for instr, expected in cases:
    r = match_instruction(instr)
    got = r[0].__name__ if r else "NO MATCH"
    ok = "PASS" if got == expected else "FAIL"
    if got == expected:
        passed += 1
    else:
        failed += 1
    print(f"{instr:40s} {expected:25s} {got:25s} {ok}")

print("=" * 70)
print(f"Passed: {passed}/{passed+failed}, Failed: {failed}")
