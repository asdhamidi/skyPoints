# SkyPoints — Source Data Analysis

Reference record of the analysis performed on the assessment's supplied materials: the illustrative flat-file sample in the assessment brief, and the three real per-country files (`AUS.xlsx`, `IND.csv`, `USA.csv`). Resolutions are already incorporated into `01_Design_Specification.md`; this document is the supporting evidence, kept for traceability.

---

## 1. Source Files Analyzed

| File | Format | Columns supplied | Rows |
|---|---|---|---|
| `AUS.xlsx` | Excel workbook | `Unique ID, Member Name, Tier Type, Date of Birth, Date of Enrollment, Date of Flight` | 3 |
| `IND.csv` | CSV | `ID, Name, DOB, TierCode, EnrollmentDate, Individual or Corporate, Flight Date` | 3 |
| `USA.csv` | CSV | `ID, Name, TierCode, EnrollmentDate, FlightDate` | 3 |

---

## 2. Findings

| Finding | Evidence | Resolution |
|---|---|---|
| `ID` is source-local, not globally unique | All three files independently number members `1, 2, 3…` | `member_key = country_code \|\| '-' \|\| member_id` — `01_Design_Specification.md` §3 |
| Cross-country move detection is structurally limited | A physical country move would arrive as a new local ID in a different source file, with no shared key to the old record | Scoped limitation stated in `01_Design_Specification.md` §3, §9 |
| Three incompatible date formats | `IND`: text `M/D/YYYY`. `AUS`: Excel datetimes, except a literal string `"NULL"` (member 1 DOB) and an invalid string `"2021-13-13"` (member 2 enrollment date). `USA`: digits concatenated with no delimiter; `1052022` and `1152022` each admit two valid date interpretations | Per-source explicit format masks; ambiguous values quarantined, not guessed — `01_Design_Specification.md` §4 |
| Schema conformance gaps | `USA.csv` has no `DOB` column; `IND.csv` carries `Individual or Corporate`, absent from the canonical layout; none of the three carry `State`, `Agent_Name`, `Post_Code`, or `Is_Active` | `dob` NULL for USA rows; `Individual or Corporate` mapped to `membership_type`; remaining fields NULL — `01_Design_Specification.md` §1, §2 |
| Excel format has no native Snowflake ingestion path | `AUS.xlsx` cannot be loaded via `COPY INTO` directly | Excel→CSV conversion component — `03_Technical_Build_Plan.md` §3 |

---

## 3. Assessment Sample Data — Design Intent Assessment

Evaluated against the assessment brief's own instruction (deliverable 5) to catch "data issues visible in the sample data."

| Item | Confidence it is intentional | Basis |
|---|---|---|
| Key Column marked on `Member_Name`, not `Member_Id`, in the field-position spec table | High | Sits in the formal spec table the candidate must consult for the explicitly-required "key-column uniqueness" check; `Member_Name` is not a valid uniqueness key at stated scale |
| Country codes mixed: `USA`/`IND`/`CAN` (ISO alpha-3) vs. `PHIL`/`AU` (non-standard) | High | Directly affects country-table routing, the exercise's central mechanic |
| DOB loses its leading zero between the flat file (`03051985`) and the staging table (`3051985`) | High | Shown as an explicit before/after ETL comparison on the same page |
| `Post Code` defined at field position 9 but absent from every header/detail row shown | Medium-High | Structural mismatch between the field-count implied by the spec table and the actual sample rows |
| `Member_Id` digit-length variance (`223457` vs. `22345` vs. `2256`) | Medium | Plausible planted malformed-ID case; not conclusively distinguishable from filler data |
| `Agent_Name` present for all rows in the flat file, dropped for 4 of 5 in the staging table | Low | No deliverable maps directly to this; more likely an incomplete illustrative example |
| Staging table header reads "County" where the flat file reads "Country" | Low | Reads as a label typo in the graphic, not a data-quality lesson |
| `AUS.xlsx`/`IND.csv`/`USA.csv` provided as heterogeneous per-country files, despite the brief describing one already-unified daily flat file | High (inferred, not stated outright) | Bundled in the same assessment package; filenames map 1:1 onto the per-country split the exercise is built around; the brief's own framing ("what are all the places the Member Data is available") implies multiple non-uniform sources ahead of the Source System's unification step |

All "High" and "Medium-High" items are reflected as explicit design decisions in `01_Design_Specification.md`.
