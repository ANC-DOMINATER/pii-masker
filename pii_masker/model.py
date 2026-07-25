import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Try importing torch and transformers, gracefully set flag if unavailable
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    TRANSFORMERS_AVAILABLE = True
except (ImportError, OSError, Exception) as e:
    TRANSFORMERS_AVAILABLE = False


@dataclass
class EntityMatch:
    entity_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0
    source: str = "regex"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "confidence": round(self.confidence, 4),
            "source": self.source
        }


@dataclass
class MaskResult:
    original_text: str
    masked_text: str
    pii_dict: Dict[str, List[str]]
    entities: List[EntityMatch]
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_text": self.original_text,
            "masked_text": self.masked_text,
            "pii_dict": self.pii_dict,
            "entities": [e.to_dict() for e in self.entities],
            "processing_time_ms": round(self.processing_time_ms, 2)
        }


class PIIMasker:
    """
    Advanced PII Masker powered by DeBERTa-v3 Transformer model and high-precision
    rule-based regex pattern matchers for comprehensive PII detection & masking.
    """
    def __init__(self, model_path: Optional[str] = None):
        self.device = 'cpu'
        self.tokenizer = None
        self.model = None
        self.use_transformer = False

        current_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            model_path,
            os.path.join(current_dir, "output_model", "deberta3base_1024"),
            os.path.join(current_dir, "..", "pii-masker", "output_model", "deberta3base_1024"),
        ]
        
        target_path = None
        for path in possible_paths:
            if path and os.path.exists(path):
                target_path = path
                break

        if TRANSFORMERS_AVAILABLE and target_path:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(target_path)
                self.model = AutoModelForTokenClassification.from_pretrained(target_path)
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                self.model.to(self.device)
                self.model.eval()
                self.use_transformer = True
                logger.info(f"Loaded DeBERTa-v3 PII model from {target_path} on {self.device}")
            except Exception as e:
                logger.warning(f"Could not load weights from {target_path} ({e}). Using Regex engine.")
                self.use_transformer = False
        else:
            logger.info("Transformers model weights not loaded. Operating in high-precision Rule & Regex engine mode.")

        # Regex patterns for high-precision PII detection
        self.regex_patterns = {
            "SSN": r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b',
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
            "PHONE_NUM": r'(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?(?:\d{3}[-.\s]?)?\d{4}\b',
            "CREDIT_CARD": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            "IP_ADDRESS": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            "URL_PERSONAL": r'\bhttps?://[^\s/$.?#].[^\s]*\b',
            "API_KEY": r'\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|api_key_[a-zA-Z0-9]{16,})\b',
            "STREET_ADDRESS": r'\b\d{1,5}\s+[A-Za-z0-9\s.,#-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\b',
            "USERNAME": r'@\w{3,20}\b',
            "ID_NUM": r'\b[A-Z]{1,2}-\d{6,8}\b|\bID-\d{5,10}\b'
        }

    def detect_regex_entities(self, text: str) -> List[EntityMatch]:
        matches: List[EntityMatch] = []
        for entity_type, pattern in self.regex_patterns.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                val = m.group(0)
                matches.append(EntityMatch(
                    entity_type=entity_type,
                    value=val,
                    start=m.start(),
                    end=m.end(),
                    confidence=0.99,
                    source="regex"
                ))
        return matches

    def detect_transformer_entities(self, text: str) -> List[EntityMatch]:
        if not self.use_transformer or not self.tokenizer or not self.model:
            return []

        matches: List[EntityMatch] = []
        try:
            inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True)
            with torch.no_grad():
                outputs = self.model(**{k: v.to(self.device) for k, v in inputs.items()})

            logits = outputs.logits
            predictions = torch.argmax(logits, dim=2)[0]

            # Reconstruct tokens
            tokens = self.tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
            predicted_labels = [self.model.config.id2label[p.item()] for p in predictions]

            for token, label in zip(tokens, predicted_labels):
                if token in [self.tokenizer.cls_token, self.tokenizer.sep_token, self.tokenizer.pad_token]:
                    continue

                clean_label = label.replace('_STUDENT', '')
                if clean_label != 'O':
                    tag = clean_label.replace('B-', '').replace('I-', '')
                    token_str = token.replace('▁', ' ').replace(' ', ' ').strip()
                    if token_str:
                        match = re.search(re.escape(token_str), text, re.IGNORECASE)
                        if match:
                            matches.append(EntityMatch(
                                entity_type=tag,
                                value=token_str,
                                start=match.start(),
                                end=match.end(),
                                confidence=0.95,
                                source="transformer"
                            ))
        except Exception as e:
            logger.error(f"Transformer inference error: {e}")

        return matches

    def mask_pii(self, input_text: str, mask_format: str = "[{TYPE}]") -> Tuple[str, Dict[str, List[str]]]:
        """
        Mask PII in input_text. Returns tuple (masked_text, pii_dict) for backward compatibility.
        """
        result = self.analyze_and_mask(input_text, mask_format=mask_format)
        return result.masked_text, result.pii_dict

    def analyze_and_mask(self, input_text: str, mask_format: str = "[{TYPE}]") -> MaskResult:
        """
        Analyze input_text, detect all PII entities, and return detailed MaskResult.
        """
        start_time = time.time()
        if not input_text or not input_text.strip():
            return MaskResult(
                original_text=input_text,
                masked_text=input_text,
                pii_dict={},
                entities=[],
                processing_time_ms=0.0
            )

        # Gather matches
        all_matches = self.detect_regex_entities(input_text)
        all_matches.extend(self.detect_transformer_entities(input_text))

        # Filter overlapping matches (sort by start ascending, end descending)
        all_matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
        filtered_matches: List[EntityMatch] = []
        last_end = -1

        for m in all_matches:
            if m.start >= last_end:
                filtered_matches.append(m)
                last_end = m.end

        # Build masked text
        masked_chunks = []
        last_pos = 0
        pii_dict: Dict[str, List[str]] = {}

        for m in filtered_matches:
            masked_chunks.append(input_text[last_pos:m.start])
            mask_token = mask_format.format(TYPE=m.entity_type)
            masked_chunks.append(mask_token)
            last_pos = m.end

            if m.entity_type not in pii_dict:
                pii_dict[m.entity_type] = []
            if m.value not in pii_dict[m.entity_type]:
                pii_dict[m.entity_type].append(m.value)

        masked_chunks.append(input_text[last_pos:])
        masked_text = "".join(masked_chunks)

        elapsed_ms = (time.time() - start_time) * 1000

        return MaskResult(
            original_text=input_text,
            masked_text=masked_text,
            pii_dict=pii_dict,
            entities=filtered_matches,
            processing_time_ms=elapsed_ms
        )

    @staticmethod
    def extract_ssn(input_string: str) -> Dict[str, str]:
        ssn_pattern = r'\b(\d{3}-\d{2}-\d{4}|\d{9})\b'
        ssn_dict = {}
        matches = re.findall(ssn_pattern, input_string)
        for ssn in matches:
            ssn_dict[ssn] = 'SSN'
        return ssn_dict
