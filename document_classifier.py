import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict

from docling_core.types.doc import PictureItem, TableItem, TextItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("classifier")


@dataclass
class DocumentFeatures:
    """Extracted features from document for classification"""
    total_pages: int
    total_text_length: int
    has_tables: bool
    table_count: int
    has_images: bool
    image_count: int
    keywords_found: Dict[str, int]  # keyword -> count
    layout_patterns: Dict[str, bool]  # pattern -> present
    text_density: float  # chars per page
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ClassificationRule:
    """Rule for a specific document type"""
    doc_type: str
    min_score: float  # Minimum score to classify as this type
    required_keywords: List[str]  # At least one must be present
    optional_keywords: List[str]  # Bonus points
    layout_requirements: Dict[str, bool]  # Layout patterns that should/shouldn't exist
    page_range: Tuple[int, int]  # (min_pages, max_pages), use (0, 999) for no limit
    table_required: bool
    image_required: bool
    weights: Dict[str, float]  # Scoring weights


class DocumentClassifier:
    """Rule-based document classifier using Docling parser"""
    
    def __init__(self, rules_file: str = "classification_rules.json"):
        self.rules = self._load_rules(rules_file)
        self.converter = self._setup_converter()
    
    def _setup_converter(self) -> DocumentConverter:
        """Initialize Docling converter"""
        pdf_opts = PdfPipelineOptions()
        pdf_opts.images_scale = 2.0
        pdf_opts.generate_page_images = False  # Don't need full page images
        pdf_opts.generate_picture_images = True
        
        format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)}
        return DocumentConverter(format_options=format_options)
    
    def _load_rules(self, rules_file: str) -> Dict[str, ClassificationRule]:
        """Load classification rules from JSON"""
        rules_path = Path(rules_file)
        if not rules_path.exists():
            logger.warning(f"Rules file {rules_file} not found. Using default rules.")
            return self._get_default_rules()
        
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules_data = json.load(f)
        
        rules = {}
        for doc_type, rule_dict in rules_data.items():
            rules[doc_type] = ClassificationRule(
                doc_type=doc_type,
                min_score=rule_dict.get('min_score', 0.5),
                required_keywords=rule_dict.get('required_keywords', []),
                optional_keywords=rule_dict.get('optional_keywords', []),
                layout_requirements=rule_dict.get('layout_requirements', {}),
                page_range=tuple(rule_dict.get('page_range', [0, 999])),
                table_required=rule_dict.get('table_required', False),
                image_required=rule_dict.get('image_required', False),
                weights=rule_dict.get('weights', {
                    'keywords': 0.4,
                    'layout': 0.3,
                    'structure': 0.3
                })
            )
        
        return rules
    
    def _get_default_rules(self) -> Dict[str, ClassificationRule]:
        """Default classification rules"""
        return {
            "invoice": ClassificationRule(
                doc_type="invoice",
                min_score=0.6,
                required_keywords=["invoice", "bill", "amount", "total"],
                optional_keywords=["payment", "due date", "tax", "subtotal", "customer"],
                layout_requirements={"has_header": True, "has_table": True},
                page_range=(1, 5),
                table_required=True,
                image_required=False,
                weights={'keywords': 0.5, 'layout': 0.3, 'structure': 0.2}
            ),
            "contract": ClassificationRule(
                doc_type="contract",
                min_score=0.6,
                required_keywords=["agreement", "contract", "party", "terms"],
                optional_keywords=["whereas", "signature", "effective date", "obligations"],
                layout_requirements={"has_sections": True},
                page_range=(2, 50),
                table_required=False,
                image_required=False,
                weights={'keywords': 0.6, 'layout': 0.2, 'structure': 0.2}
            ),
            "resume": ClassificationRule(
                doc_type="resume",
                min_score=0.6,
                required_keywords=["experience", "education", "skills"],
                optional_keywords=["objective", "summary", "projects", "certifications"],
                layout_requirements={"has_sections": True},
                page_range=(1, 4),
                table_required=False,
                image_required=False,
                weights={'keywords': 0.5, 'layout': 0.3, 'structure': 0.2}
            ),
            "report": ClassificationRule(
                doc_type="report",
                min_score=0.5,
                required_keywords=["report", "analysis", "findings", "conclusion"],
                optional_keywords=["executive summary", "recommendations", "methodology"],
                layout_requirements={"has_sections": True, "has_table": True},
                page_range=(3, 100),
                table_required=False,
                image_required=False,
                weights={'keywords': 0.4, 'layout': 0.3, 'structure': 0.3}
            )
        }
    
    def extract_features(self, pdf_path: Path) -> DocumentFeatures:
        """Extract features from PDF using Docling"""
        logger.info(f"Extracting features from: {pdf_path.name}")
        
        # Convert PDF
        conv_res = self.converter.convert(pdf_path)
        doc = conv_res.document
        
        # Extract text
        full_text = doc.export_to_text().lower()
        
        # Count items
        items = list(doc.iterate_items())
        tables = [el for el, _ in items if isinstance(el, TableItem)]
        pictures = [el for el, _ in items if isinstance(el, PictureItem)]
        
        # Collect all keywords from rules
        all_keywords = set()
        for rule in self.rules.values():
            all_keywords.update([k.lower() for k in rule.required_keywords])
            all_keywords.update([k.lower() for k in rule.optional_keywords])
        
        # Count keyword occurrences
        keywords_found = {}
        for keyword in all_keywords:
            count = full_text.count(keyword.lower())
            if count > 0:
                keywords_found[keyword] = count
        
        # Detect layout patterns
        layout_patterns = self._detect_layout_patterns(doc, full_text)
        
        # Calculate text density
        text_density = len(full_text) / max(len(doc.pages), 1)
        
        features = DocumentFeatures(
            total_pages=len(doc.pages),
            total_text_length=len(full_text),
            has_tables=len(tables) > 0,
            table_count=len(tables),
            has_images=len(pictures) > 0,
            image_count=len(pictures),
            keywords_found=keywords_found,
            layout_patterns=layout_patterns,
            text_density=text_density
        )
        
        logger.info(f"Extracted features: pages={features.total_pages}, tables={features.table_count}, images={features.image_count}")
        return features
    
    def _detect_layout_patterns(self, doc, full_text: str) -> Dict[str, bool]:
        """Detect common layout patterns"""
        patterns = {}
        
        # Has header (first 10% of text contains common header keywords)
        header_keywords = ["to:", "from:", "date:", "subject:", "re:"]
        first_portion = full_text[:int(len(full_text) * 0.1)]
        patterns['has_header'] = any(kw in first_portion for kw in header_keywords)
        
        # Has sections (multiple occurrences of numbering or headings)
        section_markers = ["\n1.", "\n2.", "\n3.", "section ", "chapter "]
        patterns['has_sections'] = sum(full_text.count(m) for m in section_markers) >= 3
        
        # Has signature block (common at end)
        signature_keywords = ["signature:", "signed:", "authorized by"]
        last_portion = full_text[-int(len(full_text) * 0.1):]
        patterns['has_signature'] = any(kw in last_portion for kw in signature_keywords)
        
        # Has bullet points or lists
        patterns['has_lists'] = full_text.count("\n•") + full_text.count("\n-") > 5
        
        # Has table (already know from features)
        items = list(doc.iterate_items())
        patterns['has_table'] = any(isinstance(el, TableItem) for el, _ in items)
        
        return patterns
    
    def score_document(self, features: DocumentFeatures, rule: ClassificationRule) -> float:
        """Score document against a specific rule"""
        scores = {}
        
        # 1. Keyword Score
        required_found = sum(1 for kw in rule.required_keywords if kw.lower() in features.keywords_found)
        required_score = required_found / max(len(rule.required_keywords), 1)
        
        optional_found = sum(1 for kw in rule.optional_keywords if kw.lower() in features.keywords_found)
        optional_score = optional_found / max(len(rule.optional_keywords), 1)
        
        keyword_score = (required_score * 0.7) + (optional_score * 0.3)
        scores['keywords'] = keyword_score
        
        # 2. Layout Score
        layout_matches = 0
        layout_total = len(rule.layout_requirements)
        
        for pattern, expected in rule.layout_requirements.items():
            actual = features.layout_patterns.get(pattern, False)
            if actual == expected:
                layout_matches += 1
        
        layout_score = layout_matches / max(layout_total, 1) if layout_total > 0 else 1.0
        scores['layout'] = layout_score
        
        # 3. Structure Score
        structure_score = 0.0
        checks = 0
        
        # Page range check
        if rule.page_range[0] <= features.total_pages <= rule.page_range[1]:
            structure_score += 1.0
        checks += 1
        
        # Table requirement
        if not rule.table_required or (rule.table_required and features.has_tables):
            structure_score += 1.0
        checks += 1
        
        # Image requirement
        if not rule.image_required or (rule.image_required and features.has_images):
            structure_score += 1.0
        checks += 1
        
        structure_score = structure_score / checks
        scores['structure'] = structure_score
        
        # Weighted total
        total_score = (
            scores['keywords'] * rule.weights['keywords'] +
            scores['layout'] * rule.weights['layout'] +
            scores['structure'] * rule.weights['structure']
        )
        
        return total_score
    
    def classify(self, pdf_path: Path) -> Dict:
        """Classify document and return results"""
        logger.info(f"Classifying: {pdf_path.name}")
        
        # Extract features
        features = self.extract_features(pdf_path)
        
        # Score against all rules
        scores = {}
        for doc_type, rule in self.rules.items():
            score = self.score_document(features, rule)
            scores[doc_type] = score
        
        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        best_rule = self.rules[best_type]
        
        # Check if meets minimum threshold
        classification_passed = best_score >= best_rule.min_score
        
        result = {
            "file_name": pdf_path.name,
            "classified_as": best_type if classification_passed else "unknown",
            "confidence": round(best_score, 3),
            "threshold_met": classification_passed,
            "all_scores": {k: round(v, 3) for k, v in scores.items()},
            "features": features.to_dict(),
            "timestamp": None  # Add if needed
        }
        
        logger.info(f"Classification: {result['classified_as']} (confidence: {result['confidence']})")
        return result


def main():
    """Example usage"""
    # Initialize classifier
    classifier = DocumentClassifier(rules_file="classification_rules.json")
    
    # Classify a single document
    pdf_path = Path("resume.pdf")
    if pdf_path.exists():
        result = classifier.classify(pdf_path)
        
        # Save result
        output = Path("output") / f"{pdf_path.stem}_classification.json"
        output.parent.mkdir(exist_ok=True)
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nClassified as: {result['classified_as']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
