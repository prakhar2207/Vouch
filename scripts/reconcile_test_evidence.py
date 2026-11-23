#!/usr/bin/env python3
"""
scripts/reconcile_test_evidence.py

Deterministic AST-Driven Test Evidence Extraction & Reconciliation Generator
SriLekh GST — Round 2.5.15 Independent Rule 37A Re-Certification

Capabilities:
1. Discovers every TestCase class and test method directly from Python AST.
2. Extracts source lines, full method names, and docstrings.
3. Parses verbose Django test runner output (-v 2).
4. Matches AST-discovered tests with executed tests.
5. Validates 1-to-1 parity (no unmatched, no duplicates, no unexecuted tests).
6. Deterministically generates machine-readable Markdown tables.
"""

import ast
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


class TestASTDiscovery:
    """Extracts test metadata directly from Python file AST."""

    def __init__(self, file_path: str):
        self.file_path = os.path.abspath(file_path)
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Test source file not found: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.source = f.read()

        self.tree = ast.parse(self.source, filename=self.file_path)

    def discover_tests(self) -> List[Dict[str, any]]:
        discovered = []

        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                # Only check TestCase classes or test classes
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                        docstring = ast.get_docstring(item) or ""
                        doc_first_line = docstring.strip().split('\n')[0].strip() if docstring else ""

                        # Extract or generate test ID
                        test_id_match = re.search(r'(R2591\d-\d+)', item.name)
                        if not test_id_match and doc_first_line:
                            test_id_match = re.search(r'(R2591\d-\d+)', doc_first_line)

                        if test_id_match:
                            test_id = test_id_match.group(1)
                        else:
                            test_id = item.name.upper()

                        discovered.append({
                            'file_path': self.file_path,
                            'class_name': class_name,
                            'method_name': item.name,
                            'line_number': item.lineno,
                            'docstring': doc_first_line,
                            'test_id': test_id,
                        })

        # Sort by line number for deterministic file ordering
        discovered.sort(key=lambda x: x['line_number'])
        return discovered


class TestRunnerParser:
    """Parses verbose output from Django test runner (-v 2)."""

    def __init__(self, output_text: str):
        self.output_text = output_text

    @classmethod
    def from_file(cls, log_path: str) -> "TestRunnerParser":
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return cls(content)

    def parse_results(self) -> Dict[str, Dict[str, str]]:
        """
        Parses test results into a mapping of method_name -> {status, class_name, docstring, raw_line}.
        Django verbose runner output patterns:
        test_method (app.module.Class.test_method) ... ok
        test_method (app.module.Class.test_method)
        Docstring line ... ok
        """
        results = {}
        lines = self.output_text.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Match: test_method (full.module.ClassName.test_method)
            m = re.match(r'^(test_\w+)\s*\(([^)]+)\)(.*)$', line)
            if m:
                method_name = m.group(1)
                full_qual_class = m.group(2)
                trailing = m.group(3).strip()

                # Extract class name from module path
                class_parts = full_qual_class.split('.')
                # Could be module.Class.method or module.Class
                if len(class_parts) >= 2 and class_parts[-1] == method_name:
                    class_name = class_parts[-2]
                else:
                    class_name = class_parts[-1]

                status = None
                docstring = ""

                # Check if status is on the same line (e.g. "... ok")
                status_match = re.search(r'\.\.\.\s*(ok|FAIL|ERROR|skipped)', trailing)
                if status_match:
                    status = status_match.group(1)
                else:
                    # Look ahead to next line for docstring and status
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        next_status = re.search(r'\.\.\.\s*(ok|FAIL|ERROR|skipped)', next_line)
                        if next_status:
                            status = next_status.group(1)
                            # Docstring is before ...
                            docstring = next_line[:next_status.start()].strip()
                            i += 1

                if status:
                    status_normalized = 'PASS' if status == 'ok' else ('FAIL' if status == 'FAIL' else ('ERROR' if status == 'ERROR' else 'SKIPPED'))
                    results[method_name] = {
                        'method_name': method_name,
                        'class_name': class_name,
                        'status': status_normalized,
                        'docstring': docstring,
                        'raw_execution': f"{line} -> {status_normalized}"
                    }
            i += 1

        return results


def reconcile_and_generate_markdown(
    test_file_path: str,
    runner_output_text: str,
    log_reference: str,
    title: str = "Test Execution Results"
) -> Tuple[str, Dict[str, any]]:
    """
    Reconciles discovered AST tests with runner output and generates Markdown table.
    """
    ast_discovery = TestASTDiscovery(test_file_path)
    discovered = ast_discovery.discover_tests()

    runner_parser = TestRunnerParser(runner_output_text)
    executed = runner_parser.parse_results()

    total_discovered = len(discovered)
    total_executed = len(executed)

    rows = []
    matched_count = 0
    passed_count = 0
    failed_count = 0
    error_count = 0
    skipped_count = 0
    unmatched_ast = []

    for item in discovered:
        m_name = item['method_name']
        c_name = item['class_name']
        t_id = item['test_id']
        line_no = item['line_number']
        desc = item['docstring'] or m_name

        if m_name in executed:
            exec_info = executed[m_name]
            exec_status = exec_info['status']
            matched_count += 1
            if exec_status == 'PASS':
                passed_count += 1
            elif exec_status == 'FAIL':
                failed_count += 1
            elif exec_status == 'ERROR':
                error_count += 1
            elif exec_status == 'SKIPPED':
                skipped_count += 1
        else:
            exec_status = 'NOT_EXECUTED'
            unmatched_ast.append(m_name)

        rows.append({
            'test_id': t_id,
            'class_name': c_name,
            'method_name': m_name,
            'source_line': line_no,
            'description': desc,
            'status': exec_status,
            'evidence': log_reference
        })

    unexpected_executed = [k for k in executed if not any(d['method_name'] == k for d in discovered)]

    stats = {
        'total_discovered': total_discovered,
        'total_executed': total_executed,
        'matched_count': matched_count,
        'passed_count': passed_count,
        'failed_count': failed_count,
        'error_count': error_count,
        'skipped_count': skipped_count,
        'unmatched_ast': unmatched_ast,
        'unexpected_executed': unexpected_executed,
        'is_perfect_match': (total_discovered == total_executed == matched_count == passed_count) and len(unexpected_executed) == 0
    }

    # Generate Markdown Table
    md = []
    md.append(f"# {title}\n")
    md.append("## 1. Summary Statistics\n")
    md.append(f"- **Source File:** `{os.path.basename(test_file_path)}`")
    md.append(f"- **AST Discovered Tests:** `{total_discovered}`")
    md.append(f"- **Runner Executed Tests:** `{total_executed}`")
    md.append(f"- **Matched Verbatim Tests:** `{matched_count}`")
    md.append(f"- **Passed Tests:** `{passed_count}`")
    md.append(f"- **Failed Tests:** `{failed_count}`")
    md.append(f"- **Errors:** `{error_count}`")
    md.append(f"- **Skipped Tests:** `{skipped_count}`")
    md.append(f"- **Log Reference:** `{log_reference}`")
    md.append(f"- **Test-to-Report Reconciliation Parity:** `{'100% VERIFIED' if stats['is_perfect_match'] else 'PARITY FAILURE'}`\n")

    if unmatched_ast:
        md.append(f"### Unmatched Discovered Tests ({len(unmatched_ast)}):")
        for u in unmatched_ast:
            md.append(f"- `{u}`")
        md.append("")

    if unexpected_executed:
        md.append(f"### Unexpected Executed Tests ({len(unexpected_executed)}):")
        for u in unexpected_executed:
            md.append(f"- `{u}`")
        md.append("")

    md.append("## 2. Deterministic Test Results Table\n")
    md.append("| Test ID | Test Class | Method Name | Source Line | Test Description | Execution Status | Execution Evidence |")
    md.append("|:---|:---|:---|:---:|:---|:---:|:---|")

    for r in rows:
        status_badge = f"**{r['status']}**" if r['status'] == 'PASS' else f"<span style='color:red;'>{r['status']}</span>"
        desc_clean = r['description'].replace('|', '-').replace('\n', ' ')
        md.append(f"| `{r['test_id']}` | `{r['class_name']}` | `{r['method_name']}` | L{r['source_line']} | {desc_clean} | {status_badge} | `{r['evidence']}` |")

    md.append("\n---\n*Generated automatically by `scripts/reconcile_test_evidence.py` via Python AST & Django verbose test runner output.*")

    return "\n".join(md), stats


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python scripts/reconcile_test_evidence.py <test_source_file> <runner_output_file> [log_reference] [output_md_file]")
        sys.exit(1)

    test_src = sys.argv[1]
    runner_out = sys.argv[2]
    log_ref = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(runner_out)
    out_md = sys.argv[4] if len(sys.argv) > 4 else None

    with open(runner_out, 'r', encoding='utf-8') as f:
        runner_text = f.read()

    md_content, stats = reconcile_and_generate_markdown(test_src, runner_text, log_ref)
    print("Reconciliation Stats:", stats)

    if out_md:
        with open(out_md, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Report written to: {out_md}")
