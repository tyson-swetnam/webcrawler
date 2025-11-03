"""
University Classifier - Categorizes universities into Peer, R1, and All Others
"""
import json
from pathlib import Path
from typing import Set, Tuple


class UniversityClassifier:
    """Classifies universities and facilities into three categories for HTML display"""

    def __init__(self):
        self.peer_institutions = self._load_peer_institutions()
        self.r1_institutions = self._load_r1_institutions()
        self.major_facilities = self._load_major_facilities()

        # Common abbreviations mapping
        self.abbreviations = {
            'mit': 'massachusetts institute of technology',
            'stanford': 'stanford university',
            'harvard': 'harvard university',
            'berkeley': 'university of california, berkeley',
            'uc berkeley': 'university of california, berkeley',
            'cmu': 'carnegie mellon university',
            'caltech': 'california institute of technology',
            'penn': 'university of pennsylvania',
            'columbia': 'columbia university',
            'cornell': 'cornell university',
            'duke': 'duke university',
            'yale': 'yale university',
            'princeton': 'princeton university',
            'uchicago': 'university of chicago',
            'jhu': 'johns hopkins university',
            'northwestern': 'northwestern university',
            'brown': 'brown university',
            'dartmouth': 'dartmouth college',
            'rice': 'rice university',
            'vanderbilt': 'vanderbilt university',
            'ucla': 'university of california, los angeles',
            'ucsd': 'university of california, san diego',
            'gatech': 'georgia institute of technology',
            'georgia tech': 'georgia institute of technology',
            'uiuc': 'university of illinois urbana-champaign',
            'umich': 'university of michigan',
            'uw': 'university of washington',
            'ut austin': 'university of texas at austin',
        }

    def _load_peer_institutions(self) -> Set[str]:
        """Load peer institution names from peer_institutions.json"""
        path = Path("crawler/config/peer_institutions.json")
        if not path.exists():
            return set()

        with open(path, 'r') as f:
            data = json.load(f)

        universities = data.get('universities', [])
        return {univ['name'].lower() for univ in universities}

    def _load_r1_institutions(self) -> Set[str]:
        """Load R1 institution names from r1_universities.json"""
        path = Path("crawler/config/r1_universities.json")
        if not path.exists():
            return set()

        with open(path, 'r') as f:
            data = json.load(f)

        universities = data.get('universities', [])
        return {univ['name'].lower() for univ in universities}

    def _load_major_facilities(self) -> Set[str]:
        """Load major facility names from major_facilities.json"""
        path = Path("crawler/config/major_facilities.json")
        if not path.exists():
            return set()

        with open(path, 'r') as f:
            data = json.load(f)

        facilities = data.get('facilities', [])
        # Include both full names and abbreviations
        facility_names = set()
        for facility in facilities:
            facility_names.add(facility['name'].lower())
            if facility.get('abbreviation'):
                facility_names.add(facility['abbreviation'].lower())
        return facility_names

    def _normalize_name(self, name: str) -> str:
        """
        Normalize university name for better matching.
        Removes common variations like 'The', trailing commas, etc.
        """
        if not name:
            return ''

        name = name.lower().strip()

        # Remove common prefixes
        prefixes_to_remove = ['the ', 'university of ', 'university at ']
        for prefix in prefixes_to_remove:
            if name.startswith(prefix):
                name = name[len(prefix):]

        return name.strip()

    def classify(self, university_name: str) -> str:
        """
        Classify a university or facility into one of three categories.
        Priority: Facility > Peer (exact) > Peer (fuzzy) > R1 (exact) > R1 (fuzzy)

        Args:
            university_name: Name of the university or facility

        Returns:
            'peer', 'r1', or 'facility'
        """
        if not university_name:
            return 'facility'

        name_lower = university_name.lower()

        # Check abbreviation expansion first
        if name_lower in self.abbreviations:
            name_lower = self.abbreviations[name_lower]

        # Check major facilities first (they may overlap with universities)
        if name_lower in self.major_facilities:
            return 'facility'

        # Check peer (highest priority for universities) - exact match
        if name_lower in self.peer_institutions:
            return 'peer'

        # Try normalized name matching for peer institutions BEFORE checking R1 exact
        # This ensures peer institutions take priority even if they're also in R1 list
        normalized = self._normalize_name(university_name)
        if normalized:
            # Check if normalized name appears in any peer institution
            for peer in self.peer_institutions:
                if normalized in peer or peer in normalized:
                    return 'peer'

        # Then check R1 - exact match
        if name_lower in self.r1_institutions:
            return 'r1'

        # Fuzzy matching for remaining categories
        if normalized:
            # Check if normalized name appears in any facility
            for facility in self.major_facilities:
                if normalized in facility or facility in normalized:
                    return 'facility'

            # Check if normalized name appears in any R1 institution
            for r1 in self.r1_institutions:
                if normalized in r1 or r1 in normalized:
                    return 'r1'

        # Default to facility category
        return 'facility'

    def get_category_stats(self) -> Tuple[int, int, int]:
        """
        Get counts of sources in each category.

        Returns:
            Tuple of (peer_count, r1_count, facility_count)
        """
        return (
            len(self.peer_institutions),
            len(self.r1_institutions),
            len(self.major_facilities)
        )
