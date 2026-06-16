"""
PHASE 2: END-TO-END DEMO
=========================
Demonstrates the full Phase 2 workflow:
1. Set up knowledge base from sample documents
2. Take a real meeting transcript
3. Extract claims
4. Validate each claim with Claude Haiku
5. Generate structured report

Usage:
  python phase2_demo.py
"""

import sys
from phase2_kb_setup import setup_knowledge_base
from phase2_validator import validate_transcript, get_priority

# ============================================================================
# SAMPLE MEETING TRANSCRIPT
# ============================================================================
# This could come from Phase 1 audio transcription

SAMPLE_TRANSCRIPT = """
CEO: "Let's review the June 21 release. What's the status?"

Engineering Lead: "Backend is complete and production-ready. We're finishing
database migration this week. Mobile apps are in final testing."

QA Lead: "We're at 82% test coverage. All critical issues are resolved.
We'll have sign-off by June 15."

Product Lead: "We have approval from legal to ship all features. The go-live
scope is locked in. We're using PostgreSQL for the database, which was decided
back in April."

Engineering Lead: "The app store review process is our wild card. That could
take 1-2 weeks."

CEO: "Any blockers?"

QA Lead: "None from our side. Testing is progressing normally."

CEO: "Great. Let's commit to June 21 release. I'll handle app store escalation
if needed."

Product Lead: "Marketing is ready. Budget is at $500,000 total spend."

Engineering Lead: "We've allocated 12 engineers to this project."
"""

# ============================================================================
# FORMATTING UTILITIES
# ============================================================================

def format_validation_result(validation):
    """Format a single validation result for display."""
    claim = validation['claim']
    category = validation['category']
    confidence = validation['confidence']
    priority = validation['priority']
    reasoning = validation['reasoning']
    action = validation['pm_action_suggested']

    # Color codes (simple ASCII)
    category_icons = {
        "VERIFIED": "🟢",
        "CONTRADICTED": "🔴",
        "UNVERIFIED": "🟡",
        "OUTDATED": "⏰",
        "NEEDS_CLARIFICATION": "❓"
    }

    priority_labels = {
        "CRITICAL": "[!!! CRITICAL]",
        "HIGH": "[!! HIGH]",
        "MEDIUM": "[! MEDIUM]",
        "LOW": "[LOW]"
    }

    icon = category_icons.get(category, "?")
    priority_label = priority_labels.get(priority, "")

    print(f"\n{icon} {category} {priority_label}")
    print(f"   Claim: '{claim}'")
    print(f"   Confidence: {confidence:.0%}")
    print(f"   Reasoning: {reasoning}")
    print(f"   Action: {action}")


def generate_report(transcript, validations):
    """Generate a structured report of all validations."""
    report = {
        "summary": {
            "total_claims": len(validations),
            "verified": len([v for v in validations if v['category'] == 'VERIFIED']),
            "contradicted": len([v for v in validations if v['category'] == 'CONTRADICTED']),
            "unverified": len([v for v in validations if v['category'] == 'UNVERIFIED']),
            "outdated": len([v for v in validations if v['category'] == 'OUTDATED']),
            "needs_clarification": len([v for v in validations if v['category'] == 'NEEDS_CLARIFICATION']),
            "critical_issues": len([v for v in validations if v['priority'] == 'CRITICAL']),
            "high_issues": len([v for v in validations if v['priority'] == 'HIGH']),
        },
        "validations": validations
    }
    return report


# ============================================================================
# MAIN DEMO
# ============================================================================

def main():
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  PHASE 2: END-TO-END DEMO".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    # Step 1: Set up knowledge base
    print(f"\n{'='*70}")
    print("STEP 1: SETTING UP KNOWLEDGE BASE")
    print(f"{'='*70}")

    try:
        client, kb_collection = setup_knowledge_base()
    except Exception as e:
        print(f"❌ Error setting up KB: {e}")
        return 1

    # Step 2: Show sample transcript
    print(f"\n{'='*70}")
    print("STEP 2: SAMPLE MEETING TRANSCRIPT")
    print(f"{'='*70}")
    print(f"\n{SAMPLE_TRANSCRIPT}\n")

    # Step 3: Validate all claims
    print(f"\n{'='*70}")
    print("STEP 3: VALIDATING CLAIMS")
    print(f"{'='*70}")

    try:
        validations = validate_transcript(SAMPLE_TRANSCRIPT, kb_collection)
    except Exception as e:
        print(f"❌ Error validating: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print(f"\nFound {len(validations)} claims to validate...\n")

    for i, validation in enumerate(validations, 1):
        print(f"\n[{i}/{len(validations)}]", end=" ")
        format_validation_result(validation)

    # Step 4: Generate report
    print(f"\n{'='*70}")
    print("STEP 4: VALIDATION REPORT")
    print(f"{'='*70}")

    report = generate_report(SAMPLE_TRANSCRIPT, validations)

    print(f"\nSUMMARY:")
    print(f"  Total claims analyzed: {report['summary']['total_claims']}")
    print(f"  🟢 Verified: {report['summary']['verified']}")
    print(f"  🔴 Contradicted: {report['summary']['contradicted']}")
    print(f"  🟡 Unverified: {report['summary']['unverified']}")
    print(f"  ⏰ Outdated: {report['summary']['outdated']}")
    print(f"  ❓ Needs Clarification: {report['summary']['needs_clarification']}")

    print(f"\nISSUES:")
    print(f"  Critical: {report['summary']['critical_issues']}")
    print(f"  High: {report['summary']['high_issues']}")

    # Step 5: Action items
    print(f"\n{'='*70}")
    print("STEP 5: ACTION ITEMS FOR PM")
    print(f"{'='*70}")

    critical_issues = [v for v in validations if v['priority'] == 'CRITICAL']
    high_issues = [v for v in validations if v['priority'] == 'HIGH']

    if critical_issues:
        print(f"\n🔴 CRITICAL ACTIONS:")
        for issue in critical_issues:
            print(f"  • {issue['pm_action_suggested']}")
            print(f"    Reason: {issue['reasoning']}")

    if high_issues:
        print(f"\n🟠 HIGH PRIORITY:")
        for issue in high_issues:
            print(f"  • {issue['pm_action_suggested']}")

    # Summary
    print(f"\n{'='*70}")
    print("✅ PHASE 2 DEMO COMPLETE!")
    print(f"{'='*70}")

    print(f"\n📊 Results:")
    print(f"  - Analyzed {len(validations)} claims from meeting transcript")
    print(f"  - Identified {report['summary']['critical_issues']} critical issues")
    print(f"  - Generated actionable PM recommendations")

    print(f"\n🚀 Next Steps:")
    print(f"  1. Review critical and high-priority action items above")
    print(f"  2. Phase 3: Build FastAPI dashboard for real-time alerts")
    print(f"  3. Integrate with Phase 1 (audio → transcript → validation)")

    return 0


if __name__ == "__main__":
    exit(main())
