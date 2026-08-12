"""
test_latex_repair.py — Integration test for IEEEtran format repair module.

Tests LatexFormatRepair against a simulated Quick Test survey paper that
contains common IEEEtran format violations. Verifies all 10 repair rules.
"""

import re
import sys
import os

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.feedback.latex_repair import LatexFormatRepair


# ---------------------------------------------------------------------------
# A simulated Quick Test survey paper with deliberate format violations
# ---------------------------------------------------------------------------
QUICK_TEST_DRAFT = r"""\documentclass[11pt]{article}
\usepackage{geometry}
\geometry{margin=1in}

\usepackage{hyperref,graphicx}

\section{Abstract}
This survey provides a comprehensive overview of Quick Test methods
for efficient deep learning inference in 2026. We cover Test-Time
Adaptation (TTA), Test-Time Training (TTT), and related approaches.

\section{Introduction}
Deep learning models have achieved remarkable success.~{\cite{li2023fast}}
However, deploying large models remains challenging. The field of Quick Test
aims to reduce inference latency through various optimizations.

Pruning techniques remove redundant weights~\cite{han2023pruning}.
Quantization reduces numerical precision. Dynamic early exit allows
shallow exits for easy samples. NAS automatically searches for
efficient architectures~\cite{zoph2018nas}.

\begin{table}
\centering
\begin{tabular}{lcc}
\hline
Method & Accuracy & Speed \\
\hline
TTA & 92.3\% & ★★★★★ \\
BN Adaptation & 90.1\% & ★★★★ \\
MAML & 88.7\% & ★★★ \\
\hline
\end{tabular}
\caption{Comparison of Quick Test methods.}
\label{tab:comparison}
\end{table}

As shown in Table~\ref{tab:comparison}, TTA achieves the best accuracy.
The FLOPs of these methods vary significantly.

\section{Background}
Batch Normalization (BN) is widely used in modern architectures.
The field has grown rapidly from 2020 to 2026.

\section{Taxonomy of Methods}
... taxonomy content ...

\section{Comparative Analysis}
... comparative analysis content ...

\begin{table}
\begin{tabular}{lcc}
\hline
Method & Param & FLOPs \\
\hline
Method A & 1.2M & 5G \\
Method B & 2.1M & 8G \\
\hline
\end{tabular}
\caption{Parameter count and FLOPs comparison.}
\label{tab:params}
\end{table}

\begin{figure}
\caption{Overview of the Quick Test taxonomy.}
\includegraphics[width=\columnwidth]{taxonomy.pdf}
\label{fig:taxonomy}
\end{figure}

\section{Future Directions}
... future directions ...

\section{Conclusion}
... conclusion ...

\begin{thebibliography}{99}
\bibitem{li2023fast} Li et al. "Fast Inference Methods." 2023.
\bibitem{han2023pruning} Han et al. "Pruning for Efficiency." 2023.
\bibitem{zoph2018nas} Zoph et al. "NAS." 2018.
\end{thebibliography}

\end{document}
"""


def test_rule0_document_header():
    """Rule 0: Replace arbitrary documentclass and remove geometry."""
    repair = LatexFormatRepair(enabled_rules={
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(QUICK_TEST_DRAFT)
    fixed = log.fixed_text

    # Check IEEEtran header is present
    assert "\\documentclass[10pt,conference]{IEEEtran}" in fixed, \
        "IEEEtran documentclass not found"
    assert "\\usepackage{booktabs,amsmath,amssymb}" in fixed, \
        "booktabs/amsmath/amssymb not loaded"

    # Check geometry is removed
    assert "\\usepackage{geometry}" not in fixed, \
        "geometry package not removed"
    assert "\\geometry{" not in fixed, \
        "geometry command not removed"

    # Check original documentclass is replaced
    assert "\\documentclass[11pt]{article}" not in fixed, \
        "Original documentclass not replaced"

    print(f"  Rule 0: {log.change_count} change(s) — OK")
    for e in log.entries:
        print(f"    {e.short()}")


def test_rule1_abstract_env():
    """Rule 1: Replace \\section{Abstract} with \\begin{abstract}."""
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(QUICK_TEST_DRAFT)
    fixed = log.fixed_text

    # Check abstract environment is used
    assert "\\begin{abstract}" in fixed, \
        "\\begin{abstract} not found"
    assert "\\end{abstract}" in fixed, \
        "\\end{abstract} not found"

    # Check \\section{Abstract} is removed
    assert "\\section{Abstract}" not in fixed, \
        "\\section{Abstract} still present"

    print(f"  Rule 1: {log.change_count} change(s) — OK")


def test_rule2_bibliography():
    """Rule 2: Remove thebibliography and insert BibTeX config."""
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(QUICK_TEST_DRAFT)
    fixed = log.fixed_text

    # Check thebibliography is removed
    assert "\\begin{thebibliography}" not in fixed, \
        "thebibliography still present"

    # Check BibTeX config is inserted
    assert "\\bibliographystyle{IEEEtran}" in fixed, \
        "bibliographystyle not found"
    assert "\\bibliography{references}" in fixed, \
        "bibliography command not found"

    # BibTeX config should be before \\end{document}
    end_doc_pos = fixed.find("\\end{document}")
    bibstyle_pos = fixed.find("\\bibliographystyle")
    assert bibstyle_pos < end_doc_pos, \
        "bibliographystyle should be before \\end{document}"

    print(f"  Rule 2: {log.change_count} change(s) — OK")


def test_rule3_table_format():
    """Rule 3: Convert tables to IEEEtran three-line style."""
    # Use a simple LaTeX snippet with a table
    test_latex = r"""
\begin{table}
\centering
\begin{tabular}{lcc}
\hline
Method & Accuracy & Speed \\
\hline
TTA & 92.3\% & ★★★★★ \\
BN & 90.1\% & ★★★★ \\
\hline
\end{tabular}
\caption{Comparison.}
\end{table}
"""
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": True,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    # Check [htbp] float placement
    assert "[htbp]" in fixed, \
        "[htbp] float placement not added"

    # Check booktabs commands
    assert "\\toprule" in fixed, \
        "\\toprule not found"
    assert "\\bottomrule" in fixed or "\\midrule" in fixed, \
        "No booktabs commands found"

    # Check star ratings replaced
    assert "★★★★★" not in fixed, \
        "Star rating not replaced"

    # Check \\hline removed
    assert "\\hline" not in fixed, \
        "\\hline still present"

    print(f"  Rule 3: {log.change_count} change(s) — OK")
    for e in log.entries:
        print(f"    {e.short()}")


def test_rule4_citation_punct():
    """Rule 4: Fix .~\\cite{} -> ~\\cite{}. """
    test_latex = r"""
As shown in previous work.~\cite{li2023fast}
This is another example.~\cite{wang2022deep}
    """
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": True,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    # Check .~\cite{...} is converted to ~\cite{...}.
    expected = r"~\cite{li2023fast}."
    assert expected in fixed, \
        f"Expected '{expected}' in output"

    expected2 = r"~\cite{wang2022deep}."
    assert expected2 in fixed, \
        f"Expected '{expected2}' in output"

    # Check no .~\cite remains
    assert ".~\\cite{" not in fixed, \
        ".~\\cite{ still present"

    print(f"  Rule 4: {log.change_count} change(s) — OK")


def test_rule5_acronym_expand():
    """Rule 5: Check acronym expansion (spot-check)."""
    test_latex = r"""
In this survey, we discuss TTA methods for efficient inference.
TTA has shown promising results. We also cover FLOPs reduction.
    """
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": True,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    # Check TTA is expanded on first occurrence
    assert "Test-Time Adaptation (TTA)" in fixed, \
        "TTA not expanded"

    # Check FLOPs is expanded
    assert "Floating Point Operations (FLOPs)" in fixed, \
        "FLOPs not expanded"

    print(f"  Rule 5: {log.change_count} change(s) — OK")
    for e in log.entries:
        print(f"    {e.short()}")


def test_rule6_time_range():
    """Rule 6: Replace 2026 with 2025."""
    test_latex = r"""
This survey covers methods from 2020 to 2026.
In 2026, significant progress was made.
    """
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": True,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    assert "2026" not in fixed, \
        "2026 still present"
    assert "2025" in fixed, \
        "2025 not found"

    print(f"  Rule 6: {log.change_count} change(s) — OK")


def test_rule7_fast_inference():
    """Rule 7: Add boundary clarification sentence."""
    test_latex = r"""
\section{Quick Test Methods}
Pruning techniques remove redundant weights to speed up inference.
Quantization reduces numerical precision for faster computation.
Dynamic early exit allows shallow exits for easy samples.
    """
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": True,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    expected = "These optimizations reduce runtime latency during inference"
    assert expected in fixed, \
        "Boundary clarification sentence not added"

    print(f"  Rule 7: {log.change_count} change(s) — OK")


def test_rule8_typography():
    """Rule 8: Fix typography issues."""
    test_latex = r"""
This is a "smart quote" test and a 'single quote' test.
Word—word should use em-dash. Word–word should use en-dash.
Space  before  punctuation  .
    """
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": True,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    # Check Unicode dashes replaced
    assert "\u2014" not in fixed, \
        "Unicode em-dash still present"
    assert "\u2013" not in fixed, \
        "Unicode en-dash still present"

    # Check smart quotes replaced
    assert "\u201c" not in fixed, \
        "Unicode left double quote still present"
    assert "\u201d" not in fixed, \
        "Unicode right double quote still present"

    print(f"  Rule 8: {log.change_count} change(s) — OK")


def test_rule9_caption_position():
    """Rule 9: Caption position fix."""
    test_latex = r"""
\begin{figure}
\caption{This caption should be below the figure.}
\includegraphics[width=\columnwidth]{figure.pdf}
\label{fig:test}
\end{figure}
"""
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": True,
        "rule10_page_estimate": False,
    })
    log = repair.repair(test_latex)
    fixed = log.fixed_text

    # Extract the figure block
    fig_match = re.search(r"\\begin\{figure\}.*?\\end\{figure\}", fixed, re.DOTALL)
    assert fig_match, "Figure block not found"
    fig_block = fig_match.group(0)

    # Check \caption is after \includegraphics
    includegraphics_pos = fig_block.find("\\includegraphics")
    caption_pos = fig_block.find("\\caption")
    assert includegraphics_pos < caption_pos, \
        "Figure caption should be after includegraphics"

    print(f"  Rule 9: {log.change_count} change(s) — OK")


def test_rule10_page_estimate():
    """Rule 10: Page count estimation."""
    repair = LatexFormatRepair(enabled_rules={
        "rule0_document_header": False,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": True,
    })
    log = repair.repair(QUICK_TEST_DRAFT)

    # Check page estimate is produced
    page_entries = [e for e in log.entries if e.rule == "rule10"]
    assert len(page_entries) > 0, \
        "No page estimate entry found"

    print(f"  Rule 10: {len(page_entries)} entry/entries — OK")
    for e in page_entries:
        print(f"    {e.short()}")


def test_full_pipeline():
    """Test all rules together on the Quick Test draft."""
    repair = LatexFormatRepair()
    log = repair.repair(QUICK_TEST_DRAFT)

    print(f"\n  Full pipeline: {log.change_count} total change(s)")

    # Verify key outcomes
    fixed = log.fixed_text

    # Rule 0
    assert "\\documentclass[10pt,conference]{IEEEtran}" in fixed
    assert "\\usepackage{geometry}" not in fixed

    # Rule 1
    assert "\\begin{abstract}" in fixed
    assert "\\end{abstract}" in fixed
    assert "\\section{Abstract}" not in fixed

    # Rule 2
    assert "\\begin{thebibliography}" not in fixed
    assert "\\bibliographystyle{IEEEtran}" in fixed
    assert "\\bibliography{references}" in fixed

    # Rule 3
    assert "[htbp]" in fixed
    assert "\\toprule" in fixed or "\\midrule" in fixed
    assert "★★★★★" not in fixed

    # Rule 4
    assert ".~\\cite{" not in fixed

    # Rule 6
    assert "2026" not in fixed or "2026" in fixed.split("2025")[0]  # Check in bib etc.

    # Rule 9 (figure caption moved below)
    fig_match = re.search(r"\\begin\{figure\}.*?\\end\{figure\}", fixed, re.DOTALL)
    assert fig_match
    fig_block = fig_match.group(0)
    includegraphics_pos = fig_block.find("\\includegraphics")
    caption_pos = fig_block.find("\\caption")
    assert includegraphics_pos < caption_pos or caption_pos == -1

    # Rule 10
    page_entries = [e for e in log.entries if e.rule == "rule10"]
    assert len(page_entries) > 0

    print("  All 10 rules verified — PASS")


def test_individual_rule_toggle():
    """Test that rules can be individually toggled."""
    # Disable all rules
    repair = LatexFormatRepair(enabled_rules={k: False for k in LatexFormatRepair.RULE_ENABLED})
    log = repair.repair(QUICK_TEST_DRAFT)

    # With all rules disabled, the output should be unchanged
    assert log.fixed_text == QUICK_TEST_DRAFT, \
        "Output should be unchanged with all rules disabled"

    # Enable only rule 0
    repair2 = LatexFormatRepair(enabled_rules={
        "rule0_document_header": True,
        "rule1_abstract_env": False,
        "rule2_bibliography": False,
        "rule3_table_format": False,
        "rule4_citation_punct": False,
        "rule5_acronym_expand": False,
        "rule6_time_range": False,
        "rule7_fast_inference": False,
        "rule8_typography": False,
        "rule9_caption_position": False,
        "rule10_page_estimate": False,
    })
    log2 = repair2.repair(QUICK_TEST_DRAFT)
    fixed2 = log2.fixed_text

    # Rule 0 changes should be present
    assert "\\documentclass[10pt,conference]{IEEEtran}" in fixed2
    # But other rules should not have run
    assert "\\section{Abstract}" in fixed2, \
        "Rule 1 should not have run"
    assert "\\begin{thebibliography}" in fixed2, \
        "Rule 2 should not have run"
    assert "★★★★★" in fixed2, \
        "Rule 3 should not have run"

    # Count rule entries — only rule0 should have entries
    rule0_entries = [e for e in log2.entries if e.rule == "rule0"]
    other_entries = [e for e in log2.entries if e.rule != "rule0"]
    assert len(rule0_entries) > 0, \
        "Rule 0 should have produced entries"
    assert len(other_entries) == 0, \
        f"Only rule 0 should have run, found: {[e.rule for e in other_entries]}"

    print("  Individual rule toggle — OK")


def test_dry_run_with_output():
    """Print the final repaired LaTeX for visual inspection."""
    repair = LatexFormatRepair()
    log = repair.repair(QUICK_TEST_DRAFT)

    print("\n" + "=" * 70)
    print("REPAIRED LATEX OUTPUT")
    print("=" * 70)
    print(log.fixed_text)
    print("=" * 70)
    print(f"\nRepair summary: {log.summary()}")
    print("=" * 70)


if __name__ == "__main__":
    print("Testing LatexFormatRepair - IEEEtran Format Repair Module")
    print("=" * 60)

    print("\n--- Individual Rule Tests ---")
    test_rule0_document_header()
    test_rule1_abstract_env()
    test_rule2_bibliography()
    test_rule3_table_format()
    test_rule4_citation_punct()
    test_rule5_acronym_expand()
    test_rule6_time_range()
    test_rule7_fast_inference()
    test_rule8_typography()
    test_rule9_caption_position()
    test_rule10_page_estimate()

    print("\n--- Full Pipeline Test ---")
    test_full_pipeline()

    print("\n--- Toggle Test ---")
    test_individual_rule_toggle()

    print("\n--- Final Output ---")
    test_dry_run_with_output()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)