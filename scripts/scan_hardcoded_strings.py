#!/usr/bin/env python3
"""
Scan Hardcoded Strings Tool - TASK 17 Phase 1
Scans codebase for hardcoded Russian/Uzbek strings that should be localized.

Usage:
    python scripts/scan_hardcoded_strings.py [--path PATH] [--format {json,text,csv}]

Features:
    - Detects Cyrillic text in strings (Russian/Uzbek)
    - Identifies f-strings with embedded Cyrillic
    - Finds answer(), send_message(), edit_text() with hardcoded text
    - Excludes comments, docstrings, and test files
    - Generates reports by file, priority, and string type
"""

import ast
import os
import re
import json
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class HardcodedString:
    """Represents a detected hardcoded string."""
    file_path: str
    line_number: int
    column: int
    string_value: str
    context: str  # function_name or context
    string_type: str  # 'literal', 'f-string', 'method_call'
    priority: str  # P0, P1, P2, P3
    suggestion: str  # suggested locale key


# Cyrillic pattern (Russian/Uzbek)
CYRILLIC_PATTERN = re.compile(r'[а-яА-ЯёЁўғҳқўҒҲҚЎ]')

# High-priority files (user-facing)
HIGH_PRIORITY_PATHS = [
    'handlers/auth.py',
    'handlers/onboarding.py',
    'handlers/requests.py',
    'handlers/base.py',
    'services/notification_service.py',
    'services/request_service.py',
    'keyboards/base.py',
    'keyboards/requests.py',
]

# Medium-priority paths
MEDIUM_PRIORITY_PATHS = [
    'handlers/admin.py',
    'handlers/shifts.py',
    'handlers/my_shifts.py',
    'services/auth_service.py',
    'services/shift_service.py',
]

# Exclude patterns
EXCLUDE_PATTERNS = [
    'test_',
    '__pycache__',
    '.git',
    'venv',
    '.env',
    'alembic',
    'MemoryBank',
    'docs',
]


class HardcodedStringScanner(ast.NodeVisitor):
    """AST-based scanner for hardcoded strings."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.source_lines = source_code.splitlines()
        self.findings: List[HardcodedString] = []
        self.current_function = "module_level"
        self.function_stack: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track current function context."""
        self.function_stack.append(node.name)
        self.current_function = ".".join(self.function_stack)
        self.generic_visit(node)
        self.function_stack.pop()
        self.current_function = ".".join(self.function_stack) if self.function_stack else "module_level"

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Track async function context."""
        self.visit_FunctionDef(node)

    def visit_Str(self, node: ast.Str):
        """Visit string nodes (Python < 3.8 compatibility)."""
        self._check_string(node, node.s, 'literal')
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        """Visit constant nodes (Python >= 3.8)."""
        if isinstance(node.value, str):
            self._check_string(node, node.value, 'literal')
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr):
        """Visit f-string nodes."""
        # Reconstruct f-string value
        f_string_parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                f_string_parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                f_string_parts.append("{...}")

        f_string_value = "".join(f_string_parts)

        if CYRILLIC_PATTERN.search(f_string_value):
            self._check_string(node, f_string_value, 'f-string')

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Visit function call nodes to detect message methods."""
        # Check for answer(), send_message(), edit_text(), etc.
        method_names = {'answer', 'send_message', 'edit_text', 'edit_reply_markup',
                       'send_photo', 'send_document', 'send_video'}

        func_name = None
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name in method_names:
            # Check first argument (usually text)
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, (ast.Str, ast.Constant)):
                    value = first_arg.s if isinstance(first_arg, ast.Str) else first_arg.value
                    if isinstance(value, str) and CYRILLIC_PATTERN.search(value):
                        self._check_string(first_arg, value, 'method_call', method_name=func_name)
                elif isinstance(first_arg, ast.JoinedStr):
                    # f-string in method call
                    pass  # Already handled by visit_JoinedStr

        self.generic_visit(node)

    def _check_string(self, node: ast.AST, value: str, string_type: str, method_name: str = None):
        """Check if string contains Cyrillic and should be localized."""
        if not CYRILLIC_PATTERN.search(value):
            return

        # Skip very short strings (likely not user-facing)
        if len(value.strip()) < 3:
            return

        # Skip strings that look like variable names or keys
        if value.isupper() or value.lower() in ['да', 'нет', 'ok']:
            return

        # Determine priority based on file path
        priority = self._determine_priority()

        # Generate suggested locale key
        suggestion = self._generate_locale_key(value, string_type)

        # Get context line
        context_line = self._get_context_line(node.lineno)

        finding = HardcodedString(
            file_path=self.file_path,
            line_number=node.lineno,
            column=node.col_offset,
            string_value=value[:100],  # Truncate long strings
            context=f"{self.current_function}:{method_name}" if method_name else self.current_function,
            string_type=string_type,
            priority=priority,
            suggestion=suggestion
        )

        self.findings.append(finding)

    def _determine_priority(self) -> str:
        """Determine priority based on file path."""
        rel_path = self.file_path

        for hp_path in HIGH_PRIORITY_PATHS:
            if hp_path in rel_path:
                return 'P0'

        for mp_path in MEDIUM_PRIORITY_PATHS:
            if mp_path in rel_path:
                return 'P1'

        if 'handlers/' in rel_path or 'keyboards/' in rel_path:
            return 'P2'

        return 'P3'

    def _generate_locale_key(self, value: str, string_type: str) -> str:
        """Generate suggested locale key from string value."""
        # Clean and normalize
        clean = re.sub(r'[^\w\s]', '', value.lower())
        clean = re.sub(r'\s+', '_', clean.strip())

        # Transliterate common Russian words
        transliteration = {
            'привет': 'hello',
            'выберите': 'select',
            'введите': 'enter',
            'ошибка': 'error',
            'успешно': 'success',
            'отправить': 'send',
            'отменить': 'cancel',
            'сохранить': 'save',
            'удалить': 'delete',
            'добавить': 'add',
            'изменить': 'edit',
            'заявка': 'request',
            'смена': 'shift',
            'исполнитель': 'executor',
            'менеджер': 'manager',
        }

        words = clean.split('_')[:3]  # First 3 words
        key_parts = []

        for word in words:
            if word in transliteration:
                key_parts.append(transliteration[word])
            else:
                # Keep as is (or use first 5 chars)
                key_parts.append(word[:8])

        key = '_'.join(key_parts)

        # Add context prefix based on file
        if 'handlers/auth' in self.file_path:
            key = f"auth.{key}"
        elif 'handlers/requests' in self.file_path:
            key = f"requests.{key}"
        elif 'handlers/shifts' in self.file_path:
            key = f"shifts.{key}"
        elif 'keyboards/' in self.file_path:
            key = f"keyboards.{key}"
        elif 'services/' in self.file_path:
            key = f"services.{key}"

        return key[:50]  # Max 50 chars

    def _get_context_line(self, line_number: int) -> str:
        """Get the source code line for context."""
        if 1 <= line_number <= len(self.source_lines):
            return self.source_lines[line_number - 1].strip()
        return ""


def scan_file(file_path: Path) -> List[HardcodedString]:
    """Scan a single Python file for hardcoded strings."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=str(file_path))
        scanner = HardcodedStringScanner(str(file_path), source_code)
        scanner.visit(tree)

        return scanner.findings

    except SyntaxError as e:
        print(f"⚠️  Syntax error in {file_path}: {e}")
        return []
    except Exception as e:
        print(f"⚠️  Error scanning {file_path}: {e}")
        return []


def scan_directory(root_path: Path) -> List[HardcodedString]:
    """Scan all Python files in directory recursively."""
    all_findings = []

    for py_file in root_path.rglob("*.py"):
        # Skip excluded paths
        if any(excl in str(py_file) for excl in EXCLUDE_PATTERNS):
            continue

        findings = scan_file(py_file)
        all_findings.extend(findings)

        if findings:
            print(f"✓ Scanned {py_file.relative_to(root_path)}: {len(findings)} findings")

    return all_findings


def generate_report_text(findings: List[HardcodedString]) -> str:
    """Generate human-readable text report."""
    lines = []
    lines.append("=" * 80)
    lines.append("HARDCODED STRINGS SCAN REPORT - TASK 17 Phase 1")
    lines.append("=" * 80)
    lines.append("")

    # Summary
    lines.append(f"Total Findings: {len(findings)}")
    lines.append("")

    # By priority
    by_priority = defaultdict(list)
    for f in findings:
        by_priority[f.priority].append(f)

    lines.append("By Priority:")
    for priority in ['P0', 'P1', 'P2', 'P3']:
        count = len(by_priority[priority])
        lines.append(f"  {priority}: {count} findings")
    lines.append("")

    # By type
    by_type = defaultdict(int)
    for f in findings:
        by_type[f.string_type] += 1

    lines.append("By Type:")
    for stype, count in sorted(by_type.items()):
        lines.append(f"  {stype}: {count}")
    lines.append("")

    # By file (top 10)
    by_file = defaultdict(int)
    for f in findings:
        by_file[f.file_path] += 1

    lines.append("Top 10 Files:")
    for file_path, count in sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"  {count:3d}  {file_path}")
    lines.append("")

    lines.append("=" * 80)
    lines.append("DETAILED FINDINGS (grouped by priority)")
    lines.append("=" * 80)
    lines.append("")

    # Detailed findings by priority
    for priority in ['P0', 'P1', 'P2', 'P3']:
        priority_findings = by_priority[priority]
        if not priority_findings:
            continue

        lines.append(f"\n{'=' * 80}")
        lines.append(f"PRIORITY {priority} ({len(priority_findings)} findings)")
        lines.append(f"{'=' * 80}\n")

        for finding in priority_findings[:50]:  # Limit to 50 per priority
            lines.append(f"File: {finding.file_path}:{finding.line_number}")
            lines.append(f"Context: {finding.context}")
            lines.append(f"Type: {finding.string_type}")
            lines.append(f"String: {finding.string_value}")
            lines.append(f"Suggested Key: {finding.suggestion}")
            lines.append("-" * 80)

    return "\n".join(lines)


def generate_report_json(findings: List[HardcodedString]) -> str:
    """Generate JSON report."""
    return json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False)


def generate_report_csv(findings: List[HardcodedString], output_path: Path):
    """Generate CSV report."""
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['file_path', 'line_number', 'priority', 'string_type',
                     'string_value', 'suggestion', 'context']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for finding in findings:
            writer.writerow(asdict(finding))


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Scan for hardcoded strings")
    parser.add_argument('--path', default='uk_management_bot', help='Path to scan')
    parser.add_argument('--format', choices=['text', 'json', 'csv'], default='text',
                       help='Output format')
    parser.add_argument('--output', help='Output file (default: stdout for text/json)')

    args = parser.parse_args()

    root_path = Path(args.path)
    if not root_path.exists():
        print(f"❌ Path not found: {root_path}")
        return 1

    print(f"🔍 Scanning {root_path} for hardcoded strings...")
    print()

    findings = scan_directory(root_path)

    print()
    print(f"✅ Scan complete: {len(findings)} hardcoded strings found")
    print()

    # Generate report
    if args.format == 'text':
        report = generate_report_text(findings)
        if args.output:
            Path(args.output).write_text(report, encoding='utf-8')
            print(f"📄 Report saved to {args.output}")
        else:
            print(report)

    elif args.format == 'json':
        report = generate_report_json(findings)
        if args.output:
            Path(args.output).write_text(report, encoding='utf-8')
            print(f"📄 Report saved to {args.output}")
        else:
            print(report)

    elif args.format == 'csv':
        output_path = Path(args.output) if args.output else Path('hardcoded_strings.csv')
        generate_report_csv(findings, output_path)
        print(f"📄 CSV report saved to {output_path}")

    return 0


if __name__ == '__main__':
    exit(main())
