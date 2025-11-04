#!/usr/bin/env python3
"""
Integration test to verify the complete flow from URL to classification.

This test simulates the spider extracting an article from eng.auburn.edu and
verifies it gets correctly mapped to "Auburn University" and classified as "peer".
"""

import sys
from crawler.spiders.university_spider import UniversityNewsSpider
from crawler.utils.university_classifier import UniversityClassifier


def test_integration():
    """
    Test complete flow: domain -> canonical name -> classification.
    """
    print("\n" + "="*70)
    print("Integration Test: Auburn University Article Processing")
    print("="*70 + "\n")

    # Initialize spider (this builds the domain mapping)
    print("Step 1: Initialize spider...")
    spider = UniversityNewsSpider()
    print(f"  Domain mapping contains {len(spider.domain_to_canonical)} domains")

    # Initialize classifier
    print("\nStep 2: Initialize classifier...")
    classifier = UniversityClassifier()
    peer_count, r1_count, facility_count = classifier.get_category_stats()
    print(f"  Classifier loaded {peer_count} peer institutions")

    # Test domain mapping
    print("\nStep 3: Test domain mapping...")
    test_domains = [
        ("eng.auburn.edu", "AuburnEngineers"),
        ("news.auburnuniversity.edu", "Auburn News"),
        ("news.arizona.edu", "UArizona News"),
        ("www.tacc.utexas.edu", "TACC"),
    ]

    all_passed = True
    for hostname, sitename in test_domains:
        canonical = spider._get_canonical_name(hostname, sitename)
        print(f"  {hostname} ({sitename}) -> {canonical}")

    # Test the critical Auburn case
    print("\nStep 4: Test Auburn University flow...")
    hostname = "eng.auburn.edu"
    sitename = "AuburnEngineers"

    # Get canonical name
    canonical_name = spider._get_canonical_name(hostname, sitename)
    print(f"  Domain mapping: {hostname} -> {canonical_name}")

    # Classify
    category = classifier.classify(canonical_name)
    print(f"  Classification: {canonical_name} -> {category}")

    # Verify expected results
    expected_canonical = "Auburn University"
    expected_category = "peer"

    print("\nStep 5: Verify results...")
    canonical_passed = canonical_name == expected_canonical
    category_passed = category == expected_category

    print(f"  Canonical name: {'PASS' if canonical_passed else 'FAIL'}")
    print(f"    Expected: {expected_canonical}")
    print(f"    Got:      {canonical_name}")

    print(f"  Category: {'PASS' if category_passed else 'FAIL'}")
    print(f"    Expected: {expected_category}")
    print(f"    Got:      {category}")

    # Test old behavior (sitename without mapping)
    print("\nStep 6: Verify old behavior was broken...")
    old_category = classifier.classify(sitename)
    print(f"  Old behavior: '{sitename}' -> {old_category}")
    print(f"  This demonstrates why we needed the fix (should be 'facility', not 'peer')")

    print("\n" + "="*70)
    if canonical_passed and category_passed:
        print("INTEGRATION TEST PASSED")
        print("\nThe fix successfully:")
        print("  1. Maps eng.auburn.edu to 'Auburn University'")
        print("  2. Classifier correctly identifies it as 'peer'")
        print("  3. Prevents misclassification as 'facility'")
        return 0
    else:
        print("INTEGRATION TEST FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(test_integration())
