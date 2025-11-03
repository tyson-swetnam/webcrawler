# Major Facilities Update - Third Column Implementation

## Overview
Successfully updated the web crawler to replace "All Others" column with "Major Facilities" column featuring NSF supercomputing centers and DOE national laboratories.

## What Was Changed

### 1. New Configuration File: `major_facilities.json`
**Location:** `crawler/config/major_facilities.json`

**Contents:** 27 major research facilities including:

**NSF Supercomputing Centers (6):**
- Texas Advanced Computing Center (TACC) - UT Austin
- San Diego Supercomputer Center (SDSC) - UC San Diego
- Pittsburgh Supercomputing Center (PSC) - CMU/Pitt
- National Center for Supercomputing Applications (NCSA) - UIUC
- Purdue Rosen Center for Advanced Computing (RCAC)
- Indiana University Pervasive Technology Institute (PTI)

**DOE National Laboratories (17):**
- Argonne National Laboratory (ANL)
- Lawrence Livermore National Laboratory (LLNL)
- Los Alamos National Laboratory (LANL)
- Oak Ridge National Laboratory (ORNL)
- Lawrence Berkeley National Laboratory (LBNL)
- Sandia National Laboratories (SNL)
- Pacific Northwest National Laboratory (PNNL)
- Brookhaven National Laboratory (BNL)
- SLAC National Accelerator Laboratory
- Fermi National Accelerator Laboratory (Fermilab)
- Idaho National Laboratory (INL)
- National Renewable Energy Laboratory (NREL)
- Ames Laboratory
- Princeton Plasma Physics Laboratory (PPPL)
- Thomas Jefferson National Accelerator Facility (Jefferson Lab)
- Savannah River National Laboratory (SRNL)
- National Energy Technology Laboratory (NETL)

**NSF Research Centers (2):**
- National Center for Atmospheric Research (NCAR)
- National Ecological Observatory Network (NEON)

**DOE Computing Facilities (2):**
- National Center for Computational Sciences (NCCS/OLCF)
- NERSC (National Energy Research Scientific Computing Center)

### 2. Updated Configuration Loader
**File:** `crawler/config/settings.py`

**Changes:**
- Added `major_facilities` to source type map
- Modified `'all'` configuration to load three lists:
  - `top_universities.json` (Peer Institutions)
  - `r1_universities.json` (R1 Institutions)
  - `major_facilities.json` (Major Facilities)
- Added facility format handler in normalization function

### 3. Enhanced Classifier
**File:** `crawler/utils/university_classifier.py`

**Changes:**
- Added `_load_major_facilities()` method
- Loads both full names and abbreviations (TACC, ORNL, etc.)
- Updated `classify()` to return 'facility' category
- Changed default from 'other' to 'facility'
- Priority order: Facility → Peer → R1

### 4. Updated HTML Generator
**File:** `crawler/utils/html_generator.py`

**Changes:**
- Changed column name from "All Others" to "Major Facilities"
- Updated variable names (`other_articles` → `facility_articles`)
- Updated stats display to show "Facilities" count
- All three columns now have clear, descriptive names

## Test Results

```
✅ System Test Results:
   Total sources: 244
   🎓 Peer institutions: 50
   🔬 R1 institutions: 167
   🏛️  Major facilities: 27

✅ Facility Recognition Test:
   ✓ Texas Advanced Computing Center -> facility
   ✓ TACC -> facility
   ✓ Argonne National Laboratory -> facility
   ✓ ORNL -> facility
   ✓ San Diego Supercomputer Center -> facility
   ✓ NERSC -> facility
```

## HTML Output Layout

The generated HTML now displays three distinct columns:

```
┌────────────────────────────────────────────────────────────┐
│         AI UNIVERSITY NEWS - [Date]                        │
├──────────────────┬──────────────────┬──────────────────────┤
│ Peer             │ R1 Institutions  │ Major Facilities     │
│ Institutions     │                  │                      │
│                  │                  │                      │
│ • Harvard        │ • Auburn         │ • TACC               │
│ • Stanford       │ • Alabama        │ • Argonne            │
│ • MIT            │ • ASU            │ • ORNL               │
│ • Princeton      │ • UArizona       │ • LLNL               │
│ ...              │ ...              │ • SDSC               │
│                  │                  │ • NCSA               │
│                  │                  │ ...                  │
└──────────────────┴──────────────────┴──────────────────────┘
```

## Running the Crawler

### Configuration
Ensure `.env` has:
```bash
UNIVERSITY_SOURCE_TYPE=all
```

### Execution
```bash
python -m crawler
```

### View Results
```bash
python scripts/serve_html.py
# Open browser to http://localhost:8000
```

## Facility Data Details

Each facility entry includes:
- **Name:** Full official name
- **Abbreviation:** Common short name (TACC, ORNL, etc.)
- **Affiliated Institution:** Parent organization
- **Facility Type:** NSF Supercomputing Center, DOE National Laboratory, etc.
- **Location:** City, state
- **News Sources:** Primary news URL and AI-specific tag URL
- **Research Focus:** Key research areas including AI/ML
- **Major Systems:** Supercomputers and major infrastructure
- **Crawl Priority:** 100-250 (higher for exascale facilities)

## Major Systems Included

**Exascale Supercomputers:**
- Frontier (ORNL) - #1 on TOP500
- Aurora (Argonne)
- El Capitan (LLNL)

**Leadership Systems:**
- Perlmutter (NERSC)
- Frontera (TACC)
- Summit (ORNL)
- Polaris (Argonne)
- Delta (NCSA)
- Bridges-2 (PSC)
- Expanse (SDSC)

## URL Verification Status

**Verified URLs (confirmed working):**
- TACC: ✓
- SDSC: ✓
- NCSA: ✓
- Argonne: ✓
- LLNL: ✓
- LANL: ✓
- ORNL: ✓
- LBNL: ✓
- SLAC: ✓
- NERSC: ✓
- OLCF: ✓

**Requires Verification:**
- Most other facilities (auto-generated URLs)

## Next Steps

1. **URL Verification:** Test auto-generated news URLs for each facility
2. **RSS Feeds:** Add RSS feed URLs where available
3. **Priority Tuning:** Adjust crawl priorities based on AI research activity
4. **Expand Coverage:** Add more specialized facilities if needed

## Files Summary

**Created:**
- `crawler/config/major_facilities.json` (27 facilities)

**Modified:**
- `crawler/config/settings.py` (facility loading)
- `crawler/utils/university_classifier.py` (facility recognition)
- `crawler/utils/html_generator.py` (three-column layout)

**Documentation:**
- `MAJOR_FACILITIES_UPDATE.md` (this file)
- Updated `CRAWLER_CONFIGURATION_SUMMARY.md`

## Impact

The crawler now monitors **244 total sources**:
- 50 Peer Institutions (elite universities)
- 167 R1 Institutions (research universities)
- 27 Major Facilities (NSF/DOE infrastructure)

This provides comprehensive coverage of AI research across:
- Academic institutions
- National laboratories
- Supercomputing centers
- Major research infrastructure
