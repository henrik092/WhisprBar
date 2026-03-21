"""Text postprocessing for WhisprBar transcription output."""

from whisprbar.config import cfg
from whisprbar.utils import debug


def postprocess_fix_spacing(text: str) -> str:
    """Fix spacing issues in transcribed text.

    Removes multiple spaces, fixes punctuation spacing, and cleans up quotes/parens.

    Args:
        text: Input text

    Returns:
        Text with fixed spacing
    """
    import re

    # Remove multiple spaces
    text = re.sub(r" +", " ", text)

    # Fix punctuation spacing: remove space before, ensure space after
    # Handles: . , ! ? : ;
    text = re.sub(r"\s+([.,!?:;])", r"\1", text)  # Remove space before
    text = re.sub(r"([.,!?:;])(?=[^\s])", r"\1 ", text)  # Add space after if missing

    # Fix quotes and parentheses
    text = re.sub(r"\(\s+", "(", text)  # No space after opening paren
    text = re.sub(r"\s+\)", ")", text)  # No space before closing paren
    # Normalize spacing inside balanced ASCII quotes while preserving outer spacing.
    text = re.sub(r'"\s*([^"]*?)\s*"', r'"\1"', text)
    # Fallback for unmatched opening quote at start/bracket boundaries.
    text = re.sub(r'(^|[\s(\[{])"\s+', r'\1"', text)

    # Fix common formatting issues
    text = re.sub(r"\s+\.", ".", text)  # Remove space before period
    text = re.sub(r"\.\s*\)", ".)", text)  # Fix ". )" to ".)"
    text = re.sub(r"\(\s*\.", "(.", text)  # Fix "( ." to "(."

    return text.strip()


def postprocess_fix_capitalization(text: str, language: str = "de") -> str:
    """Fix capitalization issues in transcribed text.

    Capitalizes first character, after sentence punctuation, and applies
    language-specific rules.

    Args:
        text: Input text
        language: Language code for language-specific rules

    Returns:
        Text with fixed capitalization
    """
    import re

    if not text:
        return text

    # Capitalize first character
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

    # Capitalize after sentence-ending punctuation (. ! ?)
    # Use Unicode-aware pattern to match lowercase letters including ä, ö, ü, é, etc.
    def capitalize_after_punct(match):
        punct = match.group(1)
        space = match.group(2)
        char = match.group(3)
        return punct + space + char.upper()

    text = re.sub(
        r"([.!?])(\s+)([a-zäöüßáéíóúàèìòùâêîôûçñ])",
        capitalize_after_punct,
        text,
        flags=re.IGNORECASE | re.UNICODE
    )

    # Language-specific fixes
    if language == "en":
        # Fix standalone "i" → "I"
        text = re.sub(r"\bi\b", "I", text)
        # Fix "i'" contractions (I'm, I'll, I've, etc.)
        text = re.sub(r"\bi'", "I'", text)

    return text


def postprocess_transcript(text: str, language: str = "de") -> str:
    """Apply all post-processing rules to the transcript.

    Args:
        text: Input transcript
        language: Language code

    Returns:
        Postprocessed transcript
    """
    if not cfg.get("postprocess_enabled"):
        return text

    original_length = len(text)
    debug(f"Post-processing transcript ({original_length} chars)")

    # Apply fixes in order
    if cfg.get("postprocess_fix_spacing", True):
        text = postprocess_fix_spacing(text)

    if cfg.get("postprocess_fix_capitalization", True):
        text = postprocess_fix_capitalization(text, language)

    # TODO: Advanced punctuation correction with transformer model
    if cfg.get("postprocess_fix_punctuation", False):
        debug("Advanced punctuation correction not yet implemented")

    final_length = len(text)
    if final_length != original_length:
        debug(
            f"Post-processing: {original_length} → {final_length} chars "
            f"(Δ{final_length - original_length:+d})"
        )

    return text
