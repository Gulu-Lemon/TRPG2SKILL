"""
输入解析器 — 将世界书原文按标题/空行切分为段落
"""
import re
from typing import OrderedDict


def parse_input(filepath: str) -> OrderedDict[str, str]:
    """
    将输入文本按结构切分为段落字典。
    
    分节策略 (优先级递减):
      1. Markdown 标题: ## / ### / #
      2. 中文标题: 第X章 / 第X节 / §X / 【X】
      3. 分隔线: 连续 ≥3 个等号/短横/星号
      4. 空行: 至少 3 个连续空行
      5. 回退: 整文件作为单个 section
    
    Returns:
        有序字典 {section_name: section_text}
    """
    text = _read_file(filepath)
    sections = OrderedDict()
    
    if not text.strip():
        sections["全文"] = text
        return sections
    
    # 寻找标题行
    lines = text.split("\n")
    boundaries = [0]  # section 起始行号
    titles = ["头"]
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        if _is_header(stripped):
            boundaries.append(i)
            titles.append(_clean_title(stripped))
    
    boundaries.append(len(lines))
    
    # 如果只找到很少的标题（≤1），尝试用连续空行切分
    if len(boundaries) <= 2:
        boundaries, titles = _split_by_blank_lines(lines)
    
    # 如果没有合理的分界，整文件作为一个 section
    if len(boundaries) <= 2 or _check_overlap(boundaries):
        sections["全文"] = text
        return sections
    
    # 切分
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        section_lines = lines[start:end]
        section_text = "\n".join(section_lines).strip()
        title = titles[idx] if idx < len(titles) else f"段落{idx}"
        
        if section_text:
            # 去重标题（多个 section 可能有相同标题）
            unique_title = _unique_title(title, sections)
            sections[unique_title] = section_text
    
    return sections


def _read_file(filepath: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法读取文件: {filepath}")


def _is_header(line: str) -> bool:
    """判断一行是否为标题"""
    line = line.strip()
    if not line:
        return False
    
    # Markdown headers
    if re.match(r'^#{1,6}\s', line):
        return True
    
    # Chinese chapter headers
    if re.match(r'^第[一二三四五六七八九十\d]+[章节幕部]', line):
        return True
    
    # Section symbol
    if re.match(r'^§\d+', line):
        return True
    
    # Bracketed headers
    if re.match(r'^【.+】$', line) or re.match(r'^［.+］$', line):
        return True
    
    # Numbered lists as headers: "1. 世界观" or "第一部分"
    if re.match(r'^\d+[\.、）\)]\s*\S', line):
        return True
    if re.match(r'^第[一二三四五六七八九十\d]+部分', line):
        return True
    
    return False


def _clean_title(line: str) -> str:
    """清理标题文本，移除 markdown 标记"""
    line = re.sub(r'^#{1,6}\s*', '', line.strip())
    # 截断过长的标题
    if len(line) > 50:
        line = line[:50] + "…"
    return line.strip()


def _split_by_blank_lines(lines: list[str]) -> tuple[list[int], list[str]]:
    """用连续空行（≥3个）切分"""
    boundaries = [0]
    titles = ["头"]
    blank_count = 0
    
    for i, line in enumerate(lines):
        if not line.strip():
            blank_count += 1
        else:
            if blank_count >= 3 and boundaries[-1] != i:
                boundaries.append(i)
                # 用下一段的前 20 字作为标题
                next_text = line.strip()[:20]
                titles.append(next_text if next_text else f"段落{len(titles)}")
            blank_count = 0
    
    boundaries.append(len(lines))
    return boundaries, titles


def _check_overlap(boundaries: list[int]) -> bool:
    """检查分段是否合理（段数不应过多）"""
    return len(boundaries) > 50


def _unique_title(title: str, existing: OrderedDict) -> str:
    """确保标题不重复"""
    if title not in existing:
        return title
    i = 2
    while f"{title} ({i})" in existing:
        i += 1
    return f"{title} ({i})"
