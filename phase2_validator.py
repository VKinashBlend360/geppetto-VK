"""
PHASE 2: CLAIM VALIDATION ENGINE
=================================
Uses Claude Haiku to classify meeting claims into 5 categories:
- VERIFIED: Aligns with KB
- CONTRADICTED: Conflicts with KB
- UNVERIFIED: No KB evidence
- OUTDATED: Old info that conflicts with newer KB
- NEEDS_CLARIFICATION: Ambiguous or partial

Usage:
  from phase2_validator import validate_claim
  result = validate_claim("QA is 100% complete", kb_collection)
"""

import os
import json
import re
from dotenv import load_dotenv
from anthropic import Anthropic
import chromadb

# Load environment variables
load_dotenv()

# Initialize Anthropic client (for Claude)
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ============================================================================
# LOAD KNOWLEDGE BASE
# ============================================================================

def load_knowledge_base():
    """
    Load ChromaDB collection created by phase2_kb_setup.py
    """
    kb_client = chromadb.PersistentClient(path="./chroma_data")

    try:
        collection = kb_client.get_collection(name="project_knowledge")
        return collection
    except Exception as e:
        raise RuntimeError(
            f"Knowledge base not found: {e}\n"
            f"Run phase2_kb_setup.py first!"
        )


# ============================================================================
# EXTRACT CLAIMS FROM TEXT
# ============================================================================

def extract_claims(text):
    """
    Simple claim extraction from transcript text.
    Looks for factual statements (sentences with verbs like 'is', 'has', 'will').

    Args:
        text (str): Meeting transcript or text

    Returns:
        List of claim strings
    """
    # Split into sentences
    sentences = text.replace("? ", "?\n").replace("! ", "!\n").split("\n")

    claims = []
    claim_keywords = [
        "is ", "are ", "has ", "have ", "will ", "completed ", "done ",
        "approved ", "ready ", "finished ", "started ", "blocked ",
        "released ", "deployed ", "scheduled "
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Filter for sentences that sound like factual claims
        if any(keyword in sentence.lower() for keyword in claim_keywords):
            if len(sentence) > 10:  # Skip very short sentences
                claims.append(sentence)

    return claims


# ============================================================================
# VALIDATE CLAIM WITH CLAUDE HAIKU
# ============================================================================

def validate_claim(claim, kb_collection):
    """
    Use Claude Haiku to classify a claim into one of 5 categories.

    Args:
        claim (str): The claim to validate
        kb_collection: ChromaDB collection

    Returns:
        Dict with: category, confidence, supporting_sources, reasoning, action
    """

    # Step 1: Search KB for relevant documents
    search_results = kb_collection.query(
        query_texts=[claim],
        n_results=3
    )

    # Format KB context
    kb_context = []
    if search_results['documents'] and search_results['documents'][0]:
        for i, doc in enumerate(search_results['documents'][0]):
            metadata = search_results['metadatas'][0][i]
            kb_context.append({
                'source': metadata.get('source', 'unknown'),
                'text': doc
            })

    # Step 2: Create Claude prompt
    kb_text = "\n\n".join([f"[{item['source']}]\n{item['text']}" for item in kb_context])

    prompt = f"""You are validating a claim made in a project meeting against a knowledge base.

CLAIM: "{claim}"

KNOWLEDGE BASE:
{kb_text if kb_text else "(No relevant KB documents found)"}

Classify this claim into ONE category:
1. VERIFIED - Claim aligns with documented sources
2. CONTRADICTED - Claim conflicts with documented sources
3. UNVERIFIED - No supporting or conflicting evidence in KB
4. OUTDATED - Claim was true but newer KB docs contradict it
5. NEEDS_CLARIFICATION - Claim is ambiguous, partial, or temporal

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "category": "VERIFIED|CONTRADICTED|UNVERIFIED|OUTDATED|NEEDS_CLARIFICATION",
  "confidence": 0.85,
  "supporting_sources": ["source1", "source2"],
  "conflicting_sources": ["source3"],
  "reasoning": "Why this category?",
  "pm_action_suggested": "What should PM do?"
}}"""

    # Step 3: Call Claude Haiku
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    # Step 4: Parse response
    response_text = response.content[0].text.strip()

    try:
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        result = {
            "category": "UNVERIFIED",
            "confidence": 0.5,
            "supporting_sources": [],
            "conflicting_sources": [],
            "reasoning": "Could not parse response",
            "pm_action_suggested": "Manual review needed"
        }

    return result


# ============================================================================
# PRIORITY ASSIGNMENT
# ============================================================================

def get_priority(category, confidence):
    """
    Assign priority level based on category and confidence.

    Returns: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    """
    if category == "CONTRADICTED" and confidence > 0.85:
        return "CRITICAL"
    elif category in ["CONTRADICTED", "OUTDATED"] and confidence > 0.7:
        return "HIGH"
    elif category in ["NEEDS_CLARIFICATION", "UNVERIFIED"]:
        return "MEDIUM"
    else:
        return "LOW"


# ============================================================================
# MAIN VALIDATION PIPELINE
# ============================================================================

def validate_transcript(transcript_text, kb_collection):
    """
    Validate all claims in a transcript.

    Args:
        transcript_text (str): Full meeting transcript
        kb_collection: ChromaDB collection

    Returns:
        List of validated claims with categories
    """
    # Extract claims
    claims = extract_claims(transcript_text)

    # Validate each claim
    validations = []
    for claim in claims:
        validation = validate_claim(claim, kb_collection)
        validation['claim'] = claim
        validation['priority'] = get_priority(
            validation['category'],
            validation['confidence']
        )
        validations.append(validation)

    return validations


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Demo: Load KB and validate sample claims."""

    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  PHASE 2: CLAIM VALIDATION ENGINE".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    # Load KB
    print(f"\n{'='*70}")
    print("LOADING KNOWLEDGE BASE")
    print(f"{'='*70}")
    kb_collection = load_knowledge_base()
    print("✓ Knowledge base loaded")

    # Test claims
    test_claims = [
        "QA is 82% complete",
        "We have approval from legal to ship",
        "The database migration is on track for June 12",
        "The release is scheduled for June 21",
        "We're using PostgreSQL for the main database",
        "All mobile app tests are passing",
        "The budget is $2 million",
    ]

    print(f"\n{'='*70}")
    print("VALIDATING TEST CLAIMS")
    print(f"{'='*70}")

    for claim in test_claims:
        print(f"\nClaim: '{claim}'")

        result = validate_claim(claim, kb_collection)

        print(f"  Category: {result['category']}")
        print(f"  Confidence: {result['confidence']:.0%}")

        if result['supporting_sources']:
            print(f"  Supporting: {', '.join(result['supporting_sources'][:2])}")

        if result['conflicting_sources']:
            print(f"  Conflicting: {', '.join(result['conflicting_sources'][:2])}")

        print(f"  Action: {result['pm_action_suggested']}")

    print(f"\n{'='*70}")
    print("✅ VALIDATION ENGINE READY!")
    print(f"{'='*70}")
    print("\nYou can now:")
    print("  1. Run phase2_demo.py for full integration test")
    print("  2. Integrate with phase1_audio_pipeline_simple.py")
    print("  3. Build Phase 3 dashboard")


if __name__ == "__main__":
    main()
