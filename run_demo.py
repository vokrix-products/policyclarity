"""Zero-argument demo for the PolicyClarity processor.

Builds an in-memory COI CSV, runs it through process_file(), and asserts the
result contract (title / status / details / due_date on every record).
"""

from processor import process_file

DEMO_CSV = """Policy Number,Insured,Insurer,Coverage,Effective Date,Expiration Date,Limits,Premium
COI-1001,Northwind Logistics,Acme Mutual,General Liability,2024-01-01,2024-12-31,$2,000,000,$18,400
COI-1002,Blue Harbor Cafe,Zenith Insurance,Commercial Property,2024-03-15,2025-03-14,$750,000,$9,120
COI-1003,Summit Builders,Ridgeline Assurance,Workers Compensation,2023-06-01,2024-05-31,$1,000,000,$22,750
"""


def main():
    records = process_file(DEMO_CSV.encode("utf-8"))

    assert isinstance(records, list), "process_file must return a list"
    assert records, "process_file returned no records"
    assert len(records) == 3, "expected 3 records, got %d" % len(records)

    for index, record in enumerate(records):
        assert isinstance(record, dict), "record %d is not a dict" % index
        for key in ("title", "status", "details", "due_date"):
            assert key in record, "record %d missing %r" % (index, key)
        assert record["title"], "record %d has empty title" % index
        assert record["status"], "record %d has empty status" % index
        assert record["details"], "record %d has empty details" % index

    print("PolicyClarity demo OK: %d records" % len(records))
    for record in records:
        print(
            " - %-20s | %-9s | due %s"
            % (record["title"], record["status"], record["due_date"])
        )


if __name__ == "__main__":
    main()
