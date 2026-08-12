"""
latex_repair.py — IEEEtran Format Repair Module

Post-processing module that repairs LaTeX output from the LLM to strictly
conform to IEEEtran conference submission format. Follows the "system prompt
pre-constraint + Python regex post-processing" dual-layer repair architecture.

All repair functions are independently togglable and execute in a fixed order.
Each modification is logged for debugging and traceability.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repair log entry
# ---------------------------------------------------------------------------
@dataclass
class RepairEntry:
    rule: str
    location: str
    original: str
    replacement: str

    def short(self, width: int = 80) -> str:
        """Truncate original and replacement for display."""
        o = self.original[:width].replace("\n", "\\n")
        r = self.replacement[:width].replace("\n", "\\n")
        return f"[{self.rule}] {self.location}: {o!r} -> {r!r}"


# ---------------------------------------------------------------------------
# Core repair class
# ---------------------------------------------------------------------------
class LatexFormatRepair:
    """Applies a sequence of togglable IEEEtran format repair rules to LaTeX source.

    Usage:
        repair = LatexFormatRepair()
        repair_log = repair.repair(latex_source)
        fixed_latex = repair_log.fixed_text
        for entry in repair_log.entries:
            print(entry.short())
    """

    # ---- Rule toggles (set False to skip a rule) ----
    RULE_ENABLED = {
        "rule0_document_header": True,
        "rule1_abstract_env": True,
        "rule2_bibliography": True,
        "rule3_table_format": True,
        "rule4_citation_punct": True,
        "rule5_acronym_expand": True,
        "rule6_time_range": True,
        "rule7_fast_inference": True,
        "rule8_typography": True,
        "rule9_caption_position": True,
        "rule10_page_estimate": True,
    }

    # ---- IEEEtran-mandated document header ----
    IEEE_HEADER = r"""\documentclass[10pt,conference]{IEEEtran}
\usepackage{booktabs,amsmath,amssymb}

"""

    def __init__(self, enabled_rules: Optional[dict[str, bool]] = None):
        if enabled_rules:
            self.RULE_ENABLED = {**self.RULE_ENABLED, **enabled_rules}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def repair(self, latex: str) -> "RepairLog":
        """Run all enabled repair rules in order and return the repair log."""
        log = RepairLog(original=latex)
        text = latex

        if self.RULE_ENABLED.get("rule0_document_header", True):
            text, entries = self._rule0_document_header(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule1_abstract_env", True):
            text, entries = self._rule1_abstract_env(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule2_bibliography", True):
            text, entries = self._rule2_bibliography(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule3_table_format", True):
            text, entries = self._rule3_table_format(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule4_citation_punct", True):
            text, entries = self._rule4_citation_punct(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule5_acronym_expand", True):
            text, entries = self._rule5_acronym_expand(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule6_time_range", True):
            text, entries = self._rule6_time_range(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule7_fast_inference", True):
            text, entries = self._rule7_fast_inference(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule8_typography", True):
            text, entries = self._rule8_typography(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule9_caption_position", True):
            text, entries = self._rule9_caption_position(text)
            log.entries.extend(entries)

        if self.RULE_ENABLED.get("rule10_page_estimate", True):
            entries = self._rule10_page_estimate(text)
            log.entries.extend(entries)

        log.fixed_text = text
        return log

    # ------------------------------------------------------------------
    # Rule 0: Global IEEEtran document header standardisation
    # ------------------------------------------------------------------
    def _rule0_document_header(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Force IEEEtran-standard documentclass and preamble; remove geometry tweaks."""
        entries = []
        text = latex

        # 0a. Replace any existing \documentclass[...]{...} with IEEEtran header block
        docclass_pat = re.compile(r"\\documentclass[^}]*\{[^}]*\}", re.DOTALL)
        match = docclass_pat.search(text)
        if match:
            entries.append(RepairEntry(
                rule="rule0", location="preamble",
                original=match.group(0),
                replacement=self.IEEE_HEADER.strip(),
            ))
            text = docclass_pat.sub(lambda m: self.IEEE_HEADER.strip(), text, count=1)

        # 0b. Remove any \usepackage{geometry} and associated \geometry{...} lines
        geo_usecase = re.compile(
            r"\\usepackage\s*(\[.*?\])?\s*\{geometry\}[\s\n]*", re.MULTILINE
        )
        for m in list(geo_usecase.finditer(text)):
            entries.append(RepairEntry(
                rule="rule0", location="geometry-package",
                original=m.group(0).strip(), replacement="(removed)",
            ))
        text = geo_usecase.sub("", text)

        geo_cmd = re.compile(r"\\geometry\s*\{[^}]*\}", re.DOTALL)
        for m in list(geo_cmd.finditer(text)):
            entries.append(RepairEntry(
                rule="rule0", location="geometry-command",
                original=m.group(0).strip(), replacement="(removed)",
            ))
        text = geo_cmd.sub("", text)

        # 0c. Remove any stray \setlength{\hoffset}, \setlength{\voffset}, \setlength{\marginparwidth}
        margin_pat = re.compile(
            r"\\setlength\s*\{\\(?:hoffset|voffset|marginparwidth|marginparsep|oddsidemargin|evensidemargin|textwidth|textheight|topmargin|headheight|headsep)\}\s*\{[^}]*\}",
        )
        for m in list(margin_pat.finditer(text)):
            entries.append(RepairEntry(
                rule="rule0", location="margin-setlength",
                original=m.group(0).strip(), replacement="(removed)",
            ))
        text = margin_pat.sub("", text)

        # 0d. Ensure IEEEtran documentclass is used (in case the header replacement didn't cover it)
        if "\\documentclass[10pt,conference]{IEEEtran}" not in text:
            # Insert proper header after any existing \documentclass
            insert_point = text.find("\\documentclass")
            end_of_line = text.find("\n", insert_point)
            if end_of_line != -1:
                preamble = self.IEEE_HEADER.strip()
                # Remove \documentclass line from the inserted preamble since it's already there
                lines = preamble.split("\n")
                non_docclass = [l for l in lines if "\\documentclass" not in l]
                extra = "\n".join(non_docclass)
                text = text[:end_of_line + 1] + extra + "\n" + text[end_of_line + 1:]
                entries.append(RepairEntry(
                    rule="rule0", location="ieeetran-package-insert",
                    original="(missing IEEEtran documentclass)",
                    replacement=extra.strip(),
                ))

        return text, entries

    # ------------------------------------------------------------------
    # Rule 1: Abstract environment correction
    # ------------------------------------------------------------------
    def _rule1_abstract_env(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Replace \\section{Abstract} with \\begin{abstract}...\\end{abstract}."""
        entries = []
        text = latex

        # Match: \section{Abstract} (or \section*{Abstract}) followed by content
        # until the next \section (or \begin{abstract} if already present)
        pattern = re.compile(
            r"\\section\*?\s*\{Abstract\}\s*"
            r"(.*?)"
            r"(?=\\section\s*\{|\Z)",
            re.DOTALL | re.IGNORECASE,
        )

        def _replace_abstract(m: re.Match) -> str:
            content = m.group(1).strip()
            entries.append(RepairEntry(
                rule="rule1", location="abstract-section",
                original=m.group(0)[:100],
                replacement=f"\\begin{{abstract}}\n{content}\n\\end{{abstract}}",
            ))
            return f"\\begin{{abstract}}\n{content}\n\\end{{abstract}}\n\n"

        text = pattern.sub(_replace_abstract, text)

        # If abstract environment already exists, just ensure it's correct
        if "\\begin{abstract}" in text and "\\end{abstract}" in text:
            # Already present — nothing to do (already handled above)
            pass

        return text, entries

    # ------------------------------------------------------------------
    # Rule 2: Bibliography system correction (IEEEtran hard requirement)
    # ------------------------------------------------------------------
    def _rule2_bibliography(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Remove hand-written thebibliography and insert BibTeX config."""
        entries = []
        text = latex

        # Remove complete thebibliography block (including all content)
        bib_pattern = re.compile(
            r"\\begin\s*\{thebibliography\}\s*\{[^}]*\}.*?"
            r"\\end\s*\{thebibliography\}",
            re.DOTALL,
        )
        for m in list(bib_pattern.finditer(text)):
            entries.append(RepairEntry(
                rule="rule2", location="thebibliography",
                original=m.group(0)[:120],
                replacement="\\bibliographystyle{IEEEtran}\\bibliography{references}",
            ))

        text = bib_pattern.sub("", text)

        # Append BibTeX config at the end (before \end{document} if present)
        bibtex_block = "\n\n\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n"

        if "\\bibliographystyle" not in text:
            end_doc = text.find("\\end{document}")
            if end_doc != -1:
                text = text[:end_doc] + bibtex_block + text[end_doc:]
                entries.append(RepairEntry(
                    rule="rule2", location="end-document",
                    original="(missing \\bibliographystyle)",
                    replacement=bibtex_block.strip(),
                ))
            else:
                text += bibtex_block
                entries.append(RepairEntry(
                    rule="rule2", location="file-end",
                    original="(missing \\bibliographystyle)",
                    replacement=bibtex_block.strip(),
                ))

        return text, entries

    # ------------------------------------------------------------------
    # Rule 3: Table format — IEEEtran toprule/midrule/bottomrule three-line style
    # ------------------------------------------------------------------
    def _rule3_table_format(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Convert tables to IEEEtran three-line booktabs style."""
        entries = []
        text = latex

        def _fix_one_table(table_body: str) -> str:
            """Fix a single table environment body."""
            result = table_body

            # 3a. Add [htbp] to \begin{table} if missing
            result = re.sub(
                r"\\begin\{table\}(?!\s*\[)",
                r"\\begin{table}[htbp]",
                result,
            )

            # 3b. Remove [h] only (but keep [htbp] if already there)
            result = re.sub(
                r"(\\begin\{table\})\s*\[(h|H)\](?!.*?t.*?b.*?p)",
                r"\1[htbp]",
                result,
            )

            # 3c. Map star rating ★★★★★ to numeric 5-scale
            stars_map = {
                "★★★★★": "5",
                "★★★★": "4",
                "★★★": "3",
                "★★": "2",
                "★": "1",
            }
            for star, num in stars_map.items():
                if star in result:
                    result = result.replace(star, num)
                    entries.append(RepairEntry(
                        rule="rule3", location="table-star-rating",
                        original=f"(star {star})",
                        replacement=f"numeric {num}",
                    ))

            # 3d. Replace \hline with booktabs commands
            # First \hline after \toprule or at top → \toprule
            lines = result.split("\n")
            fixed_lines = []
            hline_count = 0
            first_hline = True
            last_hline = False
            for line in lines:
                stripped = line.strip()
                if stripped == r"\hline" or stripped == r"\hline%":
                    hline_count += 1
                    if hline_count == 1:
                        fixed_lines.append(line.replace(stripped, r"\toprule"))
                        entries.append(RepairEntry(
                            rule="rule3", location="table-hline",
                            original=r"\hline", replacement=r"\toprule",
                        ))
                    elif hline_count >= 2 and not line.strip().endswith("%"):
                        # Check if this is near the end (before \end{tabular})
                        # We'll handle this more carefully below
                        fixed_lines.append(line.replace(stripped, r"\midrule"))
                        entries.append(RepairEntry(
                            rule="rule3", location="table-hline",
                            original=r"\hline", replacement=r"\midrule",
                        ))
                    else:
                        fixed_lines.append(line.replace(stripped, r"\midrule"))
                    continue
                fixed_lines.append(line)
            result = "\n".join(fixed_lines)

            # 3d-continued: ensure \bottomrule at the end of tabular
            result = re.sub(
                r"\\midrule\s*(\\label\{[^}]*\})?\s*\\end\{tabular\}",
                r"\\bottomrule\n\1\\end{tabular}",
                result,
            )

            # 3e. Ensure booktabs is loaded (check preamble-level; handled in rule0)
            return result

        # Find all table environments and process them
        table_pattern = re.compile(
            r"(\\begin\{table\}.*?\\end\{table\})",
            re.DOTALL,
        )

        def _table_replacer(m: re.Match) -> str:
            fixed = _fix_one_table(m.group(1))
            return fixed

        text = table_pattern.sub(_table_replacer, text)

        return text, entries

    # ------------------------------------------------------------------
    # Rule 4: Citation punctuation fix
    # ------------------------------------------------------------------
    def _rule4_citation_punct(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Fix .~\\cite{key} -> ~\\cite{key}. (period before cite moved after)."""
        entries = []
        text = latex

        # Pattern: .~\cite{...}  →  ~\cite{...}.
        # This matches a period, then ~\cite{...} and swaps them
        pattern = re.compile(r"\.\s*~\\cite\{([^}]+)\}")

        def _fix_cite_punct(m: re.Match) -> str:
            cite_content = m.group(1)
            entries.append(RepairEntry(
                rule="rule4", location="citation-punct",
                original=m.group(0),
                replacement=f"~\\cite{{{cite_content}}}.",
            ))
            return f"~\\cite{{{cite_content}}}."

        text = pattern.sub(_fix_cite_punct, text)

        return text, entries

    # ------------------------------------------------------------------
    # Rule 5: Academic abbreviation standardisation (spot-check)
    # ------------------------------------------------------------------
    def _rule5_acronym_expand(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Spot-check key acronyms; ensure first occurrence has full expansion.

        This is a best-effort regex pass. The primary constraint is the system
        prompt. We only flag common CS/AI abbreviations that are often used without
        definition.
        """
        entries = []
        text = latex

        # Full-name map for key acronyms
        acronyms = {
            r"\bTTA\b": ("Test-Time Adaptation", "TTA"),
            r"\bTTT\b": ("Test-Time Training", "TTT"),
            r"\bMAML\b": ("Model-Agnostic Meta-Learning", "MAML"),
            r"\bBN\b": ("Batch Normalization", "BN"),
            r"\bFLOPs\b": ("Floating Point Operations", "FLOPs"),
            r"\bNAS\b": ("Neural Architecture Search", "NAS"),
        }

        # For each acronym, find the first occurrence and check if it's preceded
        # by its full expansion in parentheses within the same paragraph.
        for pattern, (full_name, _) in acronyms.items():
            matches = list(re.finditer(pattern, text))
            if not matches:
                continue

            first = matches[0]
            start = max(0, first.start() - 200)

            # Check if full name appears near the acronym (including the acronym itself)
            # e.g., "Test-Time Adaptation (TTA)" — the acronym is at first.start(), so
            # we need to check up to first.end() to capture the closing parenthesis
            check_window = text[start:first.end() + 10]
            # Build a flexible expansion pattern: replace any whitespace sequence
            # in the full name with \s+ to handle line breaks
            # e.g., "Test-Time\nAdaptation (TTA)" instead of "Test-Time Adaptation (TTA)"
            name_parts = re.split(r"\s+", full_name)
            flexible_name = r"\s+".join(re.escape(p) for p in name_parts)
            expansion_pattern = flexible_name + r"\s*[\(\[\{]" + re.escape(first.group(0)) + r"[\)\]\}]"
            if re.search(expansion_pattern, check_window, re.DOTALL):
                continue  # Already defined

            # Check if it's in a section title or caption (less critical)
            line_before = text[max(0, first.start() - 80):first.start()]
            if re.search(r"\\section|\\caption|\\textbf|\\textit", line_before):
                continue

            # First occurrence not expanded — expand it
            # Only do this if the acronym appears in body text, not in commands
            if not re.match(r"\\[a-z]+", first.group(0)):
                # Insert expansion before the acronym
                expansion = f"{full_name} ({first.group(0)})"
                text = text[:first.start()] + expansion + text[first.end():]
                entries.append(RepairEntry(
                    rule="rule5", location="acronym",
                    original=f"(unexpanded {first.group(0)})",
                    replacement=expansion,
                ))

        return text, entries

    # ------------------------------------------------------------------
    # Rule 6: Time range correction
    # ------------------------------------------------------------------
    def _rule6_time_range(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Replace 2026 with 2025 throughout the document."""
        entries = []
        text = latex

        # Replace standalone 2026 (but not in BibTeX keys or URLs)
        # Look for 2026 as a year reference
        pattern = re.compile(r"(?<!\d)(2026)(?!\d)")

        for m in list(pattern.finditer(text)):
            # Skip if inside a URL or BibTeX key
            context = text[max(0, m.start() - 30):m.end() + 30]
            if re.search(r"\\url\{|\\href\{|bibkey|@article|@inproceedings", context):
                continue

            entries.append(RepairEntry(
                rule="rule6", location="year",
                original=m.group(0),
                replacement="2025",
            ))

        text = pattern.sub("2025", text)

        return text, entries

    # ------------------------------------------------------------------
    # Rule 7: Fast Inference concept boundary clarification
    # ------------------------------------------------------------------
    def _rule7_fast_inference(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Ensure pruning/quantization/NAS mentioned in test-phase context
        includes a boundary clarification sentence."""
        entries = []
        text = latex

        # Keywords that trigger the check
        trigger_keywords = [
            r"(?i)\b(?:pruning|quantization|dynamic\s*early\s*exit|NAS|neural\s*architecture\s*search)\b",
        ]

        # The required clarification sentence
        clarification = (
            "These optimizations reduce runtime latency during inference, "
            "hence belong to the test-phase pipeline."
        )

        # Check sections that discuss "quick test", "test-phase", "inference speed"
        section_pattern = re.compile(
            r"(\\section\*?\s*\{[^}]*?(?:quick|test|inference|latency|deploy|runtime)[^}]*\})"
            r"(.*?)(?=\\section\s*\{|\Z)",
            re.DOTALL | re.IGNORECASE,
        )

        def _check_section(m: re.Match) -> str:
            section_header = m.group(1)
            section_body = m.group(2)

            for trigger in trigger_keywords:
                if re.search(trigger, section_body) and clarification not in section_body:
                    # Find the paragraph containing the trigger and append clarification
                    trigger_match = re.search(trigger, section_body)
                    if trigger_match:
                        para_start = section_body.rfind("\n\n", 0, trigger_match.start())
                        if para_start == -1:
                            para_start = 0
                        para_end = section_body.find("\n\n", trigger_match.end())
                        if para_end == -1:
                            para_end = len(section_body)

                        # Insert clarification at the end of the paragraph
                        section_body = (
                            section_body[:para_end]
                            + "\n" + clarification + "\n"
                            + section_body[para_end:]
                        )
                        entries.append(RepairEntry(
                            rule="rule7", location="inference-boundary",
                            original=f"(missing clarification in section with {trigger_match.group(0)})",
                            replacement=clarification,
                        ))
                        break

            return section_header + section_body

        text = section_pattern.sub(_check_section, text)

        return text, entries

    # ------------------------------------------------------------------
    # Rule 8: English typography fixes
    # ------------------------------------------------------------------
    def _rule8_typography(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Fix common English typography issues in LaTeX."""
        entries = []
        text = latex

        # 8a. Em-dash --- (three hyphens) is standard in LaTeX, but ensure
        #     double-hyphen -- is used for en-dash ranges
        #     First, protect triple hyphens (em-dash)
        #     Then fix double hyphens that aren't already em-dashes
        #     Actually, in LaTeX: --- is em-dash, -- is en-dash
        #     We want to ensure that word--word ranges use --
        #     and that standalone hyphens in text are proper

        # 8b. Fix long em-dash in text (should be ---)
        #     Pattern: word—word (Unicode em-dash) → word---word
        text = re.sub(r"\u2014|\u2015", "---", text)
        #     Unicode en-dash → --
        text = re.sub(r"\u2013", "--", text)

        # 8c. Fix smart/curly quotes to LaTeX quotes
        #     Unicode left/right double quotes → `` resp. ''
        text = re.sub(r"\u201c", "``", text)
        text = re.sub(r"\u201d", "''", text)
        #     Unicode left/right single quotes → ` resp. '
        text = re.sub(r"\u2018", "`", text)
        text = re.sub(r"\u2019", "'", text)

        # 8d. Fix spacing between numbers and words (e.g., "3layer" -> "3 layer")
        #     Exclude LaTeX units (pt, cm, mm, in, px, em, ex, etc.) and
        #     common LaTeX dimension suffixes

        def _fix_number_word(m: re.Match) -> str:
            """Insert space between digit and word, but not for LaTeX units."""
            word = m.group(2).lower()
            # LaTeX units and common non-word abbreviations that should not be separated
            latex_units = {
                "pt", "cm", "mm", "in", "px", "em", "ex", "bp", "dd", "pc",
                "cc", "sp", "nd", "st", "th", "rd", "d", "s", "x", "y", "z",
            }
            if word in latex_units:
                return m.group(0)  # Keep as-is
            return f"{m.group(1)} {m.group(2)}"

        text = re.sub(r"(\d)([a-zA-Z]{2,})", _fix_number_word, text)

        # 8e. Fix multiple spaces (more than 2) to single space
        text = re.sub(r" {3,}", "  ", text)

        # 8f. Fix spaces before punctuation
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)

        # 8g. Ensure proper spacing after periods (single space, not double)
        text = re.sub(r"\.  (\S)", r". \1", text)

        entries.append(RepairEntry(
            rule="rule8", location="typography",
            original="(multiple typography fixes applied)",
            replacement="Unicode dashes/quotes replaced, spacing normalised",
        ))

        return text, entries

    # ------------------------------------------------------------------
    # Rule 9: Caption position — table captions above, figure captions below
    # ------------------------------------------------------------------
    def _rule9_caption_position(self, latex: str) -> tuple[str, list[RepairEntry]]:
        """Verify and fix caption positions: table captions above, figure captions below."""
        entries = []
        text = latex

        # 9a. Table captions: ensure \caption is before tabular content
        def _fix_table_caption(table_block: re.Match) -> str:
            block = table_block.group(0)
            # Check if caption is after \begin{tabular}
            if re.search(r"\\begin\{tabular\}.*?\\caption", block, re.DOTALL):
                # Move caption before tabular
                # Extract caption
                caption_match = re.search(r"\\caption\{[^}]*\}", block)
                if caption_match:
                    caption = caption_match.group(0)
                    # Remove caption from its current position
                    block = block.replace(caption, "")
                    # Insert caption right after \begin{table} or \begin{table}[htbp]
                    block = re.sub(
                        r"(\\begin\{table\}\s*(\[[^\]]*\])?\s*)",
                        lambda m: m.group(1) + caption + "\n",
                        block,
                        count=1,
                    )
                    entries.append(RepairEntry(
                        rule="rule9", location="table-caption",
                        original="(caption after tabular)",
                        replacement="(caption moved above tabular)",
                    ))
            return block

        text = re.sub(
            r"(\\begin\{table\}.*?\\end\{table\})",
            _fix_table_caption,
            text,
            flags=re.DOTALL,
        )

        # 9b. Figure captions: ensure \caption is after \includegraphics
        def _fix_figure_caption(figure_block: re.Match) -> str:
            block = figure_block.group(0)
            # Check if caption is before \includegraphics
            if re.search(r"\\caption\{[^}]*\}.*?\\includegraphics", block, re.DOTALL):
                # Move caption after includegraphics
                caption_match = re.search(r"\\caption\{[^}]*\}", block)
                includegraphics_match = re.search(r"\\includegraphics(\[[^\]]*\])?\{[^}]*\}", block)
                if caption_match and includegraphics_match:
                    caption = caption_match.group(0)
                    # Remove caption from its current position
                    block = block.replace(caption, "")
                    # Insert caption after \includegraphics
                    block = block.replace(includegraphics_match.group(0),
                                          includegraphics_match.group(0) + "\n" + caption)
                    entries.append(RepairEntry(
                        rule="rule9", location="figure-caption",
                        original="(caption before includegraphics)",
                        replacement="(caption moved below includegraphics)",
                    ))
            return block

        text = re.sub(
            r"(\\begin\{figure\}.*?\\end\{figure\})",
            _fix_figure_caption,
            text,
            flags=re.DOTALL,
        )

        return text, entries

    # ------------------------------------------------------------------
    # Rule 10: Page count estimation
    # ------------------------------------------------------------------
    def _rule10_page_estimate(self, latex: str) -> list[RepairEntry]:
        """Estimate compiled PDF page count and warn if over IEEEtran limit (6 pages)."""
        entries = []
        text = latex

        # Rough estimate: ~3000 characters per page in two-column IEEEtran format
        # This is a coarse heuristic; actual count depends on content density
        body = text

        # Remove LaTeX commands that don't contribute visible text
        body_clean = re.sub(r"\\[a-zA-Z]+(\[.*?\])?\{.*?\}", "", body)
        body_clean = re.sub(r"\\[a-zA-Z]+", "", body_clean)
        body_clean = re.sub(r"\$.*?\$", "", body_clean)  # Remove inline math
        body_clean = re.sub(r"\s+", " ", body_clean).strip()

        char_count = len(body_clean)
        # IEEEtran two-column: ~3000-3500 characters of text per page
        # But tables/figures take up space, so we use a conservative 2800 chars/page
        estimated_pages = char_count / 2800

        # Account for bibliography (not counted in IEEEtran page limit)
        bib_section = re.search(
            r"\\bibliographystyle|\\begin\{thebibliography\}",
            text,
        )
        bib_chars = 0
        if bib_section:
            bib_text = text[bib_section.start():]
            bib_clean = re.sub(r"\\[a-zA-Z]+(\[.*?\])?\{.*?\}", "", bib_text)
            bib_clean = re.sub(r"\s+", " ", bib_clean).strip()
            bib_chars = len(bib_clean)
            estimated_pages = (char_count - bib_chars) / 2800

        estimated_pages = max(1, round(estimated_pages, 1))

        if estimated_pages > 6:
            entries.append(RepairEntry(
                rule="rule10", location="page-count",
                original=f"~{estimated_pages} pages (estimated)",
                replacement=f"WARNING: ~{estimated_pages} pages exceeds IEEEtran 6-page limit. "
                            f"Consider condensing content.",
            ))
            logger.warning(
                "Page estimate: ~%.1f pages (IEEEtran limit: 6). Consider condensing.",
                estimated_pages,
            )
        else:
            entries.append(RepairEntry(
                rule="rule10", location="page-count",
                original=f"~{estimated_pages} pages",
                replacement=f"~{estimated_pages} pages — within IEEEtran 6-page limit.",
            ))

        return entries


# ---------------------------------------------------------------------------
# RepairLog container
# ---------------------------------------------------------------------------
@dataclass
class RepairLog:
    original: str
    fixed_text: str = ""
    entries: list[RepairEntry] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.entries) > 0

    @property
    def change_count(self) -> int:
        return len(self.entries)

    def summary(self) -> str:
        lines = [f"Repair log: {self.change_count} change(s)"]
        for e in self.entries:
            lines.append(f"  {e.short()}")
        return "\n".join(lines)