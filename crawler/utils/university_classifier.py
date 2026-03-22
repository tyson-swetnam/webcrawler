"""
University Classifier - Categorizes universities into Peer, R1, HPC, National Lab, and Global
"""
import json
from pathlib import Path
from typing import Set, Tuple


class UniversityClassifier:
    """Classifies universities and facilities into five categories for HTML display"""

    def __init__(self):
        self.peer_institutions = self._load_peer_institutions()
        self.r1_institutions = self._load_r1_institutions()
        self.hpc_exact, self.hpc_fuzzy = self._load_hpc_centers()
        self.national_labs_exact, self.national_labs_fuzzy = self._load_national_labs()
        self.global_exact, self.global_fuzzy = self._load_global_institutions()

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
            # Global institution abbreviations
            'eth': 'eth zurich',
            'epfl': 'epfl',
            'oxford': 'university of oxford',
            'cambridge': 'university of cambridge',
            'imperial': 'imperial college london',
            'ucl': 'university college london',
            'tsinghua': 'tsinghua university',
            'peking': 'peking university',
            'utokyo': 'university of tokyo',
            'kaist': 'kaist',
            'nus': 'national university of singapore',
            'ntu': 'nanyang technological university',
            'technion': 'technion',
            # National lab abbreviations
            'anl': 'argonne national laboratory',
            'llnl': 'lawrence livermore national laboratory',
            'lanl': 'los alamos national laboratory',
            'ornl': 'oak ridge national laboratory',
            'lbnl': 'lawrence berkeley national laboratory',
            'snl': 'sandia national laboratories',
            'pnnl': 'pacific northwest national laboratory',
            'bnl': 'brookhaven national laboratory',
            'slac': 'slac national accelerator laboratory',
            'fermilab': 'fermi national accelerator laboratory',
            'inl': 'idaho national laboratory',
            'nrel': 'national renewable energy laboratory',
            'pppl': 'princeton plasma physics laboratory',
            'srnl': 'savannah river national laboratory',
            'netl': 'national energy technology laboratory',
            'jpl': 'nasa jpl',
            'darpa': 'darpa',
            'mitre': 'mitre corporation',
            'rand': 'rand corporation',
            'lincoln lab': 'mit lincoln laboratory',
            'jhu apl': 'johns hopkins apl',
            'sei': 'cmu software engineering institute',
            'nist': 'nist',
            'nsf': 'national science foundation',
            'arpa-e': 'arpa-e',
        }

    def _load_peer_institutions(self) -> Set[str]:
        """Load peer institution names from peer_institutions.json"""
        path = Path("crawler/config/peer_institutions.json")
        if not path.exists():
            return set()

        with open(path, 'r') as f:
            data = json.load(f)

        universities = data.get('universities', [])
        names = set()
        for univ in universities:
            names.add(univ['name'].lower())
            # Also index by canonical_name and abbreviation for fuzzy robustness
            if univ.get('canonical_name'):
                names.add(univ['canonical_name'].lower())
            if univ.get('abbreviation'):
                names.add(univ['abbreviation'].lower())
        return names

    def _load_r1_institutions(self) -> Set[str]:
        """Load R1 institution names from r1_universities.json"""
        path = Path("crawler/config/r1_universities.json")
        if not path.exists():
            return set()

        with open(path, 'r') as f:
            data = json.load(f)

        universities = data.get('universities', [])
        return {univ['name'].lower() for univ in universities}

    def _load_hpc_centers(self) -> Tuple[Set[str], Set[str]]:
        """Load HPC & Research Center names from major_facilities.json.
        Returns (exact_match_set, fuzzy_match_set). Short abbreviations
        are only in the exact set to prevent false substring matches."""
        path = Path("crawler/config/major_facilities.json")
        if not path.exists():
            return set(), set()

        with open(path, 'r') as f:
            data = json.load(f)

        facilities = data.get('facilities', [])
        exact = set()
        fuzzy = set()
        for facility in facilities:
            name = facility['name'].lower()
            exact.add(name)
            fuzzy.add(name)
            if facility.get('abbreviation'):
                abbrev = facility['abbreviation'].lower()
                exact.add(abbrev)
                if len(abbrev) >= 5:
                    fuzzy.add(abbrev)
        return exact, fuzzy

    def _load_national_labs(self) -> Tuple[Set[str], Set[str]]:
        """Load national laboratory names from national_laboratories.json.
        Returns (exact_match_set, fuzzy_match_set). Short abbreviations
        are only in the exact set to prevent false substring matches."""
        path = Path("crawler/config/national_laboratories.json")
        if not path.exists():
            return set(), set()

        with open(path, 'r') as f:
            data = json.load(f)

        facilities = data.get('facilities', [])
        exact = set()
        fuzzy = set()
        for facility in facilities:
            name = facility['name'].lower()
            exact.add(name)
            fuzzy.add(name)
            if facility.get('abbreviation'):
                abbrev = facility['abbreviation'].lower()
                exact.add(abbrev)
                if len(abbrev) >= 5:
                    fuzzy.add(abbrev)
        return exact, fuzzy

    def _load_global_institutions(self) -> Tuple[Set[str], Set[str]]:
        """Load global institution names from global_institutions.json.
        Returns (exact_match_set, fuzzy_match_set). Short abbreviations
        are only in the exact set to prevent false substring matches."""
        path = Path("crawler/config/global_institutions.json")
        if not path.exists():
            return set(), set()

        with open(path, 'r') as f:
            data = json.load(f)

        universities = data.get('universities', [])
        exact = set()
        fuzzy = set()
        for univ in universities:
            name = univ['name'].lower()
            exact.add(name)
            fuzzy.add(name)
            if univ.get('abbreviation'):
                abbrev = univ['abbreviation'].lower()
                exact.add(abbrev)
                if len(abbrev) >= 5:
                    fuzzy.add(abbrev)
        return exact, fuzzy

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
        Classify a university or facility into one of five categories.
        Priority: national_lab > hpc > peer > global > r1

        Args:
            university_name: Name of the university or facility

        Returns:
            'peer', 'r1', 'hpc', 'national_lab', or 'global'
        """
        if not university_name:
            return 'r1'

        name_lower = university_name.lower()

        # Check abbreviation expansion first
        if name_lower in self.abbreviations:
            name_lower = self.abbreviations[name_lower]

        # Check national labs first (highest priority) - exact match
        if name_lower in self.national_labs_exact:
            return 'national_lab'

        # Check HPC centers - exact match
        if name_lower in self.hpc_exact:
            return 'hpc'

        # Check peer institutions
        if name_lower in self.peer_institutions:
            return 'peer'

        # Check global institutions - exact match
        if name_lower in self.global_exact:
            return 'global'

        # Check R1 exact match
        if name_lower in self.r1_institutions:
            return 'r1'

        # Fuzzy matching with normalized names
        # Uses fuzzy sets that exclude short abbreviations to prevent
        # false positives (e.g. "ida" matching "florida")
        normalized = self._normalize_name(university_name)
        if normalized:
            # Check national labs fuzzy
            for lab in self.national_labs_fuzzy:
                if len(lab) >= 5 and (normalized in lab or lab in normalized):
                    return 'national_lab'

            # Check HPC centers fuzzy
            for hpc in self.hpc_fuzzy:
                if len(hpc) >= 5 and (normalized in hpc or hpc in normalized):
                    return 'hpc'

            # Check peer institutions fuzzy
            for peer in self.peer_institutions:
                if normalized in peer or peer in normalized:
                    return 'peer'

            # Check global institutions fuzzy
            for glob in self.global_fuzzy:
                if len(glob) >= 5 and (normalized in glob or glob in normalized):
                    return 'global'

            # Check R1 institutions fuzzy
            for r1 in self.r1_institutions:
                if normalized in r1 or r1 in normalized:
                    return 'r1'

        # Default to r1 category
        return 'r1'

    def get_category_stats(self) -> Tuple[int, int, int, int, int]:
        """
        Get counts of sources in each category.

        Returns:
            Tuple of (peer_count, r1_count, hpc_count, national_lab_count, global_count)
        """
        return (
            len(self.peer_institutions),
            len(self.r1_institutions),
            len(self.hpc_exact),
            len(self.national_labs_exact),
            len(self.global_exact)
        )
