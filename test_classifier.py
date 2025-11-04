#!/usr/bin/env python3
"""
Test script to verify UniversityClassifier correctly categorizes universities.

This script tests that the classifier correctly identifies universities after
they've been mapped to canonical names.
"""

import sys
from crawler.utils.university_classifier import UniversityClassifier


def test_classifier():
    """
    Test that classifier correctly categorizes universities.
    """
    print("\n" + "="*70)
    print("Testing University Classifier")
    print("="*70 + "\n")

    classifier = UniversityClassifier()

    # Test cases: (university_name, expected_category)
    test_cases = [
        # Peer institutions
        ("Auburn University", "peer"),
        ("University of Arizona", "peer"),
        ("Arizona State University", "peer"),
        ("University of Colorado Boulder", "peer"),

        # R1 universities (not in peer list)
        ("Stanford University", "r1"),
        ("Massachusetts Institute of Technology", "r1"),
        ("Harvard University", "r1"),

        # Major facilities
        ("Texas Advanced Computing Center", "facility"),
        ("Argonne National Laboratory", "facility"),
        ("National Center for Supercomputing Applications", "facility"),

        # Test with sitenames that should NOT match (old behavior)
        ("AuburnEngineers", "facility"),  # Should be facility without mapping
    ]

    print("Testing university classifications:\n")

    all_passed = True
    for university_name, expected_category in test_cases:
        category = classifier.classify(university_name)
        passed = category == expected_category
        all_passed = all_passed and passed

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {university_name}")
        print(f"      Expected: {expected_category}")
        print(f"      Got:      {category}")
        print()

    print("="*70)
    if all_passed:
        print("ALL TESTS PASSED")
        print("\nClassifier Summary:")
        peer_count, r1_count, facility_count = classifier.get_category_stats()
        print(f"  Peer Institutions: {peer_count}")
        print(f"  R1 Universities:   {r1_count}")
        print(f"  Major Facilities:  {facility_count}")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(test_classifier())
