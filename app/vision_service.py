from google.cloud import vision
import io

class VisionService:
    """
    A service class to interact with Google Cloud Vision AI for OCR.
    """
    def __init__(self):
        """
        Initializes the VisionService client.
        The client will automatically use credentials set via
        GOOGLE_APPLICATION_CREDENTIALS environment variable.
        """
        self.client = vision.ImageAnnotatorClient()

    def detect_document_text(self, image_data: bytes):
        """
        Detects dense text from an image using DOCUMENT_TEXT_DETECTION.
        This is suitable for scanned documents like exam papers.

        Args:
            image_data (bytes): The raw bytes of the image file.

        Returns:
            dict: A dictionary containing the full extracted text and
                  structured page/block/paragraph/word information.
                  Returns None if no text is detected or on error.
        """
        try:
            image = vision.Image(content=image_data)
            response = self.client.document_text_detection(image=image)
            
            # Extract full text
            full_text = response.full_text_annotation.text if response.full_text_annotation else ""

            # Extract structured data
            pages_data = []
            if response.full_text_annotation and response.full_text_annotation.pages:
                for page in response.full_text_annotation.pages:
                    blocks_data = []
                    for block in page.blocks:
                        paragraphs_data = []
                        for paragraph in block.paragraphs:
                            words_data = []
                            for word in paragraph.words:
                                word_text = ''.join([symbol.text for symbol in word.symbols])
                                words_data.append({
                                    "text": word_text,
                                    "confidence": word.confidence,
                                    "bounding_box": [(v.x, v.y) for v in word.bounding_box.vertices]
                                })
                            paragraphs_data.append({
                                "text": ''.join([symbol.text for word in paragraph.words for symbol in word.symbols]),
                                "confidence": paragraph.confidence,
                                "words": words_data
                            })
                        blocks_data.append({
                            "text": ''.join([symbol.text for paragraph in block.paragraphs for word in paragraph.words for symbol in word.symbols]),
                            "confidence": block.confidence,
                            "paragraphs": paragraphs_data
                        })
                    pages_data.append({
                        "blocks": blocks_data,
                        "width": page.width,
                        "height": page.height
                    })

            return {
                "full_text": full_text,
                "structured_data": pages_data,
                "error": response.error.message if response.error.message else None
            }

        except Exception as e:
            print(f"Error during Vision AI OCR: {e}")
            return {"full_text": "", "structured_data": [], "error": str(e)}

    def detect_text(self, image_data: bytes):
        """
        Detects general text from an image using TEXT_DETECTION.
        Suitable for sparser text, like signs or labels.

        Args:
            image_data (bytes): The raw bytes of the image file.

        Returns:
            dict: A dictionary containing the detected text and annotations.
                  Returns None if no text is detected or on error.
        """
        try:
            image = vision.Image(content=image_data)
            response = self.client.text_detection(image=image)
            texts = response.text_annotations

            extracted_texts = []
            if texts:
                # The first annotation is the entire text detected in the image
                full_text_description = texts[0].description
                
                # Subsequent annotations are individual words or text blocks
                for text in texts[1:]: # Skip the first element as it's the full text
                    extracted_texts.append({
                        "text": text.description,
                        "bounding_box": [(v.x, v.y) for v in text.bounding_box.vertices]
                    })
            
            return {
                "full_text": full_text_description if texts else "",
                "annotations": extracted_texts,
                "error": response.error.message if response.error.message else None
            }

        except Exception as e:
            print(f"Error during Vision AI TEXT_DETECTION: {e}")
            return {"full_text": "", "annotations": [], "error": str(e)}

