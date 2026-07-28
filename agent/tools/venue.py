"""Venue lookup tool — queries DBLP to determine paper venue quality."""
import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

DBLP_API_URL = "https://dblp.org/search/publ/api"

TOP_VENUES = {
    # Computer Vision
    "cvpr", "iccv", "eccv", "bmvc", "wacv",
    # Machine Learning
    "neurips", "icml", "iclr", "jmlr", "mlsys", "aistats", "uai",
    # NLP
    "acl", "emnlp", "naacl", "eacl", "coling", "tacl",
    # AI
    "aaai", "ijcai", "ecai",
    # Software Engineering
    "icse", "fse", "ase", "issta", "tse", "tosem", "ist",
    # Systems & Networking
    "osdi", "sosp", "sigcomm", "mobicom", "nsdi", "eurosys", "atc",
    # PL & Theory
    "pldi", "popl", "cav", "stoc", "focs", "soda", "icalp",
    # Databases
    "sigmod", "vldb", "pods", "icde", "sigir",
    # Security
    "sp", "ccs", "usenix", "ndss",
}


class VenueLookup(Tool):
    name = "venue_lookup"
    description = "Look up paper venue via DBLP and mark top-tier venues"

    def execute(self, params: dict) -> ToolResult:
        papers = list(params.get("papers", []))

        if not papers:
            return ToolResult(success=True, data={"papers": []})

        for paper in papers:
            # Skip if already marked as top venue
            if paper.get("is_top_venue"):
                continue

            # Try to determine venue from existing data first
            existing_venue = (paper.get("venue") or "").strip().lower()
            if existing_venue and self._match_venue(existing_venue):
                paper["is_top_venue"] = True
                paper["venue_type"] = self._classify_venue(existing_venue)
                continue

            # Fall back to DBLP query
            venue_info = self._query_dblp(paper.get("title", ""))
            if venue_info:
                paper["venue"] = venue_info.get("venue", paper.get("venue", ""))
                if venue_info.get("is_top"):
                    paper["is_top_venue"] = True
                paper["venue_type"] = venue_info.get("type", "unknown")

            time.sleep(0.3)

        return ToolResult(success=True, data={"papers": papers})

    def _query_dblp(self, title: str):
        """Query DBLP API for venue information."""
        if not title:
            return None

        params = urllib.parse.urlencode({
            "q": title[:200],
            "format": "xml",
            "hits": 3,
        })
        url = f"{DBLP_API_URL}?{params}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ScholarAgent/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_text = resp.read().decode("utf-8")
            return self._parse_dblp_response(xml_text, title)
        except Exception as e:
            logger.debug("DBLP query failed for '%s': %s", title[:50], e)
            return None

    @staticmethod
    def _parse_dblp_response(xml_text: str, query_title: str):
        """Parse DBLP XML response, return venue info for best match."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        ns = {"dblp": "http://www.dblp.org/xml/ns/dblp"}
        hits = root.findall(".//dblp:hit", ns)
        if not hits:
            return None

        # Try to find the best title match
        query_norm = query_title.lower().strip().rstrip(".")
        for hit in hits[:3]:
            info = hit.find("dblp:info", ns)
            if info is None:
                continue

            title_el = info.find(".//dblp:title", ns)
            if title_el is None or not title_el.text:
                continue

            hit_title = title_el.text.lower().strip().rstrip(".")
            if query_norm != hit_title and query_norm[:30] != hit_title[:30]:
                continue

            # Extract venue
            venue = ""
            venue_type = "unknown"
            for tag in ("journal", "booktitle", "publisher"):
                el = info.find(f"dblp:{tag}", ns)
                if el is not None and el.text:
                    venue = el.text.strip()
                    venue_type = "journal" if tag == "journal" else "conference"
                    break

            if not venue:
                continue

            normalized = VenueLookup._normalize_venue(venue)
            is_top = normalized in TOP_VENUES

            return {
                "venue": venue,
                "is_top": is_top,
                "type": venue_type,
            }

        return None

    @staticmethod
    def _normalize_venue(venue: str) -> str:
        """Normalize venue name for matching against TOP_VENUES."""
        v = venue.lower().strip()
        v = re.sub(r'^(proceedings of|ieee|acm|the|international conference on|ieee/cvf)\s+', '', v)
        v = re.sub(r'\s+\d{4}$', '', v)
        v = re.sub(r'[^a-z0-9]', '', v)
        return v

    @staticmethod
    def _match_venue(venue: str) -> bool:
        """Check if an already-known venue string matches a top venue."""
        normalized = VenueLookup._normalize_venue(venue)
        return normalized in TOP_VENUES

    @staticmethod
    def _classify_venue(venue: str) -> str:
        """Classify venue type (conference or journal)."""
        v = venue.lower()
        if any(w in v for w in ("journal", "transactions", "letters", "computing", "survey")):
            return "journal"
        return "conference"